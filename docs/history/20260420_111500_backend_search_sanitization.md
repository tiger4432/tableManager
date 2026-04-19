# [History] 20260420_111500_backend_search_sanitization

## Phenomenon
The precise search logic implemented in v1.5 used raw user input directy in `ilike(f"%{q}%")`. This meant that if a user entered search characters like `%` or `_`, it would be interpreted as SQL wildcards, leading to incorrect result sets and potentially degraded database performance during full-table scans.

## Root Cause
- Missing escaping logic for SQL wildcard characters in the bridge between the API and the SQLAlchemy query builder.

## Solution & Code Changes
- **server/main.py**: 
  - Implemented manual escaping of `%` and `_` characters in the `q` parameter using a backslash.
  - Updated all `ilike` calls to include `escape="\\"` for cross-dialect compatibility.
  - Added `[Phase 73.8]` markers.

## Validation
- Verified that searching for a literal `%` character (by entering `%` in the UI) now only matches rows actually containing that character, rather than matching all rows.

---
*AssyManager Technical History Asset | Agent I*
