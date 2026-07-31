# assyManager Data Update Server API Documentation

> **Status:** 🟠 부분 최신 | **Last-verified:** 2026-07-31 | **Owner:** Backend
> **범위 주의:** 이 문서는 **행·셀 쓰기 계약**의 상세 레퍼런스이고 **전체 라우트 지도가 아니다.** 엔드포인트 전수는 [architecture/backend §2](../architecture/backend.md)가 정본이다.
> ⚠️ **본문이 영어인 것은 이 파일의 기존 관례다**(나머지 `docs/`는 한국어). 한 파일 안에서 언어를 섞지 않으려고 신규 절도 영어로 썼다 — 언어 통일은 총괄 판단 대기.

This document describes the API endpoints provided by the `assyManager` server to manage rows, modify cell values, control multi-source priority rules (pinning), delete specific data sources, query cell metadata and table schema, and trigger the retroactive (backfill) operations from the admin surface.

---

## 1. Row Management

### 1.1 Create Row
Adds one or more empty rows to a specific table.

- **HTTP Method**: `POST`
- **Route**: `/tables/{table_name}/rows`
- **Path Parameters**:
  - `table_name` (string, required): Target database table name.
- **Query Parameters**:
  - `count` (integer, optional): Number of rows to create. Defaults to `1`.
  - `user_name` (string, optional): Operator name for audit tracking. Defaults to `"system"`.
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "count": 1,
    "row_ids": ["018fdf99-b1d2-7c80-928d-d790d3d528b1"],
    "created_logs": [
      {
        "id": 1052,
        "table_name": "inventory_master",
        "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
        "column_name": "CREATE",
        "old_value": null,
        "new_value": "행 생성됨",
        "source_name": "system",
        "updated_by": "user_admin",
        "transaction_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
        "timestamp": "2026-06-02T07:28:56.123456+09:00",
        "business_key": null
      }
    ]
  }
  ```
- **WebSocket Broadcast**:
  - Triggers a `batch_row_create` event to notify active clients of the new row nodes.

---

### 1.2 Delete Row (Single)
Physically deletes a single row by its unique ID.

- **HTTP Method**: `DELETE`
- **Route**: `/tables/{table_name}/rows/{row_id}`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
  - `row_id` (string, required): Unique UUID identifying the row.
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1"
  }
  ```
- **WebSocket Broadcast**:
  - Triggers a `batch_row_delete` event containing the single row ID.

---

### 1.3 Delete Rows (Batch)
Deletes a batch of multiple rows in a single operation.

- **HTTP Method**: `POST`
- **Route**: `/tables/{table_name}/rows/batch_delete`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
- **Request Body (JSON)**:
  - `row_ids` (array of strings, required): List of row UUIDs to delete.
  - `user_name` (string, optional): Operator name. Defaults to `"system"`.
  - **Example**:
    ```json
    {
      "row_ids": [
        "018fdf99-b1d2-7c80-928d-d790d3d528b1",
        "018fdf99-c2e3-7d90-a39e-e891d4e639c2"
      ],
      "user_name": "user_admin"
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "deleted_count": 2,
    "created_logs": [
      {
        "id": 1053,
        "table_name": "inventory_master",
        "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
        "column_name": "DELETE",
        "old_value": null,
        "new_value": "행 삭제됨",
        "source_name": "system",
        "updated_by": "user_admin",
        "transaction_id": "018fdf99-f567-7c80-bb2d-ea82b4a169b2",
        "timestamp": "2026-06-02T07:29:12.456789+09:00",
        "business_key": "PART-A-1002",
        "is_row_deleted": true
      }
    ]
  }
  ```
- **WebSocket Broadcast**:
  - Triggers a `batch_row_delete` event containing the array of deleted row IDs and audit logs.

---

## 2. Cell & Value Updates

### 2.1 Apply Batch Updates (Core)
The primary endpoint for modifying cell values. Handles single cell edits, range pasting, and directory watching pipeline ingestion.

- **HTTP Method**: `PUT`
- **Route**: `/tables/{table_name}/data/updates`
- **Path Parameters**:
  - `table_name` (string, required): Target table.
