---
description: Generate tests for an API route or Python script
user-invocable: true
---

Generate tests for $ARGUMENTS:

## For Python files (API routes, scripts, lib modules)

1. Read the file and understand its inputs, outputs, and side effects
2. Identify edge cases, error paths, and boundary conditions
3. Generate a test file using **pytest** with clear test function names
4. Cover:
   - Happy path (expected inputs -> expected outputs)
   - Error cases (missing params, invalid data, auth failures)
   - Edge cases (empty lists, None values, boundary numbers, missing env vars)
   - Side effects (Supabase calls, HubSpot API calls, file I/O — mock these with `unittest.mock` or `pytest-mock`)
5. Place test file: `tests/test_[module_name].py`

```python
import pytest
from unittest.mock import patch, MagicMock

def test_happy_path():
    ...

def test_error_case():
    ...
```

Use `@pytest.fixture` for shared setup. Mock external services (Supabase, HubSpot, SMTP) — never make real API calls in tests.

## For Frontend JS files (renderers, utils, charts)

1. Read the file and understand what it renders and what data it expects
2. Document the expected `window.TS` / `window.STATIC` data shape for testing
3. Generate a test plan (not executable tests — frontend is vanilla JS without a test runner):
   - List each render function and what DOM elements it should create
   - List edge cases: empty data, missing TS keys, zero values, negative values
   - List Chart.js interactions: chart creation, destruction, theme switching
4. Format as a manual test checklist that can be verified in the browser console

Output the test file and instructions for running (`pytest tests/test_[module].py -v`).
