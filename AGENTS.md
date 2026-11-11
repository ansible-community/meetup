# Agent guidance

Use these repository-wide notes for Python tooling, registry data, and documentation. The files below are the detailed sources of truth.

## Key files

- `pyproject.toml`: Python version, dependencies, Ruff, and Pyright configuration.
- `tools/lint.py`: local test, lint, type-check, and documentation-build runner. It applies Ruff fixes and formatting before checking.
- `.github/workflows/ci.yml`: CI checks, including zizmor for workflow changes.
- `docs/contributing/contributing.md`: contribution and documentation workflow.
- `docs/reference/tooling-specification.md`: operational tooling contract.
- `docs/reference/pretix-discourse-auth-specification.md`: Pretix authentication contract.
- `tools/common/ansible_events_lib.py`: shared tooling constants and helpers.
- `tools/common/ansible_event_cities.py`: canonical `CityInfo` and city registry.

## Working rules

- Check the working tree before editing and preserve unrelated changes. Read the relevant implementation, tests, and docs first.
- Keep behavior, specifications, and task guides aligned. Tooling changes update the tooling specification and affected Community Team guides. Pretix authentication changes also update its specification and account for the standalone plugin repository.
- Reuse shared constants and the canonical city registry. Preserve its uniqueness, sorting, time-zone, and coordinate invariants.
- Follow `pyproject.toml` for Python, typing, and style. Add focused tests for behavior changes, especially API edge cases; omitted fields may mean “unknown.” Tests must not require live services.
- Keep API operations safe to retry. Never expose credentials, attendee details, or private email addresses in logs, reports, or test output.
- Prefer updating existing docs over creating duplicates. Keep documented behavior, commands, defaults, and examples consistent with the implementation.
- Run `uv run python tools/lint.py` for Python/tooling changes. Review its diff because it formats and fixes files under `tools/` and `tests/`. For documentation-only changes, run `uv run mkdocs build --strict` and follow the contribution guide's preview and link checks when relevant.