- **Request Body (JSON)**:
  - `updates` (array of objects, required): List of row updates.
    - `row_id` (string, optional): target PK. Either `row_id` or `business_key_val` must be supplied.
    - `business_key_val` (any, optional): target business key value (e.g. part number).
    - `updates` (object, required): column key-value mapping of updates.
    - `source_name` (string, optional): source parser or edit label (`"user"`, `"pipeline_parser"`, etc.). Defaults to `"user"`.
    - `updated_by` (string, optional): operator identity.
  - `transaction_id` (string, optional): custom transaction GUID to tie multiple updates.
  - `silent` (boolean, optional): if `true`, silences client WebSocket push broadcast. Defaults to `false`.
  - **Example**:
    ```json
    {
      "updates": [
        {
          "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
          "updates": {
            "stock_qty": 150,
            "remarks": "Updated safety buffer"
          },
          "source_name": "user",
          "updated_by": "user_admin"
        }
      ],
      "silent": false
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "updated_count": 1,
    "change_count": 1,
    "created_logs": [
      {
        "id": 1054,
        "table_name": "inventory_master",
        "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
        "column_name": "stock_qty",
        "old_value": "120",
        "new_value": "150",
        "source_name": "user",
        "updated_by": "user_admin",
        "transaction_id": "018fdf9a-a554-70a2-9e90-c23d539d48b1",
        "timestamp": "2026-06-02T07:30:15.987654+09:00",
        "business_key": "PART-A-1002"
      }
    ]
  }
  ```
- **Special Business Logic (Auto-Unpin)**:
  - If `source_name` is `"user"`, the backend automatically clears any existing manual priority constraint (`manual_priority_source = null`) for all updated cells, ensuring the user's manual value becomes active.
- **Refusal: virtual-join columns (`400`)**:
  - A column that exists only because a verified virtual join exposes it (`virtual_only`, announced by `/schema` under `virtual_columns` — see §5.2) is **not stored**, so it cannot be written. `crud.refuse_virtual_join_columns` runs as the first statement of `apply_batch_updates` and returns `400` naming the offending column(s).
  - The refusal is **batch-level**: one overlapping column rejects the whole request, including the rows and columns that were writable. A client that offers such a column as an edit target will lose an entire paste to a single cell it could never have written.
  - A `collide` column — a real stored column that a join also fills when the stored value is absent — is **deliberately still writable**. That write is the only way a user changes what the joined value shows.
- **WebSocket Broadcast**:
  - If changes count $\le 100$: Streams detailed `batch_row_upsert` chunks with all cell values.
  - If changes count $> 100$: Streams a lightweight `batch_refresh_required` event containing the change count and the list of audit logs (up to 5,000 logs) to update timelines without reloading grid data.

---

## 3. Cell Priority & Pinning Controls

Multi-source cells keep values from multiple sources in history. The display value is normally resolved using default source priority rules (`user` > `pipeline_parser` > `custom_script`). Pinning overrides this by manually selecting a priority source.

### 3.1 Pin Priority Source (Single Cell)
Sets a manual priority source for a specific cell.

- **HTTP Method**: `PUT`
- **Route**: `/tables/{table_name}/{row_id}/{col_name}/priority`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
  - `row_id` (string, required): Row UUID.
  - `col_name` (string, required): Target column.
- **Request Body (JSON)**:
  - `source_name` (string, required): Source key to prioritize (e.g. `"pipeline_parser"`). Pass `null` to unpin (remove manual priority constraint).
  - `updated_by` (string, optional): Operator. Defaults to `"user"`.
  - **Example**:
    ```json
    {
      "source_name": "pipeline_parser",
      "updated_by": "user_admin"
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1"
  }
  ```
- **WebSocket Broadcast**:
  - Triggers a `batch_row_upsert` event containing the updated row payload to refresh UI styling.

---

### 3.2 Pin Priority Source (Batch Cells)
Allows pinning manual priority sources for multiple cells/selections simultaneously.

- **HTTP Method**: `PUT`
- **Route**: `/tables/{table_name}/cells/priority/batch`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
- **Request Body (JSON)**:
  - `updates` (array of objects, required): List of cell coordinate structures.
    - `row_id` (string, required): Row UUID.
    - `column_name` (string, required): Column key.
  - `source_name` (string, required): Target source key to pin (e.g. `"user"`). Pass `null` to clear batch constraints.
  - `updated_by` (string, optional): Operator name. Defaults to `"user"`.
  - **Example**:
    ```json
    {
      "updates": [
        { "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1", "column_name": "stock_qty" },
        { "row_id": "018fdf99-c2e3-7d90-a39e-e891d4e639c2", "column_name": "stock_qty" }
      ],
      "source_name": "pipeline_parser",
      "updated_by": "user_admin"
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "count": 2
  }
  ```
- **WebSocket Broadcast**:
  - If changes count $\le 100$: Streams detailed `batch_row_upsert` event chunks with audit logs.
  - If changes count $> 100$: Streams a lightweight `batch_refresh_required` event with log metadata.

---

## 4. Source Data Deletion

