"""HTTP controls for dataset-scoped traffic observation replay."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from traffic_observations import (
    DATASET_ID,
    DatasetSourceError,
    ReplayCapacityError,
    ReplayControlError,
    ReplayFilters,
    ReplayManager,
    ReplayNotFoundError,
    ReplaySnapshot,
    SmartCityTrafficCsvAdapter,
    TrafficObservation,
    UnsupportedSourceFilter,
)


router = APIRouter(prefix="/api/v1/traffic-replays", tags=["traffic-replays"])
_manager = ReplayManager()


class TrafficReplayCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: Literal["kaggle:rauffauzanrambe/smart-city-traffic-flow-prediction-dataset"] = DATASET_ID
    filters: ReplayFilters = Field(default_factory=ReplayFilters)
    observations_per_second: float = Field(default=1.0, gt=0, le=1000)


class TrafficReplayControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["pause", "resume", "reset", "step", "set_speed"]
    count: int | None = Field(default=None, ge=1, le=10_000)
    observations_per_second: float | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def validate_action_parameters(self) -> "TrafficReplayControlRequest":
        if self.action == "step" and self.count is None:
            raise ValueError("count é obrigatório para step")
        if self.action == "set_speed" and self.observations_per_second is None:
            raise ValueError("observations_per_second é obrigatório para set_speed")
        return self


class TrafficReplayControlResponse(BaseModel):
    replay: ReplaySnapshot
    advanced_observations: tuple[TrafficObservation, ...] = ()


def _traffic_file_path() -> Path:
    configured_dir = os.getenv("CITY_ENGINE_TRAFFIC_DATA_DIR")
    data_dir = Path(configured_dir) if configured_dir else (
        Path(__file__).resolve().parents[3] / "data/external/smart-city-traffic"
    )
    return data_dir / "traffic_sensor_data.csv"


@router.post(
    "",
    response_model=ReplaySnapshot,
    status_code=status.HTTP_201_CREATED,
    summary="Criar replay histórico de fixture de tráfego",
    description=(
        "Cria uma sessão pausada do CSV de sensores do Kaggle. Os dados são simulados e ficam "
        "em um estado de observações separado; não alteram o snapshot imutável de Aurora nem alimentam SUMO."
    ),
    responses={422: {"description": "Dataset inválido ou filtro sem suporte"}, 503: {"description": "Arquivo local não configurado"}},
)
def create_traffic_replay(request: TrafficReplayCreateRequest) -> ReplaySnapshot:
    try:
        source = SmartCityTrafficCsvAdapter(_traffic_file_path())
        return _manager.create(source, request.filters, request.observations_per_second)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Dataset de replay não encontrado.") from exc
    except DatasetSourceError as exc:
        if "não encontrado" in str(exc):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Dataset de replay indisponível. Configure CITY_ENGINE_TRAFFIC_DATA_DIR ou baixe somente "
                    "traffic_sensor_data.csv com o Kaggle CLI."
                ),
            ) from exc
        if "não foi possível" in str(exc).lower():
            raise HTTPException(status_code=422, detail="Não foi possível ler o dataset local.") from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnsupportedSourceFilter as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReplayCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ReplayControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{replay_id}", response_model=ReplaySnapshot, summary="Consultar estado do replay")
def get_traffic_replay(replay_id: str) -> ReplaySnapshot:
    try:
        return _manager.get(replay_id)
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Replay não encontrado.") from exc


@router.get(
    "/{replay_id}/state",
    response_model=ReplaySnapshot,
    summary="Consultar overlay de estado de tráfego",
    description="Retorna a observação mais recente por sensor para esta sessão, sem mutar CitySnapshot/Aurora.",
)
def get_traffic_replay_state(replay_id: str) -> ReplaySnapshot:
    return get_traffic_replay(replay_id)


@router.post(
    "/{replay_id}/controls",
    response_model=TrafficReplayControlResponse,
    summary="Controlar replay: pause, resume, reset, step ou set_speed",
)
def control_traffic_replay(replay_id: str, request: TrafficReplayControlRequest) -> TrafficReplayControlResponse:
    try:
        advanced = _manager.control(
            replay_id,
            request.action,
            count=request.count or 1,
            observations_per_second=request.observations_per_second,
        )
        return TrafficReplayControlResponse(replay=_manager.get(replay_id), advanced_observations=advanced)
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Replay não encontrado.") from exc
    except (ReplayControlError, UnsupportedSourceFilter, DatasetSourceError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
