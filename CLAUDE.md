# CLAUDE.md

Raphael7: a Python CLI that scans messy HL7 v2 feeds, turns chosen messages into regression tests, and checks v2 → FHIR R4 (IL Core) output. It runs locally, so patient data never leaves the user's network.

## Read first
- `docs/PROJECT_PLAN.md`: scope, audience, technical design. Don't expand scope beyond it.
- `docs/ROADMAP.md`: the current week, its tasks and exit criteria. Decisions are recorded under the task they came from (e.g. the hl7apy spike in week 1). Follow them; ask before changing one.

## Commands (repo root)
- `uv sync`: install dependencies
- `uv run pytest`: tests (Hypothesis property tests included)
- `uv run ruff check` · `uv run ruff format`: lint and format (CI runs both, plus tests on 3.12–3.14)
- `uv run raphael7 --help`: the CLI

## Layout
- `src/raphael7/parser/`: text → `Message`. The pipeline, in reading order:
  `parse.py` (decode bytes → remove MLLP framing → split lines → group into messages at each MSH → split segments and fields),
  `encoding.py` (delimiters from MSH-1/MSH-2), `escape.py` (`\F\`, `\S\` …), `model.py` (`Message`, `Segment`, `ParseIssue`, `msg.get("PID-5.1")`), `serialize.py` (`Message` → text).
- `src/raphael7/scan/`, `diff/`, `testing/`, `fhir/`, `validate/`: one package per command, filled in week by week.
- `samples/`: synthetic messages only. `tests/`: pytest.

## Hard rules
- **No real patient data, ever.** Only synthetic messages in `samples/` and tests. Never ask for or accept real messages.
- **No hl7apy dependency** (spike decision, week 1). The parser uses no structure definitions and creates no object per element: plain nested tuples, no lookups in the hot path.
- **Positions, not field names, in v1** (`PID-5`, not "Patient Name"). If structure data is added later, use the flat, spec-checked format recorded in the roadmap.
- **Tolerant by default, never silent.** Never drop a message, segment or value without recording a `ParseIssue` with a stable `code`. Strict mode raises only on error-level issues.
- **Lossless.** Values stay raw (still escaped); `serialize(parse(text))` gives back the text. The round-trip property test must keep passing.

## Writing code that Sanja can read
Sanja reviews every change and must be able to read it quickly. Prefer clear over compact:
- **Named fields, not positional tuples.** Return dataclasses (e.g. `ParseIssue`), not `(code, severity, message)`.
- **Plain loops with named variables** over nested comprehensions and clever one-liners.
- **Small functions named after the step they perform** (`split_lines`, `group_into_messages`). No inner functions with `nonlocal`.
- **Each function starts with the HL7 reason it exists**, citing the field or segment (e.g. "MSH is special: field 1 *is* the separator, so it can't be split like other segments").
- **Explicit beats short**, e.g. five lines naming each MSH-2 character instead of a padding trick.
- A file should read top to bottom: public functions first, helpers below them.

## Workflow
- **Plan in plain words first.** Before writing a feature, describe the approach in a few sentences and wait for agreement.
- **Small steps:** one file or one idea per commit. Run `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` before each commit.
- **Give a reading guide with each change:** the file to start with, the 2–3 lines that matter, and what can be skipped.
- Work on a branch, never directly on `main`: `week<n>-<topic>` (e.g. `week1-parser`). Sanja reviews and merges.
- In `docs/ROADMAP.md`, a 🤖 task is ticked only after Sanja has reviewed it.
- Public docs stay about the product. Business and outreach notes live outside this repo (`../raphael7-private`, or gitignored `local/docs`).
