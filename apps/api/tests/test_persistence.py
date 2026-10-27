from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence.postgres import PostgresRepository, restore_timestamp
from traffic_observations import ProvenanceKind, TrafficObservation


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.migrations = set()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO schema_migrations" in sql:
            self.migrations.add(args[0])

    async def executemany(self, sql, rows):
        self.executed.append((sql, rows))

    async def fetchval(self, sql, version):
        return 1 if version in self.migrations else None

    @asynccontextmanager
    async def transaction(self):
        yield


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()
        self.executed = self.connection.executed
        self.batch = None

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def execute(self, sql, *args):
        return await self.connection.execute(sql, *args)

    async def executemany(self, sql, rows):
        self.batch = (sql, rows)
        return await self.connection.executemany(sql, rows)


def test_observation_serialization_preserves_naive_and_explicit_offset_times():
    naive = TrafficObservation(
        observation_id="naive", timestamp=datetime(2025, 2, 3, 4, 5), source_id="s",
        dataset_id="d", provenance_kind=ProvenanceKind.OBSERVED,
    )
    offset_time = datetime(2025, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-3)))
    aware = naive.model_copy(update={"observation_id": "aware", "timestamp": offset_time})

    naive_row = PostgresRepository.observation_values(naive)
    aware_row = PostgresRepository.observation_values(aware)

    assert naive_row[3:5] == (datetime(2025, 2, 3, 4, 5), None)
    assert aware_row[3:5] == (datetime(2025, 2, 3, 4, 5), -180)
    assert restore_timestamp(*aware_row[3:5]) == offset_time


def test_initial_migration_declares_api_persistence_schema_and_spatial_index():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "001_initial_postgis.sql"
    sql = migration.read_text(encoding="utf-8")

    for table in ("data_sources", "datasets", "observations", "experiments", "replay_definitions", "runs", "run_artifacts"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "geometry(Point, 4326)" in sql
    assert "USING GIST (geom)" in sql
    assert "BEFORE UPDATE ON datasets" in sql and "BEFORE DELETE ON datasets" in sql
    for job_type in ("replay", "simulation", "calibration", "validation"):
        assert f"'{job_type}'" in sql
    assert "'paused'" in sql
    assert "runs_replay_requires_dataset_version CHECK" in sql
    assert "runs_dataset_version_pair CHECK" in sql

    upgrade = migration.with_name("002_runs_require_replay_dataset.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE runs ADD CONSTRAINT runs_replay_requires_dataset_version CHECK" in upgrade
    assert "ALTER TABLE runs ADD CONSTRAINT runs_dataset_version_pair CHECK" in upgrade


def test_observation_batch_is_idempotent_and_builds_postgis_point_in_sql():
    async def scenario():
        pool = FakePool()
        repo = PostgresRepository(pool)
        observation = TrafficObservation(
            observation_id="o-1", timestamp=datetime(2025, 1, 1), source_id="s", dataset_id="d",
            latitude=-23.5, longitude=-46.6, provenance_kind=ProvenanceKind.OBSERVED,
            metadata={"sensor": "A"},
        )

        assert await repo.insert_observations("d", "a" * 64, [observation]) == 1
        sql, rows = pool.batch
        assert "ON CONFLICT (dataset_id, artifact_sha256, observation_id) DO NOTHING" in sql
        assert "CASE WHEN $14 = 'EPSG:4326'" in sql
        assert "ST_MakePoint($13::double precision, $12::double precision)" in sql
        assert "SELECT source_id FROM datasets WHERE dataset_id=$7 AND artifact_sha256=$8" in sql
        assert rows[0][11:14] == (-23.5, -46.6, None)
        assert rows[0][23] == '{"sensor":"A"}'
        assert await repo.insert_observations("d", "a" * 64, []) == 0
        spatial = observation.model_copy(update={
            "observation_id": "o-2",
            "metadata": {"spatial_reference": "EPSG:4326"},
        })
        await repo.insert_observations("d", "a" * 64, [spatial])
        assert pool.batch[1][0][13] == "EPSG:4326"

    asyncio.run(scenario())


def test_register_dataset_uses_sha256_identity_and_does_not_update_existing_version():
    async def scenario():
        pool = FakePool()
        repo = PostgresRepository(pool)
        manifest = {
            "dataset_id": "dataset-x", "source_uri": "https://example.test/source", "artifact": "data.csv",
            "artifact_sha256": "a" * 64, "license_status": "unknown", "provenance_kind": "observed",
            "provenance_note": "source supplied", "supporting_artifacts": (),
        }

        assert await repo.register_dataset(manifest) == "dataset-x"
        source_sql, _ = pool.executed[-2]
        dataset_sql, args = pool.executed[-1]
        assert "ON CONFLICT (source_id) DO NOTHING" in source_sql
        assert "ON CONFLICT (dataset_id, artifact_sha256) DO NOTHING" in dataset_sql
        assert args[3] == "a" * 64
        assert "UPDATE datasets" not in dataset_sql

    asyncio.run(scenario())


def test_migrations_record_versions_and_skip_previously_applied_files(tmp_path: Path):
    async def scenario():
        (tmp_path / "001_test.sql").write_text("SELECT 42", encoding="utf-8")
        pool = FakePool()
        repo = PostgresRepository(pool, migrations_dir=tmp_path)

        await repo.apply_migrations()
        await repo.apply_migrations()

        assert pool.connection.migrations == {"001_test.sql"}
        assert sum(sql == "SELECT 42" for sql, _ in pool.executed) == 1

    asyncio.run(scenario())


def test_run_creation_validates_job_type_and_records_json_without_mutating_on_conflict():
    async def scenario():
        pool = FakePool()
        repo = PostgresRepository(pool)
        assert await repo.create_run("r1", "simulation", {"seed": 4}) == "r1"
        sql, args = pool.executed[-1]
        assert "ON CONFLICT (run_id) DO NOTHING" in sql
        assert args[7] == '{"seed":4}'
        with pytest.raises(ValueError, match="unsupported job_type"):
            await repo.create_run("r2", "unknown")

    asyncio.run(scenario())


def test_replay_experiment_run_update_and_artifact_operations_serialize_json():
    async def scenario():
        pool = FakePool()
        repo = PostgresRepository(pool)

        await repo.create_experiment("e1", "baseline", {"seed": 7})
        await repo.create_replay_definition("rd1", "dataset-x", "a" * 64, {"start": "2025-01-01"})
        await repo.create_run(
            "r1", "replay", replay_definition_id="rd1", dataset_id="dataset-x", artifact_sha256="a" * 64
        )
        await repo.update_run("r1", status="completed", result={"count": 3}, metrics={"rows": 3})
        await repo.register_run_artifact("r1", "s3://results/r1.csv", "csv", sha256="f" * 64)

        assert '"seed":7' in pool.executed[0][1][2]
        assert '"start":"2025-01-01"' in pool.executed[1][1][3]
        update_sql, update_args = pool.executed[3]
        assert "UPDATE runs SET status" in update_sql
        assert update_args[1:4] == ("completed", '{"count":3}', '{"rows":3}')
        artifact_sql, artifact_args = pool.executed[4]
        assert "ON CONFLICT (run_id,artifact_uri) DO NOTHING" in artifact_sql
        assert artifact_args[1:4] == ("s3://results/r1.csv", "csv", "f" * 64)

    asyncio.run(scenario())
