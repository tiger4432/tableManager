# Replay Audit Cache Sync — 2026-08-10

## Problem

`chain_replay` records `AuditLog` rows in the chain-worker process. The Admin
recent-history endpoint previously returned a cache that is local to the API
process and was loaded only once. A successful replay could therefore exist in
the database and be available from its transaction detail endpoint, while being
absent from the recent audit list.

## Change

- `AuditLogCache` records the greatest database audit id seen when it builds
  the bounded recent-transaction projection.
- Before `/audit_logs/recent` responds, it probes `MAX(audit_logs.id)`.
- When a worker committed a later row, the API process reads and merges only
  the primary-key range after its watermark. It does not rescan historic audit
  groups; no range query occurs when the watermark is unchanged.

## Verification

- Added a regression test that commits a replay-like audit row without calling
  the cache, then requires the recent projection to merge and show its
  transaction first without rebuilding historic groups.
- `test_audit_cache_cross_process.py` and `test_api.py` pass.

## Operational result

After a replay completes, refreshing the Admin audit list displays the replay
transaction without restarting the API process. The database remains the audit
authority; the cache is now a coherent projection rather than a second source
of truth.
