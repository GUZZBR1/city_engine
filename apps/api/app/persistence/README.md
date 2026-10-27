# API PostgreSQL persistence

`PostgresRepository` is an API-boundary adapter using `asyncpg`; domain packages do not import a database driver or SQL. Create one pool at API startup with `await create_pool(dsn)`, pass it to the repository, call `await repository.apply_migrations()`, and close it during shutdown with `await close_pool(pool)`. The repository does not own or implicitly close the supplied pool.

The first migration requires PostgreSQL with the PostGIS extension available and permission to run `CREATE EXTENSION postgis`. Migrations are versioned by filename and tracked in `schema_migrations`; each file executes once in a transaction under a PostgreSQL advisory lock. The SQL statements are repeat-safe as well, but applied migration files should be treated as immutable and followed by a new numbered migration for schema changes.

Dataset rows are immutable versions keyed by `(dataset_id, artifact_sha256)`. A changed artifact hash creates another version; the database rejects updates to those rows. Dataset registration requires a 64-character SHA-256. Observations reference that exact dataset version and are idempotent by `(dataset_id, artifact_sha256, observation_id)`. Canonical `source_id` remains the row-level sensor/source identifier; a separate `data_source_id` FK is derived from the registered dataset version. Latitude/longitude are preserved even when the source CRS is unknown. `geom`, stored as `geometry(Point, 4326)` and indexed with GiST, is created only when metadata explicitly declares `spatial_reference="EPSG:4326"`.

Observation wall time is stored in `TIMESTAMP WITHOUT TIME ZONE`; a separate nullable offset in minutes preserves an explicit fixed offset. A naive source timestamp remains naive. The adapter never assigns UTC. Offsets with sub-minute precision are rejected because the storage contract records minute precision.

Unit tests use a fake pool and validate SQL construction, JSON serialization, dataset-version idempotency, migration tracking, and timestamp handling. They do not start PostgreSQL and do not verify migration execution against PostgreSQL, PostGIS installation, or spatial queries.
