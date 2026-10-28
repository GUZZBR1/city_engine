# README design direction

## Source of truth

This document governs the project overview and visual assets in the root README. Runtime behavior and city parameters remain defined by the code, API schemas, and `configs/cities/aurora-base-v1.yaml`.

## Brand

Urban Twin Arena is an urban systems lab: careful, legible, evidence-led, and curious. Aurora is presented as a synthetic benchmark city, not a real municipality.

## Product goals

- Explain what the project does and what currently runs.
- Help a developer start the local API and web app.
- Make provenance and scientific limits visible before showing results.

## Personas and jobs

- Developers need setup commands and package boundaries.
- Researchers need experiment conditions, reproducibility, and evidence limits.
- Urban planners need a clear distinction between scenario exploration and validated prediction.

## Information architecture

The README order is: project identity, live product image, Aurora profile, implemented capabilities, experiment model, scientific limits, quick start, repository map, and documentation links.

## Design principles

- Distinguish measured, modeled, and synthetic information.
- Prefer real interface captures for product screenshots.
- Label explanatory diagrams as schematic; never use them as evidence of simulation output.
- Avoid implying a winner, trained agent, or real-city forecast where none exists.

## Visual language

Use a quiet editorial treatment: warm off-white surfaces, deep teal text, sage green, and restrained amber accents. Use the product's DM Sans, Space Grotesk, and DM Mono typography where available. Maps are local 2D diagrams without satellite imagery or geographic basemaps.

## Components

README images use concise captions; data tables carry units; callouts state provenance or limits; command blocks are copyable from the repository root.

## Accessibility

Every image has descriptive alt text. Important caveats also appear in text. Tables use header rows and avoid relying on color alone.

## Responsive behavior

Keep diagrams readable when rendered at mobile widths; use SVG view boxes and avoid text smaller than 12 px in source artwork.

## Interaction states

README images are static artifacts. The live application owns loading, error, retry, simulation, and experiment states.

## Content voice

Write in Brazilian Portuguese with short, concrete explanations. Call synthetic inputs synthetic, SUMO runs simulated, and empirical observations observed.

## Implementation constraints

- Store committed README artwork under `docs/assets/aurora/`.
- Use relative paths so GitHub renders the assets from the repository.
- Do not include Kaggle source files or generated traffic datasets in README assets.
- Keep the root checkout used by another task untouched; make documentation changes on the dedicated Aurora README branch.

## Open questions

- Which real city and licensed observed traffic sources, if any, will support future empirical validation?
- What scientific validation threshold will be required before presenting a real-city case study?
