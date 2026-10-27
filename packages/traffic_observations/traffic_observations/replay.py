"""Replay controls and a replaceable in-memory observation store."""

from __future__ import annotations

from collections.abc import Iterator
from threading import RLock, Timer
from typing import Literal
from uuid import uuid4

from .models import (
    BoundingBox,
    ReplayFilters,
    ReplaySnapshot,
    ReplayStatus,
    TrafficObservation,
)
from .sources import ObservationSource, UnsupportedSourceFilter


class ReplayNotFoundError(KeyError):
    pass


class ReplayControlError(ValueError):
    pass


class ReplayCapacityError(ReplayControlError):
    pass


class InMemoryObservationStore:
    """Materialized latest state, scoped to one replay and replaceable by a DB store."""

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str], TrafficObservation] = {}
        self._lock = RLock()

    def upsert(self, observation: TrafficObservation) -> None:
        key = (observation.dataset_id, observation.source_id)
        with self._lock:
            current = self._latest.get(key)
            if current is None or observation.timestamp >= current.timestamp:
                self._latest[key] = observation

    def latest(self) -> tuple[TrafficObservation, ...]:
        with self._lock:
            return tuple(sorted(
                self._latest.values(),
                key=lambda observation: (observation.location_id or observation.source_id, observation.observation_id),
            ))

    def clear(self) -> None:
        with self._lock:
            self._latest.clear()


class ReplaySession:
    def __init__(
        self,
        replay_id: str,
        source: ObservationSource,
        filters: ReplayFilters,
        observations_per_second: float,
    ) -> None:
        if not 0 < observations_per_second <= 1000:
            raise ReplayControlError("observations_per_second deve estar entre 0 e 1000")
        if filters.region is not None and not source.supports_region_filter:
            raise UnsupportedSourceFilter("A fonte não possui coordenadas verificadas para filtrar por região.")
        if getattr(source, "timestamp_timezone", "unknown") == "naive" and any(
            boundary is not None and boundary.tzinfo is not None
            for boundary in (filters.start_at, filters.end_at)
        ):
            raise UnsupportedSourceFilter("Esta fonte não informa fuso horário; filtros temporais também devem ser sem fuso.")
        self.replay_id = replay_id
        self.source = source
        self.filters = filters
        self.observations_per_second = observations_per_second
        self.store = InMemoryObservationStore()
        self._status = ReplayStatus.PAUSED
        self._emitted_count = 0
        self._current_timestamp = None
        self._error: str | None = None
        self._iterator = self._filtered(source.iter_observations())
        self._lock = RLock()

    def _filtered(self, observations: Iterator[TrafficObservation]) -> Iterator[TrafficObservation]:
        allowed_types = set(self.filters.observation_types)
        allowed_locations = set(self.filters.location_ids)
        bounds: BoundingBox | None = self.filters.region
        for observation in observations:
            if observation.observation_type not in allowed_types:
                continue
            if allowed_locations and observation.location_id not in allowed_locations:
                continue
            if self.filters.start_at and observation.timestamp < self.filters.start_at:
                continue
            if self.filters.end_at and observation.timestamp > self.filters.end_at:
                continue
            if bounds is not None:
                if observation.latitude is None or observation.longitude is None:
                    continue
                if not (
                    bounds.min_latitude <= observation.latitude <= bounds.max_latitude
                    and bounds.min_longitude <= observation.longitude <= bounds.max_longitude
                ):
                    continue
            yield observation

    def snapshot(self) -> ReplaySnapshot:
        with self._lock:
            return ReplaySnapshot(
                replay_id=self.replay_id,
                status=self._status,
                dataset=self.source.manifest,
                filters=self.filters,
                observations_per_second=self.observations_per_second,
                emitted_count=self._emitted_count,
                current_timestamp=self._current_timestamp,
                error=self._error,
                latest_by_location=self.store.latest(),
            )

    @property
    def status(self) -> ReplayStatus:
        with self._lock:
            return self._status

    def _emit_next(self) -> TrafficObservation | None:
        try:
            observation = next(self._iterator)
        except StopIteration:
            self._status = ReplayStatus.COMPLETED
            return None
        self.store.upsert(observation)
        self._emitted_count += 1
        self._current_timestamp = observation.timestamp
        return observation

    def step(self, count: int = 1) -> tuple[TrafficObservation, ...]:
        if count < 1 or count > 10_000:
            raise ReplayControlError("step count deve estar entre 1 e 10000")
        with self._lock:
            if self._status == ReplayStatus.RUNNING:
                raise ReplayControlError("pause o replay antes de avançar manualmente")
            if self._status == ReplayStatus.COMPLETED:
                raise ReplayControlError("replay concluído; use reset antes de avançar")
            if self._status == ReplayStatus.FAILED:
                raise ReplayControlError("replay falhou; use reset para iniciar novamente")
            emitted = []
            for _ in range(count):
                try:
                    observation = self._emit_next()
                except Exception as exc:
                    self._status = ReplayStatus.FAILED
                    self._error = str(exc)
                    raise
                if observation is None:
                    break
                emitted.append(observation)
            return tuple(emitted)

    def pause(self) -> None:
        with self._lock:
            if self._status == ReplayStatus.RUNNING:
                self._status = ReplayStatus.PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._status == ReplayStatus.COMPLETED:
                raise ReplayControlError("replay concluído; use reset antes de retomar")
            if self._status == ReplayStatus.FAILED:
                raise ReplayControlError("replay falhou; use reset antes de retomar")
            self._status = ReplayStatus.RUNNING

    def reset(self) -> None:
        with self._lock:
            self._iterator = self._filtered(self.source.iter_observations())
            self.store.clear()
            self._emitted_count = 0
            self._current_timestamp = None
            self._error = None
            self._status = ReplayStatus.PAUSED

    def set_speed(self, observations_per_second: float) -> None:
        if not 0 < observations_per_second <= 1000:
            raise ReplayControlError("velocidade deve estar entre 0 e 1000 observações por segundo")
        with self._lock:
            self.observations_per_second = observations_per_second

    def advance_running(self) -> TrafficObservation | None:
        with self._lock:
            if self._status != ReplayStatus.RUNNING:
                return None
            try:
                return self._emit_next()
            except Exception as exc:
                self._status = ReplayStatus.FAILED
                self._error = str(exc)
                return None