Clears a specific source's historical data value inside a cell, causing the cell value to be re-evaluated using the remaining sources.

### 4.1 Delete Cell Source Value (Single Cell)
Removes historical data for a specified source from a single cell.

- **HTTP Method**: `DELETE`
- **Route**: `/tables/{table_name}/{row_id}/{col_name}/sources/{source_name}`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
  - `row_id` (string, required): Row UUID.
  - `col_name` (string, required): Column key.
  - `source_name` (string, required): Target source name to delete (e.g. `"pipeline_parser"`).
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1"
  }
  ```
- **WebSocket Broadcast**:
  - Broadcasts a `batch_row_upsert` event showing the updated cell.

---

### 4.2 Delete Cell Source Values (Batch Cells)
Removes historical data for a specified source across multiple selected cells.

- **HTTP Method**: `POST`
- **Route**: `/tables/{table_name}/cells/sources/delete/batch`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
- **Request Body (JSON)**:
  - `cells` (array of objects, required): Coordinates of target cells.
    - `row_id` (string, required): Row UUID.
    - `column_name` (string, required): Column key.
  - `source_name` (string, required): Source name to delete.
  - **Example**:
    ```json
    {
      "cells": [
        { "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1", "column_name": "stock_qty" },
        { "row_id": "018fdf99-c2e3-7d90-a39e-e891d4e639c2", "column_name": "stock_qty" }
      ],
      "source_name": "pipeline_parser"
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "status": "success",
    "count": 2
  }
  ```
- **WebSocket Broadcast**:
  - Standard batch thresholding determines whether `batch_row_upsert` chunks or lightweight `batch_refresh_required` events are broadcast.

---

## 5. Metadata Queries

### 5.1 Batch Query Cell Sources
Queries comprehensive source information (history values, pinning status) for multiple cells in a single request. Primarily used by UI modals.

- **HTTP Method**: `POST`
- **Route**: `/tables/{table_name}/cells/sources/query`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
- **Request Body (JSON)**:
  - Structure matches the updates coordinates model (`BatchCellPriorityRequest`).
  - **Example**:
    ```json
    {
      "updates": [
        { "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1", "column_name": "stock_qty" }
      ]
    }
    ```
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  [
    {
      "row_id": "018fdf99-b1d2-7c80-928d-d790d3d528b1",
      "column_name": "stock_qty",
      "sources": {
        "user": {
          "value": 150,
          "timestamp": "2026-06-02T07:30:15.987654",
          "updated_by": "user_admin"
        },
        "pipeline_parser": {
          "value": 120,
          "timestamp": "2026-06-02T00:57:21.150000",
          "updated_by": "system"
        }
      },
      "manual_priority_source": null,
      "priority_source": "user",
      "value": 150
    }
  ]
  ```

### 5.2 Table Schema
Returns the column contract a client needs to build a grid for one table.

- **HTTP Method**: `GET`
- **Route**: `/tables/{table_name}/schema`
- **Path Parameters**:
  - `table_name` (string, required): Table name.
- **Response Format**: `JSON`
- **Response Example**:
  ```json
  {
    "table_name": "bonding_map",
    "columns": ["lot", "slot", "x", "y", "val", "created_at", "updated_at"],
    "column_types": { "x": "number", "y": "number", "val": "string" },
    "business_key": "pkg_id",
    "composite_key_source": ["lot", "slot"],
    "map_key_columns": ["lot", "slot"],
    "map_push_ok": false,
    "virtual_columns": [
      {
        "name": "product_code",
        "type": "string",
        "editable": false,
        "right_table": "lot_registry",
        "rule": "lot_product",
        "unresolved_label": "미상"
      }
    ]
  }
  ```
- **`columns` means STORED columns.** `virtual_columns` is a **separate key and is never merged into it**. A client that ignores the key behaves exactly as it did before the key existed — same column list, same paste targets, same "unprotected data column" arithmetic in the map editor's push gate.
- **`virtual_columns` is always present**, `[]` when no verified virtual join touches this table.
- **Only `virtual_only` columns are announced.** A `collide` column is a real stored column already listed in `columns`; announcing it twice would give two answers to "is this column stored?". A declaration that only collides therefore leaves this response byte-identical.
- **`editable: false` is not the enforcement.** The write refusal lives in `crud.apply_batch_updates` (§2.1); this flag only tells a client not to offer an edit that would come back `400`.
- **`type` is the RIGHT table's declared type, and the value domain is wider than that type.** When the join finds no row, or finds one whose value is empty, the cell carries `unresolved_label` — so a `number` column can legitimately contain a string. The label travels in the response so the client reads it instead of hardcoding `미상`.
- **On failure the route announces nothing** rather than failing: `virtual_columns` comes back empty and the server logs `[VirtualJoin]`. An unannounced column is a visible absence; a phantom column is a silent wrong answer and a write target that does not exist.

