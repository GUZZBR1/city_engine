# Urban Arena city core

This package loads and validates `configs/cities/aurora-base-v1.yaml`, generates
its deterministic MVP 0 snapshot, and creates isolated agent copies:

```python
from urban_arena import create_agent_copies, generate_snapshot, load_city_config

config = load_city_config()
snapshot = generate_snapshot(config)
copies = create_agent_copies(snapshot, config)
```

The snapshot contract uses `LocalFeatureCollection` in the
`synthetic_local_cartesian_m` coordinate space. It is a local metric schema,
not GeoJSON RFC 7946 and not latitude/longitude. Every generated feature is
marked `synthetic=true` with `provenance_kind=synthetic_generated`.

## Deterministic geometry rule

The YAML fixes the footprint size, 5×5 intersection count, north-south barrier,
and crossing types, but does not fix exact district boundaries or road geometry.
The generator divides the 6×6 km square into five non-overlapping rectangular
urban districts: west/east full-height strips, a central square, and north/south
central strips. The rural catchment remains an external zone; its point feature
marks the south gateway and does not claim an area inside the urban footprint.

Road nodes are evenly spaced along the square bounds. The north-south barrier
runs through the middle of a central grid cell. Only the two horizontal links
listed in the configuration cross it; other candidate links are omitted. Each
undirected connection is represented as two directed edges, yielding 74 edges
for this 5×5 grid and two crossings. These are explicit MVP geometry choices,
not observed roads.

## Synthetic traffic parameters

Road class profiles in `configs/cities/aurora-base-v1.yaml` supply synthetic
speed limits, lane counts, and total capacity per directed edge. Generated edge
features carry those resolved values and explicit units. The two barrier
crossings remain two physical connections represented by four directed edges.
Configured signal programs use grid-axis movement groups with initial phase,
offset, and phase durations; their timing is a benchmark hypothesis, not an
observed or calibrated plan.

Demand is a fixed synthetic rate for each OD pair and simulation window, in
`vehicles/hour`. OD endpoints use stable network node IDs. The default seed is
42 and is passed to the downstream simulator for its stochastic behavior; OD
rates themselves are fixed, not sampled. The configuration explicitly does
not derive traffic from resident counts or the national commute mode proxy.

## Public simulation input contract

The package exports `SimulationInput` and `build_simulation_input`. The
contract is versioned (`contract_version: "1.0"`), validated, and serializable
with Pydantic's `model_dump(mode="json")`. It includes the snapshot identity,
seed, selected window duration, metric node coordinates, directed road
attributes, signal timings, and window-scoped OD flows. The engine can consume
the serialized object without importing generator helpers or private package
modules:

```python
from urban_arena import build_simulation_input, load_aurora_snapshot

config, snapshot = load_aurora_snapshot()
engine_input = build_simulation_input(config, snapshot, "weekday_am_peak")
payload = engine_input.model_dump(mode="json")
```

`examples/aurora-weekday-am-peak.json` is a serialized example. The contract
uses meters, km/h, and vehicles/hour, and marks the city provenance as
synthetic. Its values are benchmark assumptions, not observed traffic data.

The SHA-256 hash covers the normalized snapshot payload, schema and generator
versions, with object keys sorted and geometry features sorted by stable ID.
It excludes the hash and `snapshot_id` fields themselves. Adding explicit
traffic configuration changes the hash deterministically. Agent copies are
deep copies whose initial hash remains the source snapshot hash.

## Signal policy benchmark

`FixedSignalTimingPolicy` emits deterministic, versioned signal timing
proposals for exercising arbitration and an injected mobility evaluator. These
fixed rules are synthetic benchmark strategies, not trained AI policies. The
default action catalog keeps signal, housing, and service actions unavailable.
A caller must supply a catalog, valid signal targets, and an executor before a
proposal can be applied. Executor evidence is recorded on the round record,
separate from `CityState` and annual indicators.
