"""Frozen experiment configuration and the materialized Aurora synthetic profile."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, model_validator

from .city import GENERATOR_VERSION
from .models import CityConfigFile, CitySnapshot, StrictModel
from .state import canonical_hash


class ExperimentManifest(StrictModel):
    """Versioned inputs fixed before an experiment starts."""

    experiment_id: str
    schema_version: str = "1.0"
    profile_id: str
    profile_version: str
    parameter_version: str
    horizon_rounds: int = Field(ge=1, le=10)
    snapshot_id: str
    snapshot_hash: str
    generator_version: str
    transition_version: str = "1.0"
    parameters: AuroraSyntheticV1Parameters
    seeds: dict[str, int]
    catalog_version: str
    rules_version: str
    provenance: str = "synthetic_config"

    @model_validator(mode="after")
    def validate_manifest(self) -> ExperimentManifest:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id não pode ser vazio")
        if not self.profile_id.strip() or not self.profile_version.strip():
            raise ValueError("perfil e versão do perfil são obrigatórios")
        if not self.parameter_version.strip():
            raise ValueError("versão dos parâmetros é obrigatória")
        if not self.seeds or any(seed < 0 for seed in self.seeds.values()):
            raise ValueError("sementes não negativas são obrigatórias")
        return self

    @property
    def manifest_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class DemographyParameters(StrictModel):
    birth_rate: float = Field(ge=0, le=1)
    death_rate: float = Field(ge=0, le=1)
    net_migration_rate: float
    urban_net_migration_share: float = Field(ge=0, le=1)
    household_size: float = Field(gt=0)


class HousingParameters(StrictModel):
    vacancy_rate_target: float = Field(ge=0, lt=1)
    annual_capacity_rate: float = Field(ge=0)
    annual_retirement_rate: float = Field(ge=0, le=1)
    initial_units: int | None = Field(default=None, ge=0)
    initial_units_method: str
    district_allocation_method: Literal[
        "proportional_to_existing_stock_largest_remainder"
    ] = Field(
        description=(
            "Regra contábil versionada para distribuir totais agregados; não prevê "
            "em quais distritos ocorre construção ou retirada."
        )
    )


class EmploymentParameters(StrictModel):
    annual_growth_rate: float = Field(ge=-1)
    district_allocation: dict[str, float]

    @model_validator(mode="after")
    def validate_allocation(self) -> EmploymentParameters:
        if not self.district_allocation or any(value < 0 for value in self.district_allocation.values()):
            raise ValueError("district_allocation deve conter quotas não negativas")
        if round(sum(self.district_allocation.values()), 12) != 1:
            raise ValueError("district_allocation deve somar 1")
        return self


class SchoolParameters(StrictModel):
    eligible_share: float = Field(ge=0, le=1)
    initial_seats_per_resident: float = Field(ge=0)


class HealthParameters(StrictModel):
    annual_visits_per_resident: float = Field(ge=0)
    initial_visits_per_resident_year: float = Field(ge=0)


class ServiceParameters(StrictModel):
    school: SchoolParameters
    health: HealthParameters


class GreenParameters(StrictModel):
    public_area_m2_per_resident: dict[str, float]

    @model_validator(mode="after")
    def validate_areas(self) -> GreenParameters:
        if not self.public_area_m2_per_resident or any(value < 0 for value in self.public_area_m2_per_resident.values()):
            raise ValueError("public_area_m2_per_resident deve conter áreas não negativas")
        return self


class EmissionsParameters(StrictModel):
    annual_vehicle_km_per_resident: float = Field(ge=0)
    co2e_kg_per_vehicle_km: float = Field(ge=0)
    activity_scope: str


class AuroraSyntheticV1Parameters(StrictModel):
    """Fully materialized, strict parameter schema for profile v1."""

    demography: DemographyParameters
    housing: HousingParameters
    employment: EmploymentParameters
    services: ServiceParameters
    green: GreenParameters
    emissions: EmissionsParameters

    @model_validator(mode="after")
    def validate_finite_values(self) -> AuroraSyntheticV1Parameters:
        def visit(value: object, path: str) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"parâmetro {path} deve ser finito")
            if isinstance(value, dict):
                for key, nested in value.items():
                    visit(nested, f"{path}.{key}")
            elif isinstance(value, (list, tuple)):
                for index, nested in enumerate(value):
                    visit(nested, f"{path}[{index}]")

        visit(self.model_dump(mode="python"), "parameters")
        return self


def build_aurora_synthetic_v1_manifest(
    config: CityConfigFile,
    snapshot: CitySnapshot,
    *,
    experiment_id: str,
    horizon_rounds: int | None = None,
) -> ExperimentManifest:
    """Materialize every v1 profile default, keeping the YAML snapshot unchanged."""
    if snapshot.city_id != config.city.id:
        raise ValueError("snapshot e configuração pertencem a cidades diferentes")
    if snapshot.hash == "" or not experiment_id.strip():
        raise ValueError("snapshot e experiment_id válidos são obrigatórios")

    urban_districts = sorted(
        (district for district in snapshot.districts if district["type"] == "urban"),
        key=lambda district: district["id"],
    )
    urban_jobs = sum(int(district["jobs"]) for district in urban_districts)
    if urban_jobs <= 0:
        raise ValueError("não é possível materializar quotas distritais sem empregos urbanos")
    employment_allocation = {
        district["id"]: int(district["jobs"]) / urban_jobs for district in urban_districts
    }
    params: dict[str, Any] = {
        "demography": {
            "birth_rate": 0.012,
            "death_rate": 0.008,
            "net_migration_rate": 0.002,
            "urban_net_migration_share": 0.80,
            "household_size": float(snapshot.household["mean_residents_per_occupied_household"]),
        },
        "housing": {
            "vacancy_rate_target": 0.05,
            "annual_capacity_rate": 0.02,
            "annual_retirement_rate": 0.003,
            "initial_units": None,
            "initial_units_method": "ceil(round_half_up(urban_residents / household_size) / (1 - vacancy_rate_target))",
            "district_allocation_method": "proportional_to_existing_stock_largest_remainder",
        },
        "employment": {
            "annual_growth_rate": 0.01,
            "district_allocation": employment_allocation,
        },
        "services": {
            "school": {"eligible_share": 0.18, "initial_seats_per_resident": 0.16},
            "health": {"annual_visits_per_resident": 2.4, "initial_visits_per_resident_year": 2.0},
        },
        "green": {
            "public_area_m2_per_resident": {
                "centro": 2.0,
                "norte_residencial": 4.0,
                "sul_misto": 3.0,
                "leste_logistico": 1.0,
                "oeste_verde": 8.0,
            },
        },
        "emissions": {
            "annual_vehicle_km_per_resident": 2500.0,
            "co2e_kg_per_vehicle_km": 0.18,
            "activity_scope": "exogenous_urban_resident_vehicle_km_per_year",
        },
    }
    return ExperimentManifest(
        experiment_id=experiment_id,
        profile_id="aurora_synthetic_v1",
        profile_version="1.0",
        parameter_version="aurora-synthetic-transition-parameters-v1",
        horizon_rounds=config.arena.default_horizon_rounds if horizon_rounds is None else horizon_rounds,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.hash,
        generator_version=GENERATOR_VERSION,
        transition_version="1.0",
        parameters=params,
        seeds={"mobility_demand": config.mobility.demand.seed},
        catalog_version="indicator-catalog-v1",
        rules_version="urban-evolution-rules-v1",
    )
