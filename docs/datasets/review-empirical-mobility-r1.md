# Baseline review: empirical mobility validation

**Verdict: PARTIAL**
**Reviewed commit:** `6f782c55a8b821b512bd0e117aea426045666fb8`
**Review branch:** `agent/empirical-mobility-validation/reviewer`
**Scope:** validation status, TIRTL pilot and mapping register, source adapter and observation contract, PostgreSQL persistence/migration, and adapter/PostGIS integration test code.

## Finding

**MEDIUM — exploratory mapping eligibility is broader than the demonstrated evidence.** The 505 mapping is marked `medium_confidence` and `eligible_for_exploratory_comparison: true` ([mapping register](victoria-tirtl-mapping-register.json), lines 79–88), while its CRS, heading semantics, physical installation point, and covered lanes are unresolved. Its confidence rubric calls for multiple independent clues (lines 11–15), but the independence and reliability of the site label, heading predominance, and exploratory distance are not established. Restrict this eligibility to descriptive data profiling, or make explicit that it does not permit observed-versus-simulated comparison until independent installation/mapping evidence exists.

## Evidence and limits

- **Provenance and transformations:** The pilot records the source, declared license, and checksums for the monthly archive, site table, and OSM extract ([pilot](victoria-tirtl-pilot.md), lines 17–27). The adapter hashes the archive and supporting site file, records observed provenance, retains source class counts/headings, and labels hourly flow and speed as derived ([sources.py](../../packages/traffic_observations/traffic_observations/sources.py), lines 327–355, 404–408, 458–503). Speed uses bin midpoints; the open top bin uses its lower bound. The raw monthly archive is not checked into this checkout, so the reported exact counts cannot be regenerated from this branch alone.
- **Mapping confidence:** Neither site has a mapped edge or lane; 504 is unresolved and 505 is explicitly excluded from primary validation (mapping register, lines 41–52 and 77–96). The status document correctly says the candidate evidence does not confirm the physical segment ([validation status](victoria-tirtl-validation-status.md), lines 19–24).
- **Leakage and demand circularity:** The status document explicitly rejects constructing demand from the same detector series used as target ([validation status](victoria-tirtl-validation-status.md), lines 28–30, 43–45). This is a sound constraint, but no independent boundary demand, frozen split, or completed held-out design is evidenced.
- **Metrics:** The document defines MAE, RMSE, bias, and GEH and says MAPE will not be used near zero (validation status, lines 32–39). No metric values or comparison implementation are presented. TIRTL volume is a 15-minute count; `flow_veh_h` is a derived count multiplied by four. Speed is an approximate bin-based statistic, so any future comparison still needs an explicit aligned estimand and units.
- **Reproducibility and execution claims:** The report states that no SUMO baseline, calibration, or held-out evaluation ran and that PostGIS integration was not run (validation status, lines 5–8, 26–45, 58–65). The checked-in adapter tests use fixtures; the PostGIS test is opt-in and requires a disposable database ([integration test](../../apps/api/tests/integration/test_postgis_integration.py), lines 1–5, 21–25). This review inspected code only; it did not run tests, PostGIS, or SUMO. No runtime execution is demonstrated by the reviewed artifacts.

## Assessment

The baseline report is appropriately bounded and does not claim empirical validation. The source handling preserves important uncertainty, and the demand circularity risk is identified. However, there is no defensible detector-to-network assignment, West Gate SUMO network, independent demand definition, frozen held-out protocol, or executed observed-versus-simulated metric. The mapping eligibility finding should be narrowed before exploratory results are interpreted as simulation evidence.

**Architectural status: WATCH.**
**Overall: PARTIAL** — documentation and ingestion audit are reviewable; empirical mobility validation remains unperformed.

This is a **baseline-state review** of commit `6f782c55a8b821b512bd0e117aea426045666fb8`. Subsequent milestones require a new review round.
