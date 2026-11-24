# Sample corpus

Synthetic HL7 v2 messages only. **Never put real patient messages here.**

- `vendor-a/`, `vendor-b/`, `vendor-c/`: ADT, ORU and ORM from three made-up vendors
- `broken/`: deliberately broken messages
- `expected-issues.json`: the `ParseIssue` codes each file must produce

What each vendor does differently, and what each broken file tests: [MANIFEST.md](MANIFEST.md).
Regenerate with `uv run python scripts/make_samples.py`.
