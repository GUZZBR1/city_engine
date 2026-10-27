"""Small asyncpg repository; persistence stays at the API boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_MIGRATION_LOCK_ID = 7_349_202_610
_RUN_STATUSES = {"queued", "paused", "running", "completed", "failed", "cancelled"}


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"), ensure_ascii=False)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _timestamp_parts(value: datetime) -> tuple[datetime, int | None]:
    """Return wall time and explicit fixed offset; naive timestamps stay naive."""
    offset = value.utcoffset()
    if offset is None:
        return value, None
    seconds = offset.total_seconds()
    if seconds % 60:
        raise ValueError("timestamp offsets with sub-minute precision are not supported")
    return value.replace(tzinfo=None), int(seconds // 60)


def restore_timestamp(wall_time: datetime, offset_minutes: int | None) -> datetime:
    """Restore the input's naive or fixed-offset datetime representation."""
    if offset_minutes is None:
        return wall_time
    return wall_time.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))


async def create_pool(dsn: str, **kwargs: Any) -> Any:
    """Create an asyncpg pool. Call :func:`close_pool` during API shutdown."""
    import asyncpg

    return await asyncpg.create_pool(dsn=dsn, **kwargs)


async def close_pool(pool: Any) -> None:
    """Close a pool created by :func:`create_pool`."""
    await pool.close()


