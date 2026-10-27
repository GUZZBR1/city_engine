import os
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .arena_jobs import ArenaNotFoundError, create_arena, get_arena, run_arena
from .arena_schemas import ArenaRequest, ArenaResponse
from .city_provider import (
    CityNotFoundError,
    SnapshotUnavailableError,
    get_city_map,
    get_city_metadata,
)
from .schemas import (
    CityMap,
    CityMetadata,
    ComparisonRequest,
    ComparisonResponse,
    ErrorResponse,
    HealthResponse,
    SimulationRequest,
    SimulationResponse,
)
from .simulation_jobs import (
    InvalidComparisonScenario,
    SimulationNotFoundError,
    UnknownSimulationWindowError,
    create_comparison,
    create_job,
    get_comparison,
    get_job,
    run_comparison,
    run_job,
)


def _local_cors_origin() -> str:
    origin = os.getenv("API_CORS_ORIGIN", "http://localhost:5173").rstrip("/")
    parsed = urlparse(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("API_CORS_ORIGIN deve apontar para localhost ou 127.0.0.1.")
    return origin


app = FastAPI(
    title="Urban Arena API",
    description="Consulta Aurora sintética e solicita simulações-base locais.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_local_cors_origin()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/api/v1/cities/{city_id}",
    response_model=CityMetadata,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["cities"],
    summary="Metadados do snapshot da cidade",
)
def city_metadata(city_id: str) -> CityMetadata:
    try:
        return get_city_metadata(city_id)
    except CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Cidade '{city_id}' não encontrada.") from exc
    except SnapshotUnavailableError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/v1/cities/{city_id}/map",
    response_model=CityMap,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["cities"],
    summary="Bounds e camadas em coordenadas cartesianas locais",
    description="As camadas são LocalFeatureCollection em metros locais; não são GeoJSON RFC 7946 nem latitude/longitude.",
)
def city_map(city_id: str) -> CityMap:
    try:
        return get_city_map(city_id)
    except CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Cidade '{city_id}' não encontrada.") from exc
    except SnapshotUnavailableError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/api/v1/simulations",
    response_model=SimulationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["simulations"],
    summary="Solicitar simulação-base",
)
def start_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks,
) -> SimulationResponse:
    try:
        job = create_job(request)
    except UnknownSimulationWindowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Não foi possível preparar a simulação.") from exc
    background_tasks.add_task(run_job, job.simulation_id)
    return SimulationResponse(simulation=job)


@app.get(
    "/api/v1/simulations/{simulation_id}",
    response_model=SimulationResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["simulations"],
    summary="Consultar status ou resultado da simulação",
)
def simulation_status(simulation_id: str) -> SimulationResponse:
    try:
        return SimulationResponse(simulation=get_job(simulation_id))
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Simulação não encontrada.") from exc


@app.post(
    "/api/v1/comparisons",
    response_model=ComparisonResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"model": ErrorResponse}},
    tags=["comparisons"],
    summary="Criar comparação pareada de temporização semafórica",
)
def start_comparison(
    request: ComparisonRequest,
    background_tasks: BackgroundTasks,
) -> ComparisonResponse:
    try:
        comparison = create_comparison(request)
    except InvalidComparisonScenario as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(run_comparison, comparison.comparison_id)
    return ComparisonResponse(comparison=comparison)


@app.get(
    "/api/v1/comparisons/{comparison_id}",
    response_model=ComparisonResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["comparisons"],
    summary="Consultar comparação pareada",
)
def comparison_status(comparison_id: str) -> ComparisonResponse:
    try:
        return ComparisonResponse(comparison=get_comparison(comparison_id))
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Comparação não encontrada.") from exc


@app.post(
    "/api/v1/arenas",
    response_model=ArenaResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={500: {"model": ErrorResponse}},
    tags=["arenas"],
    summary="Criar arena anual sintética Aurora",
)
def start_arena(
    request: ArenaRequest,
    background_tasks: BackgroundTasks,
) -> ArenaResponse:
    try:
        arena = create_arena(request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível preparar a arena sintética Aurora.",
        ) from exc
    background_tasks.add_task(run_arena, arena.arena_id)
    return ArenaResponse(arena=arena)


@app.get(
    "/api/v1/arenas/{arena_id}",
    response_model=ArenaResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["arenas"],
    summary="Consultar status e rodadas confirmadas da arena",
)
def arena_status(arena_id: str) -> ArenaResponse:
    try:
        return ArenaResponse(arena=get_arena(arena_id))
    except ArenaNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Arena não encontrada.") from exc
