# Report: [Agent Excel] Search Scope Persistence (v1.5)

## 📋 Task Summary
Enhanced the search UI by persisting the "Search Scope" column selection across table tab switches.

## ✅ Accomplishments
- **Model State**: Added `_search_cols_state` to `ApiLazyTableModel` to act as the source of truth for UI checkbox states.
- **UI Restoration**: Updated `FilterToolBar.set_active_proxy` to restore the `_selected_cols` set from the incoming model's state.
- **Sync at Search**: Modified `_emit_search_requested` to update the model's state whenever a search is initiated, ensuring the selection is captured.
- **Menu Consistency**: Ensured the `Search Scope` dropdown reflects the restored state perfectly upon tab activation.

## 🛠️ Modified Files
- `client/models/table_model.py`: Added state variable.
- `client/ui/panel_filter.py`: Implemented save/restore logic.

## ⚠️ Issues & Observations
- The selection is persisted in-memory during the session. If the application is restarted, it will default back to an empty selection (all visible columns).

---
*Submitted by Agent Excel | 2026.04.20*
