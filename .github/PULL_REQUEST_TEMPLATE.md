## What & why

<!-- What does this change, and what problem does it solve? Link any related issue. -->

## How it was verified

<!-- Tests added/run, manual checks, screenshots for UI changes. -->

## Checklist

- [ ] `uv run ruff check` is clean
- [ ] `uv run pytest` passes (new tests added if it's a reader or behavior change)
- [ ] `npm run build` passes (for frontend changes)
- [ ] Reader `sniff()` stays honest (no over-claiming formats it can't decode)
