"""Import a bounded Victoria TIRTL site selection into PostgreSQL/PostGIS."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from itertools import islice
from pathlib import Path
from typing import Iterator, TypeVar

from traffic_observations import VictoriaTirtlZipAdapter

from .persistence.postgres import PostgresRepository, close_pool, create_pool


T = TypeVar("T")


def _chunks(items: Iterator[T], size: int) -> Iterator[list[T]]:
    while batch := list(islice(items, size)):
        yield batch


async def import_tirtl(
    *, archive_path: Path, sites_path: Path, site_ids: set[int], database_url: str,
) -> dict[str, object]:
    source = VictoriaTirtlZipAdapter(archive_path, sites_path, site_ids=site_ids)
    observations = list(source.iter_observations())
    if not observations:
        raise ValueError("a seleção não produziu observações; nenhum dataset foi registrado")
    pool = await create_pool(database_url)
    repository = PostgresRepository(pool)
    try:
        await repository.apply_migrations()
        start_at = min(item.timestamp for item in observations)
        end_at = max(item.timestamp for item in observations)
        await repository.register_dataset(
            source.manifest,
            period_start=start_at,
            period_end=end_at,
            source_timezone="unspecified by source",
            metadata={
                "site_ids": sorted(site_ids),
                "time_resolution_minutes": 15,
                "derived_fields": {
                    "flow_veh_h": "interval count multiplied by 4",
                    "mean_speed_kmh": "volume-weighted speed-bin midpoint; open top bin uses lower bound",
                },
                "coordinate_reference": "not specified by source; PostGIS geometry intentionally omitted",
            },
        )
        attempted = 0
        for batch in _chunks(iter(observations), 500):
            attempted += await repository.insert_observations(
                source.manifest.dataset_id, source.manifest.artifact_sha256 or "", batch
            )
        return {
            "dataset_id": source.manifest.dataset_id,
            "artifact_sha256": source.manifest.artifact_sha256,
            "site_ids": sorted(site_ids),
            "observations_attempted": attempted,
            "period_start": start_at.isoformat(),
            "period_end": end_at.isoformat(),
            "provenance_kind": source.manifest.provenance_kind.value,
        }
    finally:
        await close_pool(pool)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="ZIP mensal oficial do DTP")
    parser.add_argument("--sites", type=Path, required=True, help="CSV oficial TIRTL Sites")
    parser.add_argument("--site", type=int, action="append", required=True, help="Site ID; pode repetir")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL é obrigatório para importação persistente")
    result = asyncio.run(import_tirtl(
        archive_path=args.archive,
        sites_path=args.sites,
        site_ids=set(args.site),
        database_url=database_url,
    ))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
