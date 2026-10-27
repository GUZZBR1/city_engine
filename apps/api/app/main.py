import os
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

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
    TrafficCompetitionRequest,
    TrafficCompetitionResponse,
)
from .simulation_jobs import (
    SimulationNotFoundError,
    InvalidComparisonScenario,
    UnknownSimulationWindowError,
    create_job,
    get_job,
    run_job,
    create_comparison,
    get_comparison,
    run_comparison,
    create_traffic_competition,
    get_traffic_competition,
    run_traffic_competition,
)
from .traffic_replays import router as traffic_replays_router


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
    description="Consulta Aurora sintética e executa simulações e competições locais de tráfego.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_local_cors_origin()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(traffic_replays_router)


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
    "/api/v1/traffic-competitions",
    response_model=TrafficCompetitionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"model": ErrorResponse}},
    tags=["competitions"],
    summary="Executar competição pareada entre cinco empresas viárias",
)
def start_traffic_competition(
    request: TrafficCompetitionRequest,
    background_tasks: BackgroundTasks,
) -> TrafficCompetitionResponse:
    try:
        competition = create_traffic_competition(request)
    except InvalidComparisonScenario as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(run_traffic_competition, competition.competition_id)
    return TrafficCompetitionResponse(competition=competition)


@app.get(
    "/api/v1/traffic-competitions/{competition_id}",
    response_model=TrafficCompetitionResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["competitions"],
    summary="Consultar competição entre empresas viárias",
)
def traffic_competition_status(competition_id: str) -> TrafficCompetitionResponse:
    try:
        return TrafficCompetitionResponse(competition=get_traffic_competition(competition_id))
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Competição não encontrada.") from exc
