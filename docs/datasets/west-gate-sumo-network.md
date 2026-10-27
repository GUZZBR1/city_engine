# West Gate Bridge SUMO network snapshot

This directory contains a dated, OSM-derived road network for the West Gate
Bridge area. It provides reproducible real local geometry for future empirical
work. It does not validate a TIRTL detector-to-edge mapping, define traffic
demand, or calibrate a simulation.

## Build and smoke test

From the repository root, install the pinned official SUMO application wheel
into a project-local environment and rebuild from the checked-in OSM snapshot:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-sumo.txt
.venv/bin/python tools/build_west_gate_network.py
```

To fetch a fresh extract from the official OSM API and rebuild it:

```bash
.venv/bin/python tools/build_west_gate_network.py --download
```

`--download` uses the official OSM API 0.6 map endpoint in 10 × 2 tiles to
stay below its per-request node cap. It keeps highway ways, their referenced
nodes, and complete restriction relations. It waits one second between API
requests. Use `--tiles COLUMNSxROWS` for smaller tiles if the API returns a
near-cap response; each tile is checked and the script stops on errors.

The builder runs `netconvert` with SUMO's recommended OSM network options,
left-hand traffic, guessed ramps and signals, and the local OSM road geometry.
It writes `west-gate.net.xml` and `manifest.json`; no route, trip, detector,
observation, or demand file is generated. The smoke step loads that network in
`sumo` and advances one simulated second with no routes or vehicles.
SUMO's wall-clock generation timestamp is normalized in the network comment;
repeated builds from this pinned input and tool version therefore have a stable
network SHA-256.

## Source and attribution

The checked-in `data/networks/west-gate-bridge-2026-10-27/west-gate.osm.xml`
was fetched on 2026-10-27 UTC from
`https://api.openstreetmap.org/api/0.6/map` for WGS84 bounds
144.84, -37.86, 144.95, -37.80. `source.json` records the API, bounds, fetch
interval, tile layout, and retained entity counts. `manifest.json` records
SHA-256 hashes for the exact OSM input and generated SUMO network, SUMO and
netconvert versions, build options, output counts, and smoke-test result.

© OpenStreetMap contributors. OpenStreetMap data is available under the
[Open Database License 1.0 (ODbL)](https://www.openstreetmap.org/copyright).
The SUMO network is a Produced Work derived from that database; the OSM
attribution and share-alike obligations apply. The source XML includes the OSM
copyright attribution, and SUMO output is generated with its license metadata.

## Scope and limits

The selected area includes the bridge and road approaches/accesses in the
bounding box. The bbox is an extraction boundary; it does not represent a
validated model boundary or complete demand boundary. OSM road classes, lane
counts, speeds, connections, ramp guesses, and signal guesses may be missing,
generalized, or inferred by SUMO. The output is not an engineering-validated
as-built network.

The current integration gate classifies both TIRTL sites 504 and 505 as
unresolved and permits descriptive profiling only. Neither site is eligible
for observed-vs-SUMO comparison. No detector edge, lane, or measurement
section is assigned. No detector comparison, OD estimation, demand creation,
calibration, or empirical performance claim is part of this network-only smoke
test. The OSM-derived network is a geometry candidate independent of detector
mapping. See
[`victoria-tirtl-validation-status.md`](victoria-tirtl-validation-status.md)
for prior evidence and the current evidence boundary supplied by the
integration review.