---

## 6. Retroactive (Backfill) Admin Surface

Five retroactive operations that previously existed only as CLIs get an inventory route, a count route and a trigger route. The registry (`server/retroactive.py`) is **pure dispatch** — every count calls the operation's own dry-run and every run calls the same function with `apply=True`, so no operation is reimplemented here.

All three routes are behind the shared admin token (`X-Admin-Token`). `POST .../run` is **strict**: it refuses with `503` when no token is configured, rather than falling back to open.

### 6.1 List Retroactive Operations

- **HTTP Method**: `GET`
- **Route**: `/admin/retroactive/operations`
- **Response**: `{"operations": [...]}`, one entry per operation (`chain_replay`, `withdraw`, `enrichment_backfill`, `enrichment_confirm`, `graph_orphans`), each carrying `op`, `label`, `what_is_missing`, `params`, `cli`, `cli_only`, and three facts a client must not guess:
  - `deletes` — `null`, or a phrase naming what is deleted.
  - `restartable` — whether an interrupted run resumes from where it stopped.
  - `commit_granularity` — in words.
- **Why those three travel in the payload**: one confirmation wording cannot fit five buttons. Four operations write values and commit per chunk; `graph_orphans` deletes rows and issues its single commit **after** the delete loop, so an interrupted run rolls back entirely — including chunks already deleted.
- Config only, **no DB query**, so it can sit on any request path.

### 6.2 Count (read-only)

- **HTTP Method**: `GET`
- **Route**: `/admin/retroactive/{op}/count`
- **Query Parameters**: the operation's own declared parameters, plus `scan_limit` (integer, optional).
  - Unknown parameter names are refused with `400`. A silently ignored typo makes "0 affected" look like an answer.
  - `scan_limit` is the **preview budget** and is not any CLI's `--limit` (that spelling means three different things across the five CLIs, and the orphan sweep has none). Default `200`, clamped to `2000` (`retroactive.DEFAULT_SCAN_LIMIT` / `MAX_SCAN_LIMIT`).
- **Response**: `{op, mode: "dry-run", params, label, cli, deletes, restartable, commit_granularity, affected, affected_label, count_kind, scanned, scan_limit, truncated, detail, blocked_reason, extra}`.
  - **`count_kind` is part of the answer**, one of:
    - `exact` — a cheap query answered the whole question.
    - `sample` — a bounded scan; `scanned` and `truncated` say so, and `detail` states in words that the number is about the sample, not the table.
    - `upper_bound` — a cheap query answered a superset; `extra.why_upper_bound` names the missing half in words.
  - Four of the five counts cannot be exact on a request path, and none of them claims to be. An exact R1 count is the operation itself, not a preview of it.
  - **`scan_limit` is `null` for operations that walk no rows.** Echoing the requested budget there would tell a reader a sample was taken when none was.
  - `blocked_reason` (e.g. `auto_confirm_off`) is non-null when the run would be refused, so a client disables the button instead of letting the operator discover the refusal by pressing it.
  - The route is read-only by construction: it rolls back on the way out regardless of which operation ran.

### 6.3 Trigger a Run (strict token)

- **HTTP Method**: `POST`
- **Route**: `/admin/retroactive/{op}/run`
- **Request Body (JSON)**: `{"params": {...}, "requested_by": "<optional operator>"}`
- **Response**: `{"status": "queued", "run_id": "<12 hex>", "op", "params", "label"}`
- **This route queues; it does not execute.** It writes one `DatabaseOutbox` row (`event_type: "RETROACTIVE_RUN"`, `table_name: "__retroactive__"`) plus `NOTIFY outbox_event` and returns — the same shape as `POST /admin/auto-update/run-now`. The auto-update scheduler picks the row up and runs the operation on a dedicated thread; a retroactive run walks a whole table, so a synchronous handler would hold both the request and a web-server worker until the browser gave up.
- **One run at a time.** A second trigger while one is in flight is refused by the scheduler and logged, and its outbox row is left unprocessed for a later tick rather than silently queued.
- **Parameter validation happens in exactly one place** (`retroactive.validate`), so the route and the worker cannot disagree about what a valid request is.
- **The safety properties live in the operations, not here.** R2's two refusals — the `user` source, and cells a human pinned via `manual_priority_source` — are inside `chain_replay.withdraw_source`, and this path routes *into* that function. The route re-states the first refusal only so the operator gets a `400` instead of a queued job that dies in a worker log.
