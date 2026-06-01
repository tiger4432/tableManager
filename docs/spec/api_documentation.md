# assyManager Data Update Server API Documentation

This document describes the API endpoints provided by the `assyManager` server to manage rows, modify cell values, control multi-source priority rules (pinning), delete specific data sources, and query cell metadata.

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
