# Bidirectional Synchronization for Cell Edits

Bidirectional synchronization for cell edits between the PyQt client and FastAPI server. When a client double clicks and edits a cell, the updated data is sent to a new PUT endpoint which saves the edit to the SQLite DB with `is_overwrite=True` to flag the manual correction, then broadcasts the change via WebSocket. The client then proactively updates its table background to yellow (`BackgroundRole`) upon successful REST API response.

## Proposed Changes

### Database Layer
#### [MODIFY] [schemas.py](file:///c:/Users/kk980/Developments/assyManager/server/database/schemas.py)
- Create `CellUpdate` schema to validate the incoming PUT payload (`row_id`, `column_name`, `value`).

#### [NEW] [crud.py](file:///c:/Users/kk980/Developments/assyManager/server/database/crud.py)
- Introduce a new file with `update_cell` method utilizing `flag_modified` to signal dictionary mutations in JSON column when `data[col_name]` is overwritten.

### API Layer
#### [MODIFY] [main.py](file:///c:/Users/kk980/Developments/assyManager/server/main.py)
- Add `PUT /tables/{table_name}/cells` endpoint.
- Invoke `crud.update_cell` to perform the database update.
- Upon successful execution, use WebSocket manager to broadcast the updated information to all active clients.

### Client UI Layer
#### [MODIFY] [table_model.py](file:///c:/Users/kk980/Developments/assyManager/client/models/table_model.py)
- Implement `flags` method to enable `Qt.ItemFlag.ItemIsEditable` interaction.
- Implement `setData` method properly capturing user edits (`Qt.ItemDataRole.EditRole`).
- Inside `setData`, issue a synchronous OR asynchronous network request (using `urllib.request`) to `PUT /tables/{table_name}/cells`.
- Upon successful response, update internal `self._data` buffer setting the new value and activating `is_overwrite = True`.
- Emit `dataChanged` passing both `DisplayRole` and `BackgroundRole` locally.

## Verification Plan

### Automated Tests
- Not applicable for this task.

### Manual Verification
1. Run Fastapi server:
   ```bash
   cd c:\Users\kk980\Developments\assyManager\server
   uvicorn main:app --reload
   ```
2. Start PyQt6 client app:
   ```bash
   cd c:\Users\kk980\Developments\assyManager\client
   python main.py
   ```
3. In the client, double-click any cell to enter edit mode, type a new value, and press Enter.
4. Verify HTTP Response in the terminal (HTTP 200 OK for `PUT`).
5. Real-time background modification to a yellow flag.
