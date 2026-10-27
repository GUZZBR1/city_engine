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

## Evaluation metric units

In `traffic_observations.evaluation`, `volume_vehicles` and its MAE, RMSE, and
bias are actual vehicles counted in each matched interval. GEH is computed
after converting both observed and simulated interval counts to hourly-equivalent
rates (`count * 3600 / interval_seconds`), so `volume_geh` compares veh/h even
when the input bins are 15 minutes. A 15-minute pair of 5 and 7 vehicles is
therefore evaluated as 20 and 28 veh/h for GEH, while MAE and bias remain 2
vehicles per 15-minute interval. The interval duration comes from the matched
start and end timestamps. A zero/zero pair has GEH 0; speed has no GEH.

Metrics grouped by detector, segment, or time window summarize the matched
measurement rows and weight each row equally. They do not sum measurements from
multiple detectors into a segment or corridor total; such totals require an
explicit, validated aggregation policy.
