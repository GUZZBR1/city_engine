import os
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from simulation import SimulationError

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
from .multiseed_schemas import (
    ExperimentCancelResponse,
    ExperimentCreateResponse,
    ExperimentResponse,
    ExperimentRetryRequest,
    MultiSeedManifestRequest,
)
from .multiseed_experiments import (
    ExperimentBudgetError,
    ExperimentConflictError,
    ExperimentNotFoundError,
    ExperimentStateError,
    create_experiment,
    get_experiment,
    list_resumable_experiments,
    retry_experiment,
    cancel_experiment,
    run_experiment,
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


_mobility_recovery_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="aurora-mobility-recovery")


def _dispatch_persisted_mobility_experiments() -> None:
    for experiment_id in list_resumable_experiments():
        _mobility_recovery_pool.submit(run_experiment, experiment_id)


@asynccontextmanager
async def _lifespan(_app):
    _dispatch_persisted_mobility_experiments()
    yield


app = FastAPI(
    title="Urban Arena API",
    description="Consulta Aurora sintética e solicita simulações-base locais.",
    version="0.1.0",
    lifespan=_lifespan,
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


@app.post(
    "/api/v1/mobility-experiments",
    response_model=ExperimentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["mobility-experiments"],
    summary="Criar protocolo pareado Aurora multi-semente",
)
def start_mobility_experiment(request: MultiSeedManifestRequest, background_tasks: BackgroundTasks) -> ExperimentCreateResponse:
    try:
        experiment = create_experiment(request)
    except ExperimentBudgetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExperimentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, SimulationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if experiment.status in {"queued", "partial"} and experiment.missing_pairs > 0:
        background_tasks.add_task(run_experiment, experiment.experiment_id)
    return ExperimentCreateResponse(experiment=experiment)


@app.get(
    "/api/v1/mobility-experiments/{experiment_id}",
    response_model=ExperimentResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["mobility-experiments"],
    summary="Consultar protocolo, pares, tentativas e resumos por janela",
)
def mobility_experiment_status(experiment_id: str) -> ExperimentResponse:
    try:
        return ExperimentResponse(experiment=get_experiment(experiment_id))
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Experimento de mobilidade não encontrado.") from exc


@app.post(
    "/api/v1/mobility-experiments/{experiment_id}/retry",
    response_model=ExperimentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["mobility-experiments"],
    summary="Retomar pares com falha recuperável dentro do orçamento",
)
def resume_mobility_experiment(experiment_id: str, request: ExperimentRetryRequest, background_tasks: BackgroundTasks) -> ExperimentResponse:
    try:
        experiment = retry_experiment(experiment_id, request.pair_ids)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Experimento de mobilidade não encontrado.") from exc
    except ExperimentStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if experiment.status in {"queued", "partial"} and experiment.missing_pairs > 0:
        background_tasks.add_task(run_experiment, experiment.experiment_id)
    return ExperimentResponse(experiment=experiment)


@app.post(
    "/api/v1/mobility-experiments/{experiment_id}/cancel",
    response_model=ExperimentCancelResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["mobility-experiments"],
    summary="Cancelar trabalho de mobilidade pendente",
)
def stop_mobility_experiment(experiment_id: str) -> ExperimentCancelResponse:
    try:
        experiment = cancel_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Experimento de mobilidade não encontrado.") from exc
    except ExperimentStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExperimentCancelResponse(experiment_id=experiment.experiment_id, status=experiment.status,
        cancellation_requested=experiment.cancellation_requested)
