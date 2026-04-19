# [History] 20260420_110000_resource_and_schema_optimization

## Phenomenon
1. Redundant network requests for table schemas were occurring every time a tab was programmatically refreshed or added, even if the schema was already known.
2. `ApiUploadWorker` instances were not systematically tracked in the `_active_workers` set, risking premature Garbage Collection (GC) and loss of lifecycle control.

## Root Cause
- `_load_table_schema` lacked a local cache check on the model's column state.
- `_execute_file_upload` omitted the boilerplate logic for worker set registration and cleanup.

## Solution & Code Changes
- **client/models/table_model.py**:
  - Changed initial `_columns` from `["id"]` to `[]`. This ensures the first `_load_table_schema` call correctly identifies that a network fetch is required.
- **client/main.py**: 
  - Added `if model._columns: return` logic to `_load_table_schema` to implement "Lazy Caching."
  - Integrated `_active_workers` registration and removal (via `_on_finished`/`_on_error`) in `_execute_file_upload`.
  - Standardized terminology and added `[Phase 73.8]` markers.

## Validation
- Verified that switching between existing tables no longer triggers `[Schema] network fetch` logs.
- Verified that file uploads successfully complete and clear their worker tracking.

---
*AssyManager Technical History Asset | Agent Stability*
