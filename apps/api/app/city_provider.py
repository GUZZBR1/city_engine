"""Adapter from the Python city core to the HTTP response schemas."""

from functools import lru_cache
from typing import Any

from .schemas import CityMap, CityMetadata

CITY_ID = "aurora-base-v1"


class CityNotFoundError(Exception):
    pass


class SnapshotUnavailableError(Exception):
    pass


@lru_cache(maxsize=1)
def _snapshot() -> dict[str, Any]:
    try:
        # Keep configuration loading and generation in the domain package.
        from urban_arena import load_aurora_snapshot
    except ImportError as exc:
        raise SnapshotUnavailableError(
            "O pacote urban_arena não está instalado ou não expõe o gerador de snapshot."
        ) from exc

    try:
        _, generated = load_aurora_snapshot()
        if hasattr(generated, "model_dump"):
            generated = generated.model_dump(mode="json")
        elif hasattr(generated, "dict"):
            generated = generated.dict()
        if not isinstance(generated, dict):
            raise TypeError("O gerador deve retornar um objeto de snapshot serializável.")
        return generated
    except Exception as exc:
        raise SnapshotUnavailableError("Não foi possível gerar ou carregar o snapshot de Aurora.") from exc


def get_city_metadata(city_id: str) -> CityMetadata:
    if city_id != CITY_ID:
        raise CityNotFoundError(city_id)
    snapshot = _snapshot()
    try:
        return CityMetadata.model_validate(snapshot)
    except Exception as exc:
        raise SnapshotUnavailableError("O snapshot de Aurora não atende ao contrato da API.") from exc


def get_city_map(city_id: str) -> CityMap:
    if city_id != CITY_ID:
        raise CityNotFoundError(city_id)
    snapshot = _snapshot()
    try:
        return CityMap.model_validate(snapshot)
    except Exception as exc:
        raise SnapshotUnavailableError("O snapshot de Aurora não atende ao contrato de mapa da API.") from exc
