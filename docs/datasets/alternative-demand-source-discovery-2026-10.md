# West Gate traffic source discovery

**Research date:** 2026-10-27
**Scope:** identify real traffic observations and independent demand candidates for the West Gate SUMO pilot. This is a source assessment only: no OD matrix was constructed, no demand was estimated, and no empirical calibration or validation was run.

## Finding

No current candidate clears every gate for a West Gate empirical run. Under the completed TIRTL evidence decision, sites 504/505 are **`UNSUITABLE_FOR_EMPIRICAL_VALIDATION` on currently available public evidence**. Their historical observations remain source data for descriptive profiling only. The mapping of these sites to a SUMO lane/edge is unresolved, and point observations do not identify OD demand. The repository has an executable OSM-derived West Gate network, but its empty-network smoke test is not a traffic validation. See the [pilot audit](victoria-tirtl-pilot.md), [mapping register](victoria-tirtl-mapping-register.json), [network notes](west-gate-sumo-network.md), and [validation status](victoria-tirtl-validation-status.md).

Scores are unstructured qualitative expert judgment for this West Gate research comparison (1 = weak, 5 = strong), not the output of predefined anchors or a reproducible scoring method. Mapping is judged by available evidence of assignment to a road direction/section, not mere availability of coordinates. The rank is a **research-priority ranking only**; no rank or score means the source passed an empirical-validation gate. Overall rank prioritizes potential local research value, not current validation eligibility, and is not a score average.

| Research priority | Candidate | Mapping | Temporal | License | Demand utility | SUMO fit | Overall |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | DTP TIRTL, West Gate sites 504/505 | 2 | 5 | 5 | 1 | 3 | Highest-priority local evidence follow-up; currently unsuitable for empirical validation |
| 2 | DTP SCATS traffic-signal volume data | 2 | 5 | 5 | 3 | 3 | Provisional candidate for independent time-varying demand constraints; measurement semantics and detector locations need verification |
| 3 | Victoria historical AADT GeoJSON | 4 | 1 | 5 | 3 | 4 | Independent directional volume prior; too coarse and old for time-resolved demand |
| 4 | FHWA NGSIM I-80 | 4 | 5 | 1 | 4* | 3 | Strong real-traffic research benchmark, but unrelated geography and explicit reuse license not located |

## Candidate evidence and limitations

### 1. DTP TIRTL — West Gate observation candidate

The [official DTP dataset page](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts) describes optical sensors that count and classify vehicles and measure speed. Records aggregate volume by 15-minute period, site, heading, vehicle class, and speed bin. The portal declares **Creative Commons Attribution 4.0** and warns of classification errors during high throughput and site outages.

The repository's October 2026 audit reports 2,501 site/time/heading groups for site 505. The historical observations are retained as source data for descriptive profiling only. The [TIRTL validation report](victoria-tirtl-validation-status.md) classifies sites 504/505 as **`UNSUITABLE_FOR_EMPIRICAL_VALIDATION` on available public evidence**: the site table does not specify site-specific CRS/datum or positional accuracy; physical installation location, carriageway and lane coverage are undocumented; and the meaning/orientation of exported headings is unverified, including contrary heading records. No detector-to-lane/edge mapping is established. Reopening requires site-specific confirmation of CRS/datum and coordinate accuracy, an authoritative installation plan or statement identifying carriageway and covered lanes, documented heading semantics resolving contrary headings, and independent verification that the versioned SUMO measurement section matches that installation. Until that evidence is available, do not use these sites for empirical validation or demand generation. TIRTL counts provide no trajectories or OD and cannot alone define network demand.

### 2. DTP SCATS traffic-signal volumes — independent count candidate

The [official DTP dataset](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data) publishes 15-minute SCATS detector measurements and declares **Creative Commons Attribution 4.0**. The [data dictionary](https://opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data/resource/001ace40-280b-462d-b580-7a79e70185fb) documents site ID, detector ID, interval time in AEST, and a volume field defined as detector state transitions from deactivated to activated. That definition is not, by itself, a verified vehicle count.

This is a provisional demand-constraint candidate, not a mapped or semantically verified vehicle-count source. The reviewed fields do not establish detector coordinates, approach direction, lane-to-SUMO assignment, speed, or whether each state transition corresponds to one passing vehicle at the selected sites. Verify those measurement semantics and the site-level detector geometry, coverage, and direction before using values as demand constraints. Even verified point counts cannot uniquely determine routes or OD.

### 3. DTP historical AADT — directional volume prior

The [official historical AADT dataset](https://opendata.transport.vic.gov.au/dataset/historical-annual-average-daily-traffic-volume) provides GeoJSON road-segment volumes for all vehicles and heavy vehicles in each direction, under **Creative Commons Attribution 4.0**. It covers 2001–2019 and is no longer updated; the portal says volumes may be either estimated or collected. It is useful as an independent broad-scale volume constraint, but not as current, time-of-day demand or speed evidence.

### 4. FHWA NGSIM I-80 — academic/research benchmark

FHWA's [I-80 dataset description](https://www.fhwa.dot.gov/publications/research/operations/06137/) documents real eastbound freeway data from Emeryville collected on 2005-04-13: a roughly 500 m, six-lane section, vehicle locations every 0.1 seconds, 45 minutes across three intervals, plus CAD/GIS, orthophotos, and loop-detector data. FHWA says NGSIM resources are [freely available](https://ops.fhwa.dot.gov/trafficanalysistools/ngsim.htm), but the reviewed official pages did not state an explicit reuse license; free download is not treated here as a license grant. Its geometry and trajectories are a strong SUMO research benchmark, not a West Gate demand source.

*NGSIM's rich trajectories and detector series could support demand or validation experiments. The same trajectory records must not be used to generate demand and then be counted again as independent validation evidence.*

## Demand and leakage boundary for West Gate

- Keep the historical TIRTL observations from sites 504/505 and their summaries as descriptive/source data only. Do not use them for demand generation, adjustment, calibration, or empirical validation under the current evidence decision. Reconsider validation eligibility only after the site-specific reopening evidence listed above is documented.
- Investigate SCATS detectors at distinct sites/approaches as a possible independent source of time-varying demand constraints, provisionally. First verify that state transitions represent vehicle counts at the selected sites, then verify geospatial locations, directions, network coverage, and SUMO assignments. Separate detector IDs prevent reuse of the exact TIRTL observations, but do not remove shared-source or sensor-system biases.
- Use historical AADT only as a coarse external prior, not a time-resolved profile.
- DTP confirms West Gate Tunnel project traffic modelling and published assessments, but the reviewed [official overview](https://transport.vic.gov.au/news-and-resources/projects-hub/transport-amenity-program) does not establish availability of executable OD or assignment matrices. Access and license for such inputs remain unknown.
- SUMO documents route/demand generation from detector observations in its [HighwayDetector tutorial](https://sumo.sourceforge.net/docs/Tutorials/HighwayDetector.html); counts constrain demand but do not define a unique route solution. Do not report reconstructed OD as observed demand without independent trip/OD evidence.

## Gate to advance

Before an empirical West Gate run, establish an authoritative detector-to-lane/edge mapping and direction convention; verify the semantics and site-level mapping of any SCATS counts used as demand constraints; choose independent demand inputs that exclude TIRTL sites 504/505; and document coverage, time zone, missing-data and vehicle-class handling. TIRTL sites 504/505 remain descriptive-only and are explicitly excluded from demand, adjustment, calibration, and validation under the current evidence decision. Until the evidence gates are met, describe the West Gate SUMO network as an executable geometry candidate, not an empirically validated traffic model.
