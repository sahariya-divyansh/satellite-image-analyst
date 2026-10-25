## Description
Provide a concise explanation of the changes made and the motivation behind them.

## Related Issues
Fixes # (issue)

## Architectural Principle Checklist
- [ ] **LLM Never Computes Numbers**: Geospatial metrics, polygon areas, thresholds, and coordinates are derived solely through deterministic math and raster processing.
- [ ] **Type Safety & Testing**: `mypy src tests` passes cleanly and unit tests cover new logic.
- [ ] **Reproducibility**: Changes maintain deterministic results given identical inputs.

## Changes Checklist
- [ ] Code follows project style guidelines (`ruff check .`, `ruff format --check .`)
- [ ] Tests added/updated (`pytest tests/unit`)
- [ ] Documentation updated in `docs/` or `README.md`
- [ ] CHANGELOG.md updated (if user-facing)
