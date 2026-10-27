CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    source_uri TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dataset records are append-only versions. A changed artifact hash creates a new row.
CREATE TABLE IF NOT EXISTS datasets (
    dataset_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES data_sources(source_id),
    artifact TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-fA-F]{64}$'),
    period_start TIMESTAMP WITHOUT TIME ZONE,
    period_end TIMESTAMP WITHOUT TIME ZONE,
    source_timezone TEXT,
    declared_license TEXT,
    license_status TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    provenance_note TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_start IS NULL OR period_end IS NULL OR period_start <= period_end),
    UNIQUE (dataset_id, artifact_sha256)
);

CREATE OR REPLACE FUNCTION reject_dataset_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'dataset artifact records are immutable';
END;
$$;
DROP TRIGGER IF EXISTS datasets_immutable_update ON datasets;
DROP TRIGGER IF EXISTS datasets_immutable_delete ON datasets;
CREATE TRIGGER datasets_immutable_update BEFORE UPDATE ON datasets
    FOR EACH ROW EXECUTE FUNCTION reject_dataset_mutation();
CREATE TRIGGER datasets_immutable_delete BEFORE DELETE ON datasets
    FOR EACH ROW EXECUTE FUNCTION reject_dataset_mutation();

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    -- Keep wall-clock fields and the supplied offset separately; never infer UTC for naive values.
    observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    timestamp_offset_minutes SMALLINT,
    artifact_sha256 TEXT NOT NULL,
    -- source_id is the row-level sensor/source id; data_source_id links the provider via its dataset version.
    source_id TEXT NOT NULL,
    data_source_id TEXT NOT NULL REFERENCES data_sources(source_id),
    dataset_id TEXT NOT NULL,
    location_id TEXT,
    road_segment_id TEXT,
    intersection_id TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    spatial_reference TEXT,
    vehicle_count BIGINT,
    flow_veh_h DOUBLE PRECISION,
    mean_speed_kmh DOUBLE PRECISION,
    density DOUBLE PRECISION,
    congestion_level TEXT,
    weather JSONB,
    event_type TEXT,
    confidence DOUBLE PRECISION,
    provenance_kind TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(Point, 4326),
    FOREIGN KEY (dataset_id, artifact_sha256)
        REFERENCES datasets(dataset_id, artifact_sha256),
    PRIMARY KEY (dataset_id, artifact_sha256, observation_id),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);
CREATE INDEX IF NOT EXISTS observations_geom_gist_idx ON observations USING GIST (geom);
CREATE INDEX IF NOT EXISTS observations_dataset_time_idx ON observations (dataset_id, observed_at);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    spec JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS replay_definitions (
    replay_definition_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    spec JSONB NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (replay_definition_id, dataset_id, artifact_sha256),
    FOREIGN KEY (dataset_id, artifact_sha256)
        REFERENCES datasets(dataset_id, artifact_sha256)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT REFERENCES experiments(experiment_id),
    replay_definition_id TEXT REFERENCES replay_definitions(replay_definition_id),
    dataset_id TEXT,
    artifact_sha256 TEXT,
    job_type TEXT NOT NULL CHECK (job_type IN ('replay', 'simulation', 'calibration', 'validation')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'paused', 'running', 'completed', 'failed', 'cancelled')),
    spec JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    FOREIGN KEY (dataset_id, artifact_sha256)
        REFERENCES datasets(dataset_id, artifact_sha256),
    FOREIGN KEY (replay_definition_id, dataset_id, artifact_sha256)
        REFERENCES replay_definitions(replay_definition_id, dataset_id, artifact_sha256),
    CONSTRAINT runs_replay_requires_dataset_version CHECK (
        replay_definition_id IS NULL OR
        (job_type = 'replay' AND dataset_id IS NOT NULL AND artifact_sha256 IS NOT NULL)
    ),
    CONSTRAINT runs_dataset_version_pair CHECK (
        (dataset_id IS NULL) = (artifact_sha256 IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_uri TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    sha256 TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, artifact_uri)
);
