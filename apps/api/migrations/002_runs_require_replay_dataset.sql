-- Preserve dataset-version integrity for databases that already applied migration 001.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'runs_replay_requires_dataset_version'
          AND conrelid = 'runs'::regclass
    ) THEN
        ALTER TABLE runs ADD CONSTRAINT runs_replay_requires_dataset_version CHECK (
            replay_definition_id IS NULL OR
            (job_type = 'replay' AND dataset_id IS NOT NULL AND artifact_sha256 IS NOT NULL)
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'runs_dataset_version_pair'
          AND conrelid = 'runs'::regclass
    ) THEN
        ALTER TABLE runs ADD CONSTRAINT runs_dataset_version_pair CHECK (
            (dataset_id IS NULL) = (artifact_sha256 IS NULL)
        );
    END IF;
END;
$$;
