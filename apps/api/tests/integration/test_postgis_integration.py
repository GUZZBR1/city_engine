"""Opt-in PostgreSQL/PostGIS integration coverage.

Set CITY_ENGINE_TEST_DATABASE_URL to a disposable database URL. The test creates
and drops a unique schema and requires permission to create the PostGIS extension
when it is not already installed in that database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime

import pytest

from app.persistence.postgres import PostgresRepository
from traffic_observations import ProvenanceKind, TrafficObservation


TEST_DATABASE_URL = os.getenv("CITY_ENGINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set CITY_ENGINE_TEST_DATABASE_URL to a disposable PostgreSQL/PostGIS database",
)


def test_postgis_migrations_integrity_spatial_query_recovery_and_concurrency():
    async def scenario() -> None:
        import asyncpg

        assert TEST_DATABASE_URL is not None
        admin = await asyncpg.connect(TEST_DATABASE_URL)
        schema = f"ce_it_{uuid.uuid4().hex}"
        pool = None
        try:
            database_name = await admin.fetchval("SELECT current_database()")
            if database_name in {"template0", "template1"}:
                raise AssertionError(
                    "CITY_ENGINE_TEST_DATABASE_URL must target a dedicated disposable test database"
                )
            await admin.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            pool = await asyncpg.create_pool(
                dsn=TEST_DATABASE_URL,
                server_settings={"search_path": f'"{schema}",public'},
            )
            repo = PostgresRepository(pool)
            await repo.apply_migrations()
            await repo.apply_migrations()

            migration_count = await pool.fetchval("SELECT count(*) FROM schema_migrations")
            assert migration_count == 2

            suffix = uuid.uuid4().hex
            source_id = f"integration-source:{suffix}"
            dataset_id = f"integration-dataset:{suffix}"
            digest_a, digest_b = "a" * 64, "b" * 64
            manifest = {
                "dataset_id": dataset_id,
                "source_id": source_id,
                "source_uri": "https://example.invalid/tirtl-test.csv",
                "artifact": "tirtl-test.csv",
                "artifact_sha256": digest_a,
                "declared_license": "CC-BY-4.0",
                "license_status": "declared",
                "provenance_kind": "observed",
                "provenance_note": "Integration-test fixture only",
                "supporting_artifacts": (),
            }
            await repo.register_dataset(manifest)
            await repo.register_dataset({**manifest, "artifact_sha256": digest_b})

            observation = TrafficObservation(
                observation_id=f"obs:{suffix}",
                timestamp=datetime(2026, 10, 1, 8, 0),
                source_id="505",
                dataset_id=dataset_id,
                latitude=-37.830815,
                longitude=144.900329,
                vehicle_count=12,
                provenance_kind=ProvenanceKind.OBSERVED,
                metadata={"spatial_reference": "EPSG:4326", "test": True},
            )
            inserted = await asyncio.gather(*(
                repo.insert_observations(dataset_id, digest_a, [observation])
                for _ in range(2)
            ))
            assert inserted == [1, 1]
            stored = await pool.fetchrow(
                """SELECT data_source_id, geom IS NOT NULL AS has_geom,
                          ST_DWithin(geom::geography,
                              ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 20) AS nearby
                   FROM observations WHERE dataset_id=$3 AND artifact_sha256=$4""",
                observation.longitude, observation.latitude, dataset_id, digest_a,
            )
            assert stored["data_source_id"] == source_id
            assert stored["has_geom"] is True
            assert stored["nearby"] is True
            assert await pool.fetchval(
                "SELECT count(*) FROM observations WHERE dataset_id=$1 AND artifact_sha256=$2",
                dataset_id, digest_a,
            ) == 1

            replay_id = f"replay:{suffix}"
            await repo.create_replay_definition(replay_id, dataset_id, digest_a, {"speed": 1})
            run_id = f"run:{suffix}"
            await repo.create_run(
                run_id, "replay", replay_definition_id=replay_id,
                dataset_id=dataset_id, artifact_sha256=digest_a,
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await pool.execute(
                    """INSERT INTO runs (run_id,replay_definition_id,job_type,status)
                       VALUES ($1,$2,'replay','queued')""",
                    f"bad-null:{suffix}", replay_id,
                )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await pool.execute(
                    """INSERT INTO runs
                       (run_id,replay_definition_id,dataset_id,artifact_sha256,job_type,status)
                       VALUES ($1,$2,$3,$4,'replay','queued')""",
                    f"bad-version:{suffix}", replay_id, dataset_id, digest_b,
                )
            with pytest.raises(asyncpg.RaiseError):
                await pool.execute("UPDATE datasets SET artifact='mutated' WHERE dataset_id=$1", dataset_id)

            await pool.close()
            pool = await asyncpg.create_pool(
                dsn=TEST_DATABASE_URL,
                server_settings={"search_path": f'"{schema}",public'},
            )
            assert await pool.fetchval("SELECT count(*) FROM observations") == 1
            assert await pool.fetchval("SELECT count(*) FROM runs WHERE run_id=$1", run_id) == 1
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(scenario())
