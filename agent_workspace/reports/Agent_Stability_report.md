# Report: [Agent Stability] Resource & Schema Optimization (v1.5)

## 📋 Task Summary
Optimized the client-side resource handling by implementing schema caching and hardening worker lifecycle management.

## ✅ Accomplishments
- **Schema Caching**: Added a check in `MainWindow._load_table_schema` that skips network requests if the model already has column data. This improves tab-switching speed and reduces server load.
- **Worker Management**: Enhanced `_execute_file_upload` to correctly track and clean up `ApiUploadWorker` instances in the `_active_workers` set.
- **Improved Logging**: Added debug logs to track cache hits for schema loading.

## 🛠️ Modified Files
- `client/main.py`: Updated `_load_table_schema` and `_execute_file_upload`.

## ⚠️ Issues & Observations
- The `_active_workers` set is now more consistent, but we should eventually implement a central worker manager class if the number of async operations grows.

---
*Submitted by Agent Stability | 2026.04.20*