class ReplayManager:
    """Bounded process-local replay registry; replace with a durable backend later."""

    def __init__(self, *, max_sessions: int = 100) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions deve ser positivo")
        self.max_sessions = max_sessions
        self._sessions: dict[str, ReplaySession] = {}
        self._timers: dict[str, Timer] = {}
        self._timer_generations: dict[str, int] = {}
        self._lock = RLock()

    def create(
        self,
        source: ObservationSource,
        filters: ReplayFilters | None = None,
        observations_per_second: float = 1.0,
    ) -> ReplaySnapshot:
        replay_id = uuid4().hex
        session = ReplaySession(replay_id, source, filters or ReplayFilters(), observations_per_second)
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                evictable = next(
                    (
                        existing_id
                        for existing_id, existing in self._sessions.items()
                        if existing.status != ReplayStatus.RUNNING
                    ),
                    None,
                )
                if evictable is None:
                    raise ReplayCapacityError(
                        f"limite de {self.max_sessions} replays ativos/retidos atingido"
                    )
                self._cancel_timer(evictable)
                del self._sessions[evictable]
                self._timer_generations.pop(evictable, None)
            self._sessions[replay_id] = session
        return session.snapshot()

    def get(self, replay_id: str) -> ReplaySnapshot:
        return self._get_session(replay_id).snapshot()

    def _get_session(self, replay_id: str) -> ReplaySession:
        try:
            return self._sessions[replay_id]
        except KeyError as exc:
            raise ReplayNotFoundError(replay_id) from exc

    def _cancel_timer(self, replay_id: str) -> None:
        self._timer_generations[replay_id] = self._timer_generations.get(replay_id, 0) + 1
        timer = self._timers.pop(replay_id, None)
        if timer is not None:
            timer.cancel()

    def _schedule(self, replay_id: str) -> None:
        session = self._get_session(replay_id)
        if session.status != ReplayStatus.RUNNING:
            return
        self._cancel_timer(replay_id)
        delay = 1 / session.snapshot().observations_per_second
        generation = self._timer_generations[replay_id]
        timer = Timer(delay, self._tick, args=(replay_id, generation))
        timer.daemon = True
        self._timers[replay_id] = timer
        timer.start()

    def _tick(self, replay_id: str, generation: int) -> None:
        with self._lock:
            try:
                session = self._get_session(replay_id)
            except ReplayNotFoundError:
                return
            if generation != self._timer_generations.get(replay_id):
                return
            self._timers.pop(replay_id, None)
            if session.status != ReplayStatus.RUNNING:
                return
            session.advance_running()
            if session.status == ReplayStatus.RUNNING:
                self._schedule(replay_id)

    def control(
        self,
        replay_id: str,
        action: Literal["pause", "resume", "reset", "step", "set_speed"],
        *,
        count: int = 1,
        observations_per_second: float | None = None,
    ) -> tuple[TrafficObservation, ...]:
        with self._lock:
            session = self._get_session(replay_id)
            if action == "pause":
                self._cancel_timer(replay_id)
                session.pause()
                return ()
            if action == "resume":
                session.resume()
                self._schedule(replay_id)
                return ()
            if action == "reset":
                self._cancel_timer(replay_id)
                session.reset()
                return ()
            if action == "step":
                return session.step(count)
            if action == "set_speed":
                if observations_per_second is None:
                    raise ReplayControlError("observations_per_second é obrigatório para set_speed")
                session.set_speed(observations_per_second)
                if session.status == ReplayStatus.RUNNING:
                    self._schedule(replay_id)
                return ()
            raise ReplayControlError(f"ação de replay desconhecida: {action}")
