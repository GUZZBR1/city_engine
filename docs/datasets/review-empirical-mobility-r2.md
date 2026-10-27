# Empirical mobility validation review — round 2

**Reviewed commit:** `49279351e52b3c1f4062171070fc156bc3a237f0`  
**Review branch:** `agent/empirical-mobility-validation/reviewer-r2`  
**Scope:** round-1 mapping-eligibility correction and current claims about TIRTL-to-SUMO validation.

## Finding

**LOW — site 505 confidence label is stronger than its documented evidence basis.** The register defines `medium_confidence` as requiring “multiple independent clues” ([mapping register](victoria-tirtl-mapping-register.json), lines 11–15), but assigns that confidence to 505 while listing CRS, heading semantics, physical installation, and covered lanes as unresolved (lines 80–87). The validation status explicitly says the clues' independence and reliability have not been established ([validation status](victoria-tirtl-validation-status.md), lines 19–24). Keep 505 as a candidate for investigation, but either document which clues are independent and their provenance or use a confidence description consistent with the evidence. This does not grant comparison eligibility.

## Round-1 disposition and claim audit

**Resolved:** the prior finding that 505 was eligible for exploratory comparison is fixed. Both sites have `eligible_for_exploratory_comparison: false` and `eligible_for_descriptive_profiling: true` ([mapping register](victoria-tirtl-mapping-register.json), lines 51–53 and 88–90). The register prohibits observed-versus-simulated and spatial SUMO comparison (line 93); the pilot limits the site profile to source observations and gates any numerical baseline on mapping, network, independent demand, and separate validation period ([pilot](victoria-tirtl-pilot.md), lines 65–72).

No success is implied for baseline execution, database integration, calibration, or held-out validation. The status report says no SUMO baseline or metrics were run (lines 5, 26–39), no calibration protocol or split was frozen (lines 41–45), and PostGIS integration was not run (lines 58–65). It also identifies demand circularity and prohibits using the target detector series as demand (lines 28–30). The pilot separately says TIRTL counts do not identify OD or routes (lines 15, 66–68). Claims remain appropriately bounded to source-data ingestion/profiling and documented blockers.

## Verdict and limits

**PARTIAL** — round-1 eligibility wording is resolved and no empirical validation success is overstated. The confidence-label issue above should be reconciled before treating 505's mapping confidence as evidence. No PostGIS, SUMO, baseline, calibration, or held-out execution was performed for this review; conclusions are based on checked-in documentation and the integrated commit.

**Checks:** reviewed commit and scoped docs; parsed mapping-register JSON; `git diff --check`. No application tests or simulations were run (documentation-only review).
