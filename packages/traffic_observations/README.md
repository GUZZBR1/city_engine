# Traffic observations

Small, framework-independent package for source manifests, the versioned
`TrafficObservation` contract, dataset adapters, replay controls, and an
in-memory observation store. It does not import FastAPI, SUMO, or Aurora.

## Current adapter

`SmartCityTrafficCsvAdapter` reads `traffic_sensor_data.csv` from the Kaggle
Smart City Traffic Flow Prediction Dataset. This is a **simulated fixture**;
it must not be described as empirical city data or used to calibrate or validate
SUMO. The adapter emits only the source's vehicle count, mean speed, congestion
label, IDs, and provenance. Unknown fields stay `None`; unverified coordinates
and road IDs stay in metadata.

Install it with the API's local environment:

```bash
uv pip install --python .venv/bin/python -e ./packages/traffic_observations
```

The core API is `ObservationSource.iter_observations()`, which yields canonical
observations. `ReplaySession` applies timestamp/location/type filters and
supports pause, resume, reset, step, and playback speed. Geographic filtering
is rejected unless a source declares verified coordinates. The included store
is process-local and replaceable; it is not durable event streaming.

See [`docs/datasets/traffic-observation-mvp.md`](../../docs/datasets/traffic-observation-mvp.md)
for the four-dataset audit, scientific boundaries, replay endpoints, and future
calibration/validation gates.

## Observed-versus-SUMO interval evaluation

`traffic_observations.evaluation` provides a small reusable comparison layer.
It accepts interval rows with a detector ID and/or segment ID, interval start
and end, volume in vehicles per interval, and mean speed in km/h. The observed
and SUMO keys must match exactly on IDs and interval bounds. Duplicates,
unmatched intervals, and empty measurement pairs fail explicitly; gaps are not
filled with zero.

```python
from traffic_observations import evaluate_csv_files, write_evaluation_artifact

report = evaluate_csv_files(
    "confirmed-observed.csv",
    "confirmed-sumo-measurements.csv",
    seed=17,
    sumo_version="1.26.0",
    additional_inputs={
        "network": "confirmed-network.net.xml",
        "mapping": "confirmed-detector-mapping.json",
        "independent_demand": "boundary-demand.json",
        "protocol": "frozen-evaluation-protocol.json",
    },
)
write_evaluation_artifact(report, "evaluation.json")
```

Both CSVs use `detector_id,segment_id,interval_start,interval_end,
volume_vehicles,mean_speed_kmh`; empty IDs or metric cells are blank. Timestamps
must use the same exact interval boundaries and documented timezone convention.
The JSON artifact includes SHA-256 hashes and paths for the two measurement
files and every additional input, the seed, SUMO version, overall metrics,
metrics grouped by detector/segment/window, and per-interval residuals.

For each metric, errors have the sign `simulated - observed`: MAE is the mean
absolute error, RMSE is the square root of mean squared error, and bias is the
mean signed error. GEH is computed for volume only as
`sqrt(2 * (simulated - observed)^2 / (simulated + observed))`; a zero/zero pair
has GEH 0. Speed GEH is not applicable. These are unweighted interval metrics;
the harness does not calibrate, infer demand, select mappings, or run SUMO.
The tests use small artificial rows only to check formulas and serialization;
they are not baseline outputs.

## Baseline status and split protocol

No observed-versus-SUMO baseline has been run and no result artifact is
published. The current checkout has no accepted detector-to-lane mapping, no
West Gate SUMO network, no SUMO detector-output series, and no independently
defined boundary demand. The existing Aurora network/demand are synthetic and
must not be substituted. The mapping audit leaves site 504 unresolved and site
505 a candidate only. Both sites are restricted to descriptive profiling of
their source observations; neither may be compared with SUMO or a candidate
edge.

When those prerequisites exist, pre-register one contiguous calibration period
and a later, untouched held-out period before examining interval outcomes.
Where coverage allows, reserve a separate corridor/segment group as an
additional spatial holdout. Assign partitions from timestamps, stable segment
IDs, and coverage metadata only. Do not inspect observed-versus-simulated
residuals, score candidate splits, or fit parameters while choosing boundaries.
Freeze the split, mapping version, measurement policy, demand definition,
parameter bounds, seeds, and SUMO/network hashes in the experiment manifest.
Calibrate on the calibration partition only; run the held-out evaluation once
after parameters and protocol are frozen. If data exploration is required to
understand schema, timezone, interval coverage, or provenance, record that
limitation and keep the exploration separate from outcomes used for fitting or
split selection. The current audit is a blocker review; it does not define or
select a calibration/held-out split.