class PostgresRepository:
    """Persistence operations backed by a caller-owned asyncpg-compatible pool."""

    def __init__(self, pool: Any, migrations_dir: Path = MIGRATIONS_DIR) -> None:
        self.pool = pool
        self.migrations_dir = migrations_dir

    async def apply_migrations(self) -> None:
        migrations = sorted(self.migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
        async with self.pool.acquire() as connection:
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            for migration in migrations:
                async with connection.transaction():
                    await connection.execute("SELECT pg_advisory_xact_lock($1)", _MIGRATION_LOCK_ID)
                    exists = await connection.fetchval(
                        "SELECT 1 FROM schema_migrations WHERE version = $1", migration.name
                    )
                    if exists:
                        continue
                    await connection.execute(migration.read_text(encoding="utf-8"))
                    await connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES ($1)", migration.name
                    )

    async def register_source(self, source_id: str, source_uri: str, metadata: Any = None) -> str:
        await self.pool.execute(
            "INSERT INTO data_sources(source_id, source_uri, metadata) VALUES ($1, $2, $3::jsonb) "
            "ON CONFLICT (source_id) DO NOTHING",
            source_id, source_uri, _json(metadata or {}),
        )
        return source_id

    async def register_dataset(
        self, manifest: Any, *, metadata: Any = None, period_start: datetime | None = None,
        period_end: datetime | None = None, source_timezone: str | None = None,
    ) -> str:
        """Register a source manifest as a hash-addressed immutable dataset version."""
        dataset_id = str(_get(manifest, "dataset_id"))
        artifact_hash = _get(manifest, "artifact_sha256")
        if not artifact_hash:
            raise ValueError("dataset artifact_sha256 is required for immutable registration")
        artifact_hash = str(artifact_hash).lower()
        if len(artifact_hash) != 64 or any(c not in "0123456789abcdef" for c in artifact_hash):
            raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256")
        source_uri = str(_get(manifest, "source_uri"))
        source_id = str(_get(manifest, "source_id", source_uri))
        await self.register_source(source_id, source_uri)
        extras = dict(metadata or {})
        extras["supporting_artifacts"] = _get(manifest, "supporting_artifacts", ())
        await self.pool.execute(
            """INSERT INTO datasets
            (dataset_id, source_id, artifact, artifact_sha256, period_start, period_end, source_timezone,
             declared_license, license_status, provenance_kind, provenance_note, metadata)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
            ON CONFLICT (dataset_id, artifact_sha256) DO NOTHING""",
            dataset_id, source_id, str(_get(manifest, "artifact")), artifact_hash,
            period_start, period_end, source_timezone,
            _get(manifest, "declared_license"), str(_plain(_get(manifest, "license_status"))),
            str(_plain(_get(manifest, "provenance_kind"))), str(_get(manifest, "provenance_note")), _json(extras),
        )
        return dataset_id

    @staticmethod
    def observation_values(observation: Any) -> tuple[Any, ...]:
        timestamp, offset_minutes = _timestamp_parts(_get(observation, "timestamp"))
        latitude = _get(observation, "latitude")
        longitude = _get(observation, "longitude")
        return (
            _get(observation, "observation_id"), _get(observation, "schema_version", "1.0"),
            str(_plain(_get(observation, "observation_type", "traffic"))), timestamp, offset_minutes,
            _get(observation, "source_id"), _get(observation, "dataset_id"), _get(observation, "location_id"),
            _get(observation, "road_segment_id"), _get(observation, "intersection_id"), latitude, longitude,
            _get(observation, "vehicle_count"), _get(observation, "flow_veh_h"),
            _get(observation, "mean_speed_kmh"), _get(observation, "density"),
            _get(observation, "congestion_level"),
            _json(_get(observation, "weather")) if _get(observation, "weather") is not None else None,
            _get(observation, "event_type"), _get(observation, "confidence"),
            str(_plain(_get(observation, "provenance_kind", "unknown"))), _json(_get(observation, "metadata", {})),
        )

    async def insert_observations(
        self, dataset_id: str, artifact_sha256: str, observations: Sequence[Any],
    ) -> int:
        """Insert observations idempotently for one immutable dataset version."""
        if not observations:
            return 0
        if any(str(_get(item, "dataset_id")) != dataset_id for item in observations):
            raise ValueError("all observations must belong to the registered dataset_id")
        artifact_sha256 = artifact_sha256.lower()
        if len(artifact_sha256) != 64 or any(c not in "0123456789abcdef" for c in artifact_sha256):
            raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256")
        sql = """INSERT INTO observations
        (observation_id, schema_version, observation_type, observed_at, timestamp_offset_minutes,
         source_id, dataset_id, artifact_sha256, location_id, road_segment_id, intersection_id, latitude, longitude,
         spatial_reference,
         vehicle_count, flow_veh_h, mean_speed_kmh, density, congestion_level, weather, event_type,
         confidence, provenance_kind, metadata, data_source_id, geom)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20::jsonb,$21,$22,$23,
                $24::jsonb,
                (SELECT source_id FROM datasets WHERE dataset_id=$7 AND artifact_sha256=$8),
                CASE WHEN $14 = 'EPSG:4326' AND $12::double precision IS NOT NULL
                     THEN ST_SetSRID(ST_MakePoint($13::double precision, $12::double precision), 4326) END)
        ON CONFLICT (dataset_id, artifact_sha256, observation_id) DO NOTHING"""
        values = []
        for observation in observations:
            base = self.observation_values(observation)
            metadata = _get(observation, "metadata", {})
            spatial_reference = _get(metadata, "spatial_reference")
            values.append((*base[:7], artifact_sha256, *base[7:12], spatial_reference, *base[12:]))
        await self.pool.executemany(sql, values)
        return len(observations)

    async def create_replay_definition(
        self, replay_definition_id: str, dataset_id: str, artifact_sha256: str,
        spec: Any, provenance: Any = None,
    ) -> str:
        await self.pool.execute(
            """INSERT INTO replay_definitions
            (replay_definition_id,dataset_id,artifact_sha256,spec,provenance)
            VALUES ($1,$2,$3,$4::jsonb,$5::jsonb) ON CONFLICT (replay_definition_id) DO NOTHING""",
            replay_definition_id, dataset_id, artifact_sha256.lower(), _json(spec), _json(provenance or {}),
        )
        return replay_definition_id

    async def create_experiment(
        self, experiment_id: str, name: str, spec: Any = None, provenance: Any = None,
    ) -> str:
        await self.pool.execute(
            """INSERT INTO experiments(experiment_id,name,spec,provenance)
            VALUES ($1,$2,$3::jsonb,$4::jsonb) ON CONFLICT (experiment_id) DO NOTHING""",
            experiment_id, name, _json(spec or {}), _json(provenance or {}),
        )
        return experiment_id

    async def create_run(
        self, run_id: str, job_type: str, spec: Any = None, *, status: str = "queued",
        experiment_id: str | None = None, replay_definition_id: str | None = None,
        dataset_id: str | None = None, artifact_sha256: str | None = None,
        metrics: Any = None, provenance: Any = None,
    ) -> str:
        if job_type not in {"replay", "simulation", "calibration", "validation"}:
            raise ValueError(f"unsupported job_type: {job_type}")
        if status not in _RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        if (dataset_id is None) != (artifact_sha256 is None):
            raise ValueError("dataset_id and artifact_sha256 must be supplied together")
        if artifact_sha256 is not None:
            artifact_sha256 = artifact_sha256.lower()
            if len(artifact_sha256) != 64 or any(c not in "0123456789abcdef" for c in artifact_sha256):
                raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256")
        if replay_definition_id is not None:
            if job_type != "replay":
                raise ValueError("replay_definition_id is only valid for replay runs")
            if dataset_id is None or artifact_sha256 is None:
                raise ValueError("replay runs must identify the same immutable dataset version as their definition")
        await self.pool.execute(
            """INSERT INTO runs
            (run_id,experiment_id,replay_definition_id,dataset_id,artifact_sha256,job_type,status,spec,metrics,provenance)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb)
            ON CONFLICT (run_id) DO NOTHING""",
            run_id, experiment_id, replay_definition_id, dataset_id, artifact_sha256, job_type, status,
            _json(spec or {}), _json(metrics or {}), _json(provenance or {}),
        )
        return run_id

    async def update_run(
        self, run_id: str, *, status: str, result: Any = None, metrics: Any = None,
        provenance: Any = None, progress: Any = None,
    ) -> None:
        if status not in _RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        await self.pool.execute(
            """UPDATE runs SET status=$2, result=$3::jsonb, metrics=COALESCE($4::jsonb, metrics),
            provenance=COALESCE($5::jsonb, provenance), progress=COALESCE($6::jsonb, progress),
            started_at=CASE WHEN $2='running' THEN COALESCE(started_at,now()) ELSE started_at END,
            finished_at=CASE WHEN $2 IN ('completed','failed','cancelled') THEN now() ELSE NULL END,
            updated_at=now() WHERE run_id=$1""",
            run_id, status, _json(result) if result is not None else None,
            _json(metrics) if metrics is not None else None,
            _json(provenance) if provenance is not None else None,
            _json(progress) if progress is not None else None,
        )

    async def register_run_artifact(
        self, run_id: str, artifact_uri: str, artifact_type: str, *,
        sha256: str | None = None, metadata: Any = None,
    ) -> None:
        await self.pool.execute(
            """INSERT INTO run_artifacts(run_id,artifact_uri,artifact_type,sha256,metadata)
            VALUES ($1,$2,$3,$4,$5::jsonb)
            ON CONFLICT (run_id,artifact_uri) DO NOTHING""",
            run_id, artifact_uri, artifact_type, sha256, _json(metadata or {}),
        )
