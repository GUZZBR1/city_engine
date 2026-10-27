# Empirical mobility validation review — round 3

**Scientific verdict: PARTIAL** — the round-2 mapping-confidence issue is resolved, but no real SUMO baseline, observed-versus-simulated metrics, calibration, or held-out validation has been performed.

**Reviewed integration commit:** `a5bea57bcbcc49cecbdb15b5954078fa59395597`

**Included changes:** `15aea1739318ab7b7574a276bca9e324c3a0ed5` and `7a3fd57d4b31945db0487567a858363870209860`

**Comparison baseline:** `632207e`
**Review branch:** `agent/empirical-mobility-validation/reviewer-r3`

## Round-2 disposition and mapping gate

**Resolved.** The mapping register now assigns site 505 `confidence: unresolved`, gives no segment or lane, and marks both exploratory-comparison and primary-validation eligibility `false` ([mapping register](victoria-tirtl-mapping-register.json), lines 95–129). The site-505 rationale says its label, predominant heading, and distance do not independently support a segment assignment (lines 121–126). Site 504 is also unresolved and comparison-ineligible (lines 58–92).

I found no stale operative claim that 505 has medium confidence or may be compared with SUMO. The only current `medium_confidence` occurrence is the generic confidence-scale definition in the mapping register (line 52); the older round-2 review records the superseded finding as history. The pilot limits use to descriptive profiling and gates any SUMO baseline on verified mapping and independent demand ([pilot](victoria-tirtl-pilot.md), lines 69–76). The status report says to stop before SUMO comparison and repeats the same descriptive-only rule ([validation status](victoria-tirtl-validation-status.md), lines 5–7 and 19–24). These documentation gates are consistent.

## Findings

**LOW — application persistence does not enforce empirical-evaluation eligibility.** The generic run writer accepts `calibration` and `validation` job types and stores the supplied dataset identity and metadata without checking detector mapping or evidence eligibility ([postgres.py](../../apps/api/app/persistence/postgres.py), lines 211–238). I found no TIRTL-aware comparison path, and the current comparison endpoint is for paired signal-timing simulations ([main.py](../../apps/api/app/main.py), lines 147–164), so this is a future bypass risk rather than evidence of a current TIRTL comparison. When an empirical evaluator is connected, enforce eligibility at that consumer boundary so the documented no-comparison rule cannot be bypassed by job metadata alone.

## Scientific claim and provenance audit

- **Official source claims:** The current DTP portal describes 15-minute aggregation by vehicle class, speed bin, site, and heading, and warns of classification errors at high throughput and site-specific outages ([DTP dataset page](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts)). Its site dictionary lists only `site`, `site_description`, `latitude`, and `longitude` ([DTP site-resource dictionary](https://opendata.transport.vic.gov.au/dataset/tirtl-traffic-counts/resource/1f685833-24fd-4eb0-af11-2e7cfc94da74)); it does not identify the coordinate reference system, accuracy, installation, or lane. Victorian guidance identifies GDA2020/MGA2020 as official and says GDA94/MGA94 remain supported, but does not establish which reference DTP used ([Surveyor-General of Victoria guidance](https://www.land.vic.gov.au/surveying/geodesy/geocentric-datum-of-australia)). The pilot correctly separates those jurisdictional facts from the unknown TIRTL-site CRS.
- **Direction and lane evidence:** The cited TIRTL technical paper describes direction output as dependent on beam-event order and correct installation orientation/configuration, and lane positions as learned for the installation. The pilot correctly treats this as general device behavior, not proof of DTP's exported `W`/`E` semantics or the West Gate installations ([technical paper](https://ihmcl.co.in/wp-content/uploads/2018/07/ATCC-Using-TIRTL-Technology-1.pdf)). It also correctly confines the Georgia DOT study to a different I-475 installation ([study record](https://dlg.usg.edu/record/dlg_ggpd_s-ga-bt700-pr4-bm1-b2020-bd4-belec-p-btext)).
- **Distance estimates:** The 9.28 m, 8.01 m, 6.52 m, and 10.77 m figures are explicitly described as inherited exploratory point-to-line estimates, calculated under an unverified CRS, with no preserved projection parameters and no OSM extract available for recomputation ([mapping register](victoria-tirtl-mapping-register.json), lines 10 and 48; [pilot](victoria-tirtl-pilot.md), lines 35–42). They are expressly not match evidence. This caveat is adequate; no segment assignment relies on the distances.
- **Leakage, metrics, and holdout:** The status report rejects using the target detector series to construct demand (lines 28–30), lists volume/speed metrics only as uncalculated, and states that calibration, a frozen split, and held-out evaluation have not started (lines 32–45). It requires independent demand and a later held-out period. No result or improvement is claimed.
- **Reproducibility:** The pilot records SHA-256 checksums and source versions, while noting that the raw DTP archive and OSM extract are outside the checkout and must be reacquired for replay ([pilot](victoria-tirtl-pilot.md), lines 19–27 and 35–42). Counts and distances therefore could not be independently regenerated from this worktree.

## Checks and limitations

- Mapping-register JSON parsed successfully.
- `git diff --check 632207e..a5bea57` reports trailing spaces on two lines of the historical round-2 review; these are Markdown hard-break formatting and do not affect the claims reviewed.
- No application tests, PostGIS integration, or SUMO execution were run. No empirical result is claimed.
- External-source review used the linked official pages and technical references as available on 2026-10-27. Source archive and OSM geometry were not present locally, so reported source counts and distances were not recomputed.

**Independent lane evidence:** code-reviewer recommendation `APPROVE` for the scoped documentation review; architect status `WATCH` for the non-blocking application-boundary gap above. **Review disposition: COMMENT.**
