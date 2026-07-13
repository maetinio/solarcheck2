# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository actually contains

This repo has only two files:

- `README.md` — one line: "Wann lohnt sich ein Balkonkraftwerk?"
- `index.html` — a single, already-built, minified production bundle (~600KB, mostly on a handful of very long lines)

There is **no source code** in this repository: no `package.json`, no `src/` directory, no build config (Vite/webpack/etc.), no `node_modules`, no test files, no linter config. `index.html` is the final output of a Vite production build (recognizable from the `<script type="module" crossorigin>` / `<style rel="stylesheet" crossorigin>` pattern) with everything inlined:

- A minified React (v19, fiber-based) runtime and app code inside the single `<script type="module" crossorigin>` block
- Recharts (charting library) bundled into that same script
- Tailwind CSS v4 output (recognizable from the `@layer properties { @supports ... }` boilerplate) inside the single `<style rel="stylesheet" crossorigin>` block
- No external `src=`/`href=` references anywhere — the page is fully self-contained and needs no network access or build step to run

**Implication for any task in this repo:** there are no build/lint/test commands to run because there is no toolchain checked in — only the compiled artifact exists. Do not go looking for a `package.json` or try to run `npm install`; it isn't there. If a task requires changing app behavior, the actual editable source doesn't exist in this repo — flag this to the user rather than trying to hand-patch the minified bundle, since even small edits to code inside these giant single-line blocks are extremely risky and hard to verify.

## Running / previewing

Since `index.html` is fully self-contained (no external asset requests), it can be opened directly in a browser, or served statically for a more realistic environment, e.g.:

```bash
python3 -m http.server 8000
```

then visit `http://localhost:8000/index.html`.

## App purpose (inferred from embedded UI strings)

The page is a German-language **"Balkonkraftwerk Amortisationsrechner"** (balcony solar power plant payback calculator). Based on user-facing strings found in the bundle, it lets a user enter inputs such as:

- `Modulleistung` (module power), `Max. Speicher` (max storage)
- `Strompreis` (electricity price), `Eigenverbrauch` / `Maximale Eigenverbrauchsquote` (self-consumption), `Einspeiseleistung` (feed-in power)
- `Anschaffungskosten` (purchase cost)

and computes/displays:

- `Amortisationszeit` and an `Amortisationsverlauf` (payback time and a payback-over-time chart, via Recharts)
- `Jahresertrag` (annual yield)

The bundle also contains informational/legal content (e.g. GDPR data-portability text) and product recommendation content (e.g. "PV Solaranlage Komplettset mit Speicher").
