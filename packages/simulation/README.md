# Simulation engine

`simulation` is a Python package with a simulator-neutral `SimulationEngine`
protocol, a strict input/result contract, a deterministic SUMO command-line
adapter, and a pure compiler to SUMO plain XML plus routes. It has no FastAPI
dependency. The API call surface is:

```python
from simulation import run_simulation

result = run_simulation(city_id="aurora-base-v1", window_id="weekday_am_peak", seed=42)
```

Callers can pass an explicit `SimulationInput` and `SimulationLimits` for
testing, other engines, or alternate artifact directories. The default call
loads the snapshot using the public `urban_arena.load_aurora_snapshot()` API.
It does not create road parameters or demand.

## Paired signal-timing scenarios

`SignalTimingIntervention` is a declarative, immutable override for the ordered
phase movements at one existing signal. `apply_signal_timing_intervention()`
rejects unknown nodes, missing controllers, a phase count/order that differs
from north-south / all-red / east-west / all-red, non-positive durations, or a
cycle total different from the base plan. It returns a new `SimulationInput`
and changes only those phase durations; the YAML and all other controller
parameters remain untouched. For Aurora's demonstration intervention:

```python
from simulation import SignalTimingIntervention, SignalTimingPhase, run_simulation

intervention = SignalTimingIntervention(
    node_id="node:02:04",
    phases=(
        SignalTimingPhase(movement="north_south", duration_seconds=40),
        SignalTimingPhase(movement="all_red", duration_seconds=3),
        SignalTimingPhase(movement="east_west", duration_seconds=20),
        SignalTimingPhase(movement="all_red", duration_seconds=3),
    ),
)
result = run_simulation(signal_timing_intervention=intervention, seed=42)
```

