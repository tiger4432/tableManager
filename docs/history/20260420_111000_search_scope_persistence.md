# [History] 20260420_111000_search_scope_persistence

## Phenomenon
When switching between different table tabs in the UI, the user-selected columns in the "Search Scope" dropdown menu were reset. This forced users to re-select specific columns every time they navigated back to a table.

## Root Cause
- The `FilterToolBar` maintained `_selected_cols` as a transient UI member that was cleared or reset in `_refresh_scope_menu` without referencing the specific table model's previous state.

## Solution & Code Changes
- **client/models/table_model.py**: 
  - Added `_search_cols_state` to store the list of previously selected columns for each model instance.
- **client/ui/panel_filter.py**:
  - `set_active_proxy`: Restores `self._selected_cols` from the model's `_search_cols_state`.
  - `_emit_search_requested`: Saves the current `self._selected_cols` to the model's `_search_cols_state`.
  - Added `[Phase 73.8]` markers.

## Validation
- Verified that column selections are successfully remembered when switching between multiple table tabs.

---
*AssyManager Technical History Asset | Agent Excel*
