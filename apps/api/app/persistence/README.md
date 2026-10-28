# API PostgreSQL persistence

`PostgresRepository` is an API-boundary adapter using `asyncpg`; domain packages do not import a database driver or SQL. Create one pool at API startup with `await create_pool(dsn)`, pass it to the repository, call `await repository.apply_migrations()`, and close it during shutdown with `await close_pool(pool)`. The repository does not own or implicitly close the supplied pool.

The first migration requires PostgreSQL with the PostGIS extension available and permission to run `CREATE EXTENSION postgis`. Migrations are versioned by filename and tracked in `schema_migrations`; each file executes once in a transaction under a PostgreSQL advisory lock. The SQL statements are repeat-safe as well, but applied migration files should be treated as immutable and followed by a new numbered migration for schema changes.

Dataset rows are immutable versions keyed by `(dataset_id, artifact_sha256)`. A changed artifact hash creates another version; the database rejects updates to those rows. Dataset registration requires a 64-character SHA-256. Observations reference that exact dataset version and are idempotent by `(dataset_id, artifact_sha256, observation_id)`. Canonical `source_id` remains the row-level sensor/source identifier; a separate `data_source_id` FK is derived from the registered dataset version. Latitude/longitude are preserved even when the source CRS is unknown. `geom`, stored as `geometry(Point, 4326)` and indexed with GiST, is created only when metadata explicitly declares `spatial_reference="EPSG:4326"`.

Observation wall time is stored in `TIMESTAMP WITHOUT TIME ZONE`; a separate nullable offset in minutes preserves an explicit fixed offset. A naive source timestamp remains naive. The adapter never assigns UTC. Offsets with sub-minute precision are rejected because the storage contract records minute precision.

Unit tests use a fake pool and validate SQL construction, JSON serialization, dataset-version idempotency, migration tracking, and timestamp handling. They do not start PostgreSQL. The opt-in integration suite at `apps/api/tests/integration/test_postgis_integration.py` uses a real database, creates/drops a unique schema, applies migrations 001/002 twice, prints the server and PostGIS build versions, and verifies immutable dataset versions, FK/check constraints, replay-run version matching, spatial geometry/`ST_DWithin`, pool reconnect recovery, and concurrent insert idempotency.

## Reproduce with Docker Compose

The disposable Compose service pins PostgreSQL 16 with the `postgis/postgis:16-3.6` image family (currently PostgreSQL 16 and PostGIS 3.6.4); the test output records the exact server and extension build versions used. Docker Engine and Compose v2 are required.

From the repository root:

```sh
docker compose -f apps/api/compose.postgis.integration.yml up --detach --wait
docker compose -f apps/api/compose.postgis.integration.yml exec -T postgis \
  psql -U city_engine_test -d city_engine_test -c 'SELECT version(), postgis_full_version();'
CITY_ENGINE_TEST_DATABASE_URL=postgresql://city_engine_test:city_engine_test@127.0.0.1:55432/city_engine_test \
  uv run --project apps/api --with pytest pytest -s apps/api/tests/integration/test_postgis_integration.py -q
docker compose -f apps/api/compose.postgis.integration.yml down --volumes
```

The database is created for this test only and the last command removes its container and data volume. If the test command fails, run the cleanup command separately after collecting the failure output. Never point `CITY_ENGINE_TEST_DATABASE_URL` at a database with data to keep: the test drops its uniquely named schema on completion.

## Local PostgreSQL alternative

When Docker is unavailable on Debian/Ubuntu, install PostgreSQL 16 and its matching PostGIS package, then create a dedicated test role/database:

```sh
sudo apt-get install postgresql-16 postgresql-16-postgis-3
sudo -u postgres psql -d postgres <<'SQL'
CREATE ROLE city_engine_test LOGIN SUPERUSER PASSWORD 'city_engine_test';
CREATE DATABASE city_engine_test OWNER city_engine_test;
SQL
CITY_ENGINE_TEST_DATABASE_URL=postgresql://city_engine_test:city_engine_test@127.0.0.1:5432/city_engine_test \
  uv run --project apps/api --with pytest pytest -s apps/api/tests/integration/test_postgis_integration.py -q
```

Record the printed `PostgreSQL` and `PostGIS` versions with the result. This path requires host administrator access and PostgreSQL configured to listen on `127.0.0.1`. Do not reuse a production or valuable development database.

A run without `CITY_ENGINE_TEST_DATABASE_URL` skips the integration test; fake-pool unit tests and a skipped integration test are not evidence of PostgreSQL/PostGIS execution.