For a paired comparison, load one `SimulationInput`, then pass the same input,
seed and `SimulationLimits` to both runs; pass the intervention only to the
second. The resulting SUMO `.net.xml` changes only the target controller's
phase durations. SUMO documents phase order and the `duration`/`state` fields
in [Traffic Lights](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html)
and [Traffic Light Programs](https://sumo.dlr.de/docs/Networks/SUMO_Road_Networks.html#traffic_light_programs).

## Contract status and reproducibility

`load_aurora_input()` uses the public `urban_arena.build_simulation_input()`
contract. It converts configured road speeds from km/h to m/s and expands each
fixed OD flow into `round(rate × window duration / 3600)` vehicle trips, spaced
evenly within that window. This is a deterministic benchmark conversion of
synthetic hourly rates, not observed individual trips. Configured YAML signal
plans are compiled into the network. Only configured signal nodes are marked
as SUMO traffic lights. After `netconvert` builds the base network, the adapter
maps its actual controlled connection indices to the north-south/east-west
axis using incoming road geometry, writes a static `<tlLogic>` per configured
node, rotates phases to the configured initial phase index, and preserves
configured durations and offset. Before SUMO starts, it validates that every
controller exists in `.net.xml`, has controlled links, and each phase state has
one character per link. Public city node/edge IDs are encoded to SUMO-safe IDs
in generated artifacts because the source IDs contain reserved separators;
the public contract remains unchanged. Aurora and all its inputs remain
synthetic benchmark data.

## Metrics

- Requested trips: count of vehicles expanded from synthetic hourly OD rates,
  rounded over the window and evenly spaced by the adapter.
- Completed trips: count of SUMO TripInfo arrival records through the end of
  the drain period. Vehicles that finish during drain count as completed.
- Not completed: requested trips without an arrival by the end of drain;
  `trips_completed + trips_not_completed` always equals `trips_requested`.
- Mean travel time: arithmetic mean of `tripinfo.duration` for completed
  vehicles through the end of drain; `null` when no vehicle completes.
- Mean speed: distance-weighted speed, total `routeLength` / total `duration`,
  for vehicles completed through the end of drain, converted to km/h; `null`
  if no trip completes or total time is zero.
- Mean queue length: mean across SUMO queue-output timesteps of the sum of
  lane `queueing_length` during the demand window only, in meters. SUMO's
  default queued-vehicle threshold is 1.39 m/s. It is a length in meters, not
  a vehicle count.

The result records input IDs/versions/hash, seed, SUMO version, metric methods,
warnings, and artifact file paths. Same inputs, seed, SUMO version and runtime
configuration are reproducible; cross-platform identity is not promised.
`SimulationLimits.drain_limit_seconds` configures the maximum additional
simulation period after the demand window; its default is 3,600 seconds and it
can be set to zero. No trips depart during this period: SUMO runs only the
already compiled demand. If vehicles remain when the limit expires, they are
reported in `trips_not_completed` and a warning is returned. `wall_timeout_seconds`,
`max_window_seconds` and `max_requested_trips` also bound execution and input
size. The CLI process is terminated by the subprocess timeout. There is no
distributed queue or persistent job state.

Each selected window runs on its own relative simulation clock from 0 through
the demand duration plus the drain limit. Trip departure times are offsets from
the window start and remain within the demand window; the human-readable start
clock identifies the demand period only. The mean queue metric excludes drain
samples to preserve its existing demand-window meaning.

## Environment

Install the official SUMO Python application package into the same local
environment that runs the API. It provides both `sumo` and `netconvert` without
changing a system-wide installation:

```bash
uv pip install --python .venv/bin/python eclipse-sumo
sumo --version
netconvert --version
```

Or run the SUMO tools in the official container image. The adapter expects
local executable commands, so container users can mount a prepared artifact
directory and run the same emitted `netconvert` and `sumo` commands inside the
container (image versions are available at `ghcr.io/eclipse-sumo/sumo`, for
example `v1_26_0`):

```bash
docker pull ghcr.io/eclipse-sumo/sumo:v1_26_0
docker run --rm -v "$PWD:/workspace" -w /workspace \
  ghcr.io/eclipse-sumo/sumo:v1_26_0 sumo --version
```

The Python package itself installs without SUMO; calling the engine then
returns `sumo_unavailable` with the missing executable names.

## Install and direct invocation

From the repository root, after the upstream package is installed:

```bash
uv pip install --python .venv/bin/python -e ./packages/simulation
.venv/bin/python -c 'from simulation import run_simulation; print(run_simulation(seed=42).model_dump_json(indent=2))'
```

`compile_sumo_inputs()` is pure and writes `aurora.nod.xml`, `aurora.edg.xml`,
and `aurora.rou.xml` into a caller-selected directory. `SumoEngine` invokes
`netconvert` with `--tls.guess-signals` to generate controlled links for YAML
traffic-light nodes, then writes and verifies controller programs in the
compiled `.net.xml`. SUMO runs with fixed `--seed`, the window start/end,
TripInfo and queue output. It never enables `--random`. Each phase gives green
to connections aligned with its configured axis; this is a synthetic fixed-
time benchmark plan, not a conflict-reviewed or calibrated traffic plan. See
https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html.

## Annual-engine integration boundary

The annual engine may request mobility only for a configured simulation window.
Its caller must provide the window-specific `SimulationInput` and pass the same
`inputs.window.id` as `window_id` to `run_simulation()`. An optional approved
signal change uses the existing `SignalTimingIntervention` argument. The package
returns the existing `SimulationResult`, whose metrics describe that one
window; callers must preserve its window identity and must not scale, repeat,
or otherwise annualize those metrics. The annual transition and annual
indicators remain owned by the annual-engine package.

This checkout does not yet contain the annual round runner or a shared
annual-to-mobility job handoff. The dependency for that integration is for the
runner to invoke this existing Python boundary with its configured-window
input, seed, limits, and optional signal intervention, then retain the returned
window result as window-scoped evidence. No second mobility request or result
schema is introduced here. The API's current HTTP job accepts the configured
Aurora base snapshot and window; it cannot yet enqueue an annual candidate
state or action. That API handoff depends on the annual runner and coordinator
agreeing where to invoke the existing simulation contract.
