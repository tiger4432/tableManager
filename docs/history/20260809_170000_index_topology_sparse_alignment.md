# Index topology accepts sparse DT sequences

**Date:** 2026-08-09  
**Status:** Implemented and verified

`map_alignment._index_member` no longer compares a stored `dt_index` to a
renumbered contiguous source rank. Per source map, it orders cells by each
candidate's serpentine topology and accepts the candidate when the stored index
values are strictly increasing in that order.

This preserves the existing `index_agreement` count, thresholds, candidate API,
and automatic-confirm gate. It permits omitted values such as `1,2,3,6,7` while
rejecting an inversion or duplicate index. The change is bounded to the index
membership predicate; `direction_violations` remains the existing tie-break.
