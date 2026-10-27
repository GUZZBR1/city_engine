"""Adapters from external traffic files into the canonical contract."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from .models import DatasetManifest, ProvenanceKind, SupportingArtifact, TrafficObservation


DATASET_ID = "kaggle:rauffauzanrambe/smart-city-traffic-flow-prediction-dataset"
DATASET_URL = "https://www.kaggle.com/datasets/rauffauzanrambe/smart-city-traffic-flow-prediction-dataset"
TRAFFIC_FILE = "traffic_sensor_data.csv"
VIC_TIRTL_DATASET_ID = "vic:tirtl:traffic-counts-and-classification"
VIC_TIRTL_SOURCE_URL = "https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts"
_SPEED_BIN = re.compile(r"^(?P<lower>\d+)km/hr to < (?P<upper>\d+)km/hr$")
_OPEN_SPEED_BIN = re.compile(r"^(?P<lower>\d+)km/hr \+$")

REQUIRED_COLUMNS = (
    "timestamp",
    "sensor_id",
    "location",
    "direction",
    "vehicle_count",
    "average_speed_kmh",
    "occupancy_rate",
    "congestion_level",
    "car_count",
    "motorcycle_count",
    "truck_count",
    "bus_count",
    "day_of_week",
    "is_holiday",
    "hour",
)


class DatasetSourceError(ValueError):
    """A source file is unavailable or does not meet the adapter contract."""


class UnsupportedSourceFilter(ValueError):
    """The source cannot safely support a requested filter."""


class ObservationSource(Protocol):
    manifest: DatasetManifest
    supports_region_filter: bool
    timestamp_timezone: str

    def iter_observations(self) -> Iterator[TrafficObservation]: ...


class SmartCityTrafficCsvAdapter:
    """Read the Kaggle traffic sensor CSV without treating it as observed city data."""

    supports_region_filter = False
    timestamp_timezone = "naive"

    def __init__(
        self,
        path: str | Path,
        *,
        sensor_locations_path: str | Path | None = None,
        config_path: str | Path | None = None,
    ):
        self.path = Path(path)
        if not self.path.is_file():
            raise DatasetSourceError(f"Arquivo de tráfego não encontrado: {self.path}")
        self.sensor_locations_path = Path(sensor_locations_path) if sensor_locations_path else self.path.with_name("sensor_locations.json")
        self.config_path = Path(config_path) if config_path else self.path.with_name("traffic_prediction_config.json")
        self._supporting_artifacts = self._supporting_artifact_hashes()
        self._sensor_metadata = self._load_sensor_metadata()
        self._declared_interval_minutes = self._load_declared_interval()
        if self._supporting_artifact_hashes() != self._supporting_artifacts:
            raise DatasetSourceError("Um sidecar mudou durante a criação do manifesto; tente novamente.")
        self._source_ordered: bool | None = None
        self.manifest = DatasetManifest(
            dataset_id=DATASET_ID,
            source_uri=DATASET_URL,
            artifact=TRAFFIC_FILE,
            artifact_sha256=self._sha256(),
            supporting_artifacts=tuple(
                SupportingArtifact(artifact=name, sha256=sha256)
                for name, sha256 in self._supporting_artifacts
            ),
            declared_license="Apache-2.0",
            license_status="declared_unverified",
            provenance_kind=ProvenanceKind.SIMULATED,
            provenance_note=(
                "O publicador descreve os dados como simulados/real-world-inspired; "
                "não fornece origem observacional rastreável por registro."
            ),
            limitations=(
                "Não usar como observação empírica nem calibrar/validar SUMO.",
                "A unidade/janela de vehicle_count não é estabelecida por evidência independente.",
                "Associação espacial sensor→segmento falhou na auditoria; coordenadas não são mapeadas.",
            ),
        )
        self._validate_header()

    def _sha256(self) -> str:
        return self._file_sha256(self.path, "CSV")

    @staticmethod
    def _file_sha256(path: Path, label: str) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise DatasetSourceError(f"Não foi possível calcular checksum do {label} local.") from exc
        return digest.hexdigest()

    def _supporting_artifact_hashes(self) -> tuple[tuple[str, str], ...]:
        artifacts = []
        for path in (self.sensor_locations_path, self.config_path):
            if path.is_file():
                artifacts.append((path.name, self._file_sha256(path, "sidecar")))
        return tuple(sorted(artifacts))

    def _load_sensor_metadata(self) -> dict[str, dict[str, object]]:
        if not self.sensor_locations_path.is_file():
            return {}
        try:
            payload = json.loads(self.sensor_locations_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise DatasetSourceError("sensor_locations.json deve ter um objeto na raiz.")
            sensors = payload.get("sensors", [])
            if not isinstance(sensors, list):
                raise DatasetSourceError("sensor_locations.json deve conter uma lista em 'sensors'.")
            if any(not isinstance(item, dict) or not isinstance(item.get("sensor_id"), str) for item in sensors):
                raise DatasetSourceError("sensor_locations.json contém objeto de sensor inválido.")
            indexed = {item["sensor_id"]: item for item in sensors}
            if len(indexed) != len(sensors):
                raise DatasetSourceError("sensor_locations.json contém sensor_id duplicado.")
            return indexed
        except (OSError, UnicodeError) as exc:
            raise DatasetSourceError("Não foi possível ler sensor_locations.json.") from exc
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise DatasetSourceError(f"sensor_locations.json inválido: {exc}") from exc

    def _load_declared_interval(self) -> int | None:
        if not self.config_path.is_file():
            return None
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            text = payload["data_sources"]["primary"]["update_frequency"]
            number, unit, *_ = str(text).split()
            if unit.lower().startswith("min"):
                return int(number)
            if unit.lower().startswith("hour"):
                return int(float(number) * 60)
            return None
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def _read_rows(self) -> Iterator[tuple[int, dict[str, str]]]:
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None:
                    raise DatasetSourceError("CSV sem cabeçalho.")
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise DatasetSourceError("CSV contém nomes de coluna duplicados.")
                missing = sorted(set(REQUIRED_COLUMNS) - set(reader.fieldnames))
                unexpected = sorted(set(reader.fieldnames) - set(REQUIRED_COLUMNS))
                if missing or unexpected:
                    details = []
                    if missing:
                        details.append(f"ausentes: {', '.join(missing)}")
                    if unexpected:
                        details.append(f"inesperadas: {', '.join(unexpected)}")
                    raise DatasetSourceError(f"Cabeçalho fora do schema: {'; '.join(details)}.")
                for line_number, row in enumerate(reader, start=2):
                    if None in row:
                        raise DatasetSourceError(f"Colunas inesperadas na linha {line_number}.")
                    if any(value is None or not value.strip() for value in row.values()):
                        raise DatasetSourceError(f"Campo vazio na linha {line_number}.")
                    yield line_number, row
        except (OSError, UnicodeError) as exc:
            raise DatasetSourceError("Não foi possível ler o CSV local; verifique a codificação UTF-8.") from exc

    def _validate_header(self) -> None:
        try:
            next(self._read_rows(), None)
        except DatasetSourceError:
            raise

    def _parse_timestamp(self, value: str, line_number: int) -> datetime:
        try:
            timestamp = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise DatasetSourceError(f"Timestamp inválido na linha {line_number}: {value!r}.") from exc
        if timestamp.tzinfo is not None:
            raise DatasetSourceError(
                f"Timezone inesperado na linha {line_number}; versão auditada usa timestamps sem fuso."
            )
        return timestamp

    def _rows_in_timestamp_order(self) -> Iterator[tuple[int, dict[str, str], datetime]]:
        """Stream already ordered files; sort only if the source ordering is broken."""
        if self._source_ordered is None:
            previous: tuple[datetime, str] | None = None
            self._source_ordered = True
            for line_number, row in self._read_rows():
                key = (self._parse_timestamp(row.get("timestamp", ""), line_number), row.get("sensor_id", ""))
                if previous is not None and key < previous:
                    self._source_ordered = False
                    break
                previous = key

        if self._source_ordered:
            for line_number, row in self._read_rows():
                yield line_number, row, self._parse_timestamp(row.get("timestamp", ""), line_number)
            return

        buffered = [
            (line_number, row, self._parse_timestamp(row.get("timestamp", ""), line_number))
            for line_number, row in self._read_rows()
        ]
        buffered.sort(key=lambda item: (item[2], item[1].get("sensor_id", ""), item[0]))
        yield from buffered

    def iter_observations(self) -> Iterator[TrafficObservation]:
        if self._sha256() != self.manifest.artifact_sha256:
            raise DatasetSourceError("O CSV mudou depois da criação do manifesto; crie um novo replay.")
        if self._supporting_artifact_hashes() != self._supporting_artifacts:
            raise DatasetSourceError("Um sidecar mudou depois da criação do manifesto; crie um novo replay.")
        for line_number, row, timestamp in self._rows_in_timestamp_order():
            try:
                sensor_id = row["sensor_id"].strip()
                if not sensor_id:
                    raise ValueError("sensor_id vazio")
                vehicle_count = int(row["vehicle_count"])
                speed = float(row["average_speed_kmh"])
                occupancy = float(row["occupancy_rate"])
                class_counts = {
                    "car_count": int(row["car_count"]),
                    "motorcycle_count": int(row["motorcycle_count"]),
                    "truck_count": int(row["truck_count"]),
                    "bus_count": int(row["bus_count"]),
                }
                day_of_week = int(row["day_of_week"])
                is_holiday = int(row["is_holiday"])
                hour = int(row["hour"])
                if vehicle_count < 0 or any(count < 0 for count in class_counts.values()):
                    raise ValueError("contagens devem ser inteiros não negativos")
                if not math.isfinite(speed) or speed < 0:
                    raise ValueError("average_speed_kmh deve ser finito e não negativo")
                if not math.isfinite(occupancy) or not 0 <= occupancy <= 1:
                    raise ValueError("occupancy_rate deve estar entre 0 e 1")
                if not 0 <= day_of_week <= 6:
                    raise ValueError("day_of_week deve estar entre 0 e 6")
                if is_holiday not in (0, 1):
                    raise ValueError("is_holiday deve ser 0 ou 1")
                if not 0 <= hour <= 23:
                    raise ValueError("hour deve estar entre 0 e 23")
                congestion_level = row["congestion_level"].strip()
                if congestion_level not in {"Low", "Medium", "High", "Critical"}:
                    raise ValueError(f"congestion_level inválido: {congestion_level!r}")
                quality_flags = []
                if vehicle_count != sum(class_counts.values()):
                    quality_flags.append("vehicle_count_subtype_sum_mismatch")
                sensor = self._sensor_metadata.get(sensor_id, {})
                coordinates = sensor.get("coordinates", {}) if isinstance(sensor, dict) else {}
                coordinates = coordinates if isinstance(coordinates, dict) else {}
                yield TrafficObservation(
                    observation_id=f"{DATASET_ID}:{sensor_id}:{timestamp.isoformat()}",
                    timestamp=timestamp,
                    source_id=sensor_id,
                    dataset_id=DATASET_ID,
                    location_id=sensor_id,
                    vehicle_count=vehicle_count,
                    mean_speed_kmh=speed,
                    congestion_level=congestion_level,
                    provenance_kind=ProvenanceKind.SIMULATED,
                    metadata={
                        "source_location_label": row["location"],
                        "source_direction": row["direction"],
                        "source_occupancy_rate": occupancy,
                        "source_vehicle_type_counts": class_counts,
                        "source_day_of_week": day_of_week,
                        "source_is_holiday": bool(is_holiday),
                        "source_hour": hour,
                        "declared_sampling_interval_minutes": self._declared_interval_minutes,
                        "timestamp_timezone": "unspecified; source timestamps are naive",
                        "spatial_mapping_status": "unverified; coordinates and road IDs withheld",
                        "reported_coordinates": {
                            "latitude": coordinates.get("latitude"),
                            "longitude": coordinates.get("longitude"),
                            "source_coordinate_system": "WGS84 (publisher-declared)" if coordinates else None,
                        },
                        "reported_road_segment_id": sensor.get("road_segment_id") if isinstance(sensor, dict) else None,
                        "reported_district": sensor.get("district") if isinstance(sensor, dict) else None,
                        "reported_sensor_sampling_rate_seconds": sensor.get("sampling_rate_seconds") if isinstance(sensor, dict) else None,
                        "data_quality_flags": quality_flags,
                    },
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DatasetSourceError(f"Valor inválido na linha {line_number}: {exc}") from exc


class VictoriaTirtlZipAdapter:
    """Adapt official Victorian TIRTL interval aggregates without inventing missing bins."""

    supports_region_filter = False
    timestamp_timezone = "naive"

    def __init__(self, archive_path: str | Path, sites_path: str | Path, *, site_ids: set[int]):
        if not site_ids:
            raise DatasetSourceError("Informe ao menos um site TIRTL para limitar o piloto.")
        self.archive_path = Path(archive_path)
        self.sites_path = Path(sites_path)
        if not self.archive_path.is_file() or not self.sites_path.is_file():
            raise DatasetSourceError("Arquivo oficial TIRTL ou tabela de sites indisponível.")
        self.site_ids = frozenset(site_ids)
        sites_hash = self._sha256(self.sites_path)
        self._site_metadata = self._load_sites()
        if self._sha256(self.sites_path) != sites_hash:
            raise DatasetSourceError("A tabela TIRTL Sites mudou durante a criação do manifesto; tente novamente.")
        unknown = self.site_ids - self._site_metadata.keys()
        if unknown:
            raise DatasetSourceError(f"Site(s) TIRTL ausente(s) na tabela oficial: {sorted(unknown)}")
        archive_hash = self._sha256(self.archive_path)
        self.manifest = DatasetManifest(
            dataset_id=VIC_TIRTL_DATASET_ID,
            source_uri=VIC_TIRTL_SOURCE_URL,
            artifact=self.archive_path.name,
            artifact_sha256=archive_hash,
            supporting_artifacts=(SupportingArtifact(artifact=self.sites_path.name, sha256=sites_hash),),
            declared_license="CC BY 4.0",
            license_status="verified",
            provenance_kind=ProvenanceKind.OBSERVED,
            provenance_note=(
                "Contagens agregadas por sensores TIRTL oficiais do Department of Transport and Planning, Victoria; "
                "velocidade média é derivada de bins de 5 km/h e o bin aberto usa seu limite inferior."
            ),
            limitations=(
                "A fonte alerta para erro de classificação em alto fluxo e indisponibilidade/desativação por site.",
                "Ausência de linha/intervalo não é convertida em zero: pode significar zero ou falta de dado.",
                "Direção e geometria de via não identificam faixa; mapear para SUMO requer associação explícita e revisada.",
                "Classes 13 (erro de classificação) e 14 (bicicletas) são preservadas na contagem agregada.",
                "O timezone dos campos date/time_bin não é especificado pelo dicionário consultado.",
            ),
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise DatasetSourceError("Não foi possível calcular checksum de artefato TIRTL.") from exc
        return digest.hexdigest()

    def _load_sites(self) -> dict[int, dict[str, object]]:
        result: dict[int, dict[str, object]] = {}
        try:
            with self.sites_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != ["site", "site_description", "latitude", "longitude"]:
                    raise DatasetSourceError("Cabeçalho da tabela oficial TIRTL Sites inesperado.")
                for line_number, row in enumerate(reader, start=2):
                    site = int(row["site"])
                    latitude, longitude = float(row["latitude"]), float(row["longitude"])
                    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                        raise ValueError("coordenadas fora dos limites")
                    if site in result:
                        raise ValueError(f"site duplicado: {site}")
                    result[site] = {
                        "description": row["site_description"],
                        "latitude": latitude,
                        "longitude": longitude,
                    }
        except (OSError, UnicodeError, csv.Error, TypeError, ValueError) as exc:
            raise DatasetSourceError(f"Tabela oficial TIRTL Sites inválida na linha {line_number if 'line_number' in locals() else 1}.") from exc
        return result

    @staticmethod
    def _speed_bin(value: str) -> tuple[float, bool]:
        match = _SPEED_BIN.fullmatch(value.strip())
        if match:
            lower, upper = int(match.group("lower")), int(match.group("upper"))
            if upper != lower + 5:
                raise ValueError(f"bin de velocidade não tem largura de 5 km/h: {value!r}")
            return (lower + upper) / 2, False
        match = _OPEN_SPEED_BIN.fullmatch(value.strip())
        if match:
            return float(match.group("lower")), True
        raise ValueError(f"bin de velocidade desconhecido: {value!r}")

    def _verify_manifest_inputs(self) -> None:
        if self._sha256(self.archive_path) != self.manifest.artifact_sha256:
            raise DatasetSourceError("O arquivo ZIP TIRTL mudou depois da criação do manifesto.")
        if self._sha256(self.sites_path) != self.manifest.supporting_artifacts[0].sha256:
            raise DatasetSourceError("A tabela TIRTL Sites mudou depois da criação do manifesto.")

    def iter_observations(self) -> Iterator[TrafficObservation]:
        self._verify_manifest_inputs()
        try:
            with zipfile.ZipFile(self.archive_path) as archive:
                names = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
                if not names:
                    raise DatasetSourceError("Arquivo ZIP TIRTL não contém CSV diário.")
                for name in names:
                    grouped: dict[tuple[datetime, int, str], dict[str, object]] = {}
                    with archive.open(name) as binary:
                        text = (line.decode("utf-8-sig") for line in binary)
                        reader = csv.DictReader(text)
                        if reader.fieldnames != [
                            "date", "time_bin", "site", "heading", "vehicle_class", "speed_bin", "volume"
                        ]:
                            raise DatasetSourceError(f"Cabeçalho TIRTL inesperado em {name}.")
                        for line_number, row in enumerate(reader, start=2):
                            try:
                                site = int(row["site"])
                                if site not in self.site_ids:
                                    continue
                                time_value = row["time_bin"]
                                interval_time = (
                                    datetime.strptime(time_value, "%H:%M:%S").time()
                                    if len(time_value.split(":")[-1]) == 2 and time_value.count(":") == 2
                                    else datetime.strptime(time_value, "%H:%M").time()
                                )
                                observed_at = datetime.combine(
                                    date.fromisoformat(row["date"]), interval_time
                                )
                                heading = row["heading"].strip().upper()
                                if heading not in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}:
                                    raise ValueError(f"heading inválido: {heading!r}")
                                vehicle_class = int(row["vehicle_class"])
                                if not 0 <= vehicle_class <= 14:
                                    raise ValueError(f"vehicle_class inválida: {vehicle_class}")
                                volume = int(row["volume"])
                                if volume < 0:
                                    raise ValueError("volume negativo")
                                speed, open_bin = self._speed_bin(row["speed_bin"])
                                key = (observed_at, site, heading)
                                group = grouped.setdefault(key, {
                                    "volume": 0,
                                    "speed_weighted_sum": 0.0,
                                    "speed_volume": 0,
                                    "class_counts": {},
                                    "has_open_speed_bin": False,
                                })
                                group["volume"] += volume
                                group["speed_weighted_sum"] += speed * volume
                                group["speed_volume"] += volume
                                group["has_open_speed_bin"] = group["has_open_speed_bin"] or open_bin
                                class_counts = group["class_counts"]
                                class_counts[str(vehicle_class)] = class_counts.get(str(vehicle_class), 0) + volume
                            except (KeyError, TypeError, ValueError) as exc:
                                raise DatasetSourceError(f"Registro TIRTL inválido em {name}:{line_number}: {exc}") from exc
                    for (observed_at, site, heading), group in sorted(grouped.items()):
                        location = self._site_metadata[site]
                        count = int(group["volume"])
                        class_counts = group["class_counts"]
                        flags = []
                        if group["has_open_speed_bin"]:
                            flags.append("speed_mean_is_lower_bound_for_open_top_bin")
                        if class_counts.get("13", 0):
                            flags.append("contains_tirtl_classification_errors")
                        if class_counts.get("14", 0):
                            flags.append("contains_bicycle_counts")
                        yield TrafficObservation(
                            observation_id=f"{VIC_TIRTL_DATASET_ID}:{site}:{observed_at.isoformat()}:{heading}",
                            timestamp=observed_at,
                            source_id=f"vic:tirtl:site:{site}",
                            dataset_id=VIC_TIRTL_DATASET_ID,
                            location_id=f"tirtl-site:{site}",
                            latitude=float(location["latitude"]),
                            longitude=float(location["longitude"]),
                            vehicle_count=count,
                            flow_veh_h=count * 4.0,
                            mean_speed_kmh=(
                                float(group["speed_weighted_sum"]) / int(group["speed_volume"])
                                if int(group["speed_volume"]) else None
                            ),
                            provenance_kind=ProvenanceKind.OBSERVED,
                            metadata={
                                "site_description": location["description"],
                                "heading": heading,
                                "series_id": f"tirtl-site:{site}:heading:{heading}",
                                "source_interval_minutes": 15,
                                "timestamp_timezone": "not specified by source",
                                "source_vehicle_class_counts": class_counts,
                                "derived_fields": ["flow_veh_h", "mean_speed_kmh"],
                                "speed_bin_statistic": "volume_weighted bin midpoint; open-ended bin uses lower bound",
                                "spatial_mapping_status": "source coordinates; road segment and lane not mapped",
                                "spatial_reference": "not specified by the source",
                                "data_quality_flags": flags,
                            },
                        )
        except DatasetSourceError:
            raise
        except (OSError, UnicodeError, zipfile.BadZipFile, csv.Error) as exc:
            raise DatasetSourceError("Não foi possível ler os artefatos oficiais TIRTL.") from exc
