# 📜 AssyManager Project History Index

This directory contains the detailed technical logs for every major phase of the AssyManager development journey. Use this index to find specific implementation details or architectural decisions.

---

## 🏗️ Core Infrastructure & Architecture
- **[Phase 19: Integrity & Stability Fixes](./20260412_221000_phase19_integrity_and_stability_fixes.md)**: Baseline stability for the enterprise suite.
- **[Unified System Columns](./20260412_232000_unified_system_columns.md)**: Standardizing `row_id`, `created_at`, `updated_at`.
- **[System Column Read-Only Guard](./20260412_233700_system_column_readonly_guard.md)**: Implementing metadata security.
- **[Centralized Endpoint Configuration](./20260415_210500_centralized_endpoint_config.md)**: Migrating to `config.py` driven endpoints.
- **[API Unification (Phase 33)](./20260417_api_unification_phase33.md)**: Streamlining REST endpoints for performance.

## 🛰️ Real-time Synchronization (WebSocket)
- **[WS Debug & Staggered Initialization](./20260412_222200_ws_debug_staggered_init.md)**: Handling multi-tab race conditions.
- **[WS Reliability & Manual Fix Sync](./20260412_224000_ws_reliability_and_manual_fix_sync.md)**: Ensuring 100% sync coverage.
- **[Broadcast Localization Fix](./20260412_233500_broadcast_localization_fix.md)**: Solving timezone issues in real-time streams.

## 📊 Data Integrity & Search Stability (v1.4)
- **[Updated At Sorting Sync](./20260412_230500_updated_at_sorting_sync.md)**: Implementing the "Float-to-top" logic.
- **[Row ID Direct Targeting](./20260417_data_integrity_and_batch_ordering_fix.md)**: Solving "Index Drift" during rapid updates.
- **[Search Session Guard & History Optimization (v1.4)](./20260420_phase73_5_search_and_history_optimization.md)**: ⚡ **[Latest]** UUID-based session validation & Server-driven total count sync.

## 🎨 UI Modernization & UX
- **[Enterprise UI Modernization](./20260415_224500_enterprise_ui_modernization.md)**: Catppuccin theme & Navigation Rail integration.
- **[History Panel Noise Removal](./20260415_211000_history_panel_noise_removal.md)**: Cleaning up the side panel stream.
- **[Cursor Lock & Viewport Tracking](./20260419_cursor_lock_and_viewport_tracking.md)**: High-performance lazy loading enhancements.

## ⚙️ Automation & Ingestion
- **[Directory Watcher Stabilization](./20260412_225500_directory_watcher_stabilization.md)**: Real-time file monitoring logic.
- **[Custom Parser Plugin Architecture](./20260412_235400_custom_parser_plugin.md)**: Extensible regex-based parsing.
- **[File Upload & Drag-and-Drop](./20260415_214000_drag_and_drop_upload.md)**: Expanding ingestion sources.

---
*Last Index Update: 2026.04.20 (Phase 73.6 Synchronization)*
