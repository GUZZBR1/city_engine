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
