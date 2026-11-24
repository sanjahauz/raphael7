# CLAUDE.md

Raphael7: a Python CLI that scans messy HL7 v2 feeds, turns chosen messages into regression tests, and checks v2 → FHIR R4 (IL Core) output. It runs locally, so patient data never leaves the user's network.

## Read first
- `docs/PROJECT_PLAN.md`: scope, audience, technical design. Don't expand scope beyond it.
- `docs/ROADMAP.md`: the current week, its tasks and exit criteria. Decisions are recorded under the task they came from. Follow them; ask before changing one.

## Before each commit
`uv run ruff check` · `uv run ruff format --check` · `uv run pytest` (CI runs the same).

## Hard rules
- **No real patient data, ever.** Only synthetic messages in `samples/` and tests. Never ask for or accept real messages.
- **No hl7apy dependency** (week-1 spike). The parser uses no structure definitions and creates no object per element: plain nested tuples, no lookups in the hot path.
- **Positions, not field names, in v1** (`PID-5`, not "Patient Name").
- **Tolerant by default, never silent.** Never drop a message, segment or value without recording a `ParseIssue` with a stable `code`. Strict mode raises only on error-level issues.
- **Lossless.** Values stay raw (still escaped); `serialize(parse(text))` gives back the text. The round-trip property test must keep passing.

## Writing code that humans can read
- **Named fields, not positional tuples.** Return dataclasses (e.g. `ParseIssue`), not `(code, severity, message)`.
- **Explicit over clever:** plain loops, named intermediate values, small functions named after their step. No nested comprehensions or closures with `nonlocal`.
- **Docstrings give the HL7 reason**, citing the field or segment (e.g. "MSH is special: field 1 *is* the separator, so it can't be split like other segments").

## Workflow
- **Plan in plain words first.** Before writing a feature, describe the approach in a few sentences and wait for agreement.
- **Small steps:** one file or one idea per commit.
- **Give a reading guide with each change:** the file to start with, the 2–3 lines that matter, and what can be skipped.
- Work on a branch `week<n>-<topic>`, never on `main`. Sanja reviews and merges.
- In `docs/ROADMAP.md`, a 🤖 task is ticked only after Sanja has reviewed it.
- Public docs stay about the product. Business and outreach notes live outside this repo (`../raphael7-private`, or gitignored `local/docs`).
