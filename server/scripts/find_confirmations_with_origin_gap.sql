-- Confirmations whose source map and reference floor declare DIFFERENT origins.
--
-- WHY THIS EXISTS
-- Until 2026-08-06 a confirmation borrowed the floor's origin for the map and never applied
-- the alignment's translation. Measured on a synthetic pair matching a real shape on the dev
-- box (floor start (1,1), map start (0,0)): scoring found the frame with 266/266 agreement,
-- and reading the map back through the confirmation put 0 of 266 cells where the scoring had
-- put them, off by a uniform (2,-2) -- exactly twice the solved shift, because the origin was
-- overwritten in the wrong direction AND the translation was never applied.
--
-- The error is ZERO whenever the two origins agree, which is why it went unseen: every fixture
-- in the repo, and every confirmed pair on the dev box, sits at (0,0)/(0,0).
--
-- WHAT THIS FINDS
-- Live (non-superseded) confirmation source rows whose map origin differs from the floor's.
-- Those are the rows written under the old behaviour whose stored coordinate system does not
-- reproduce the alignment it was confirmed from. Re-confirming such a unit rewrites it
-- correctly; nothing here modifies anything.
--
-- WHAT IT CANNOT SEE
--   * rows whose source map or reference has no `wafer_map_metadata` row -- the join drops
--     them, and they cannot be assessed from these columns at all. Count them with the second
--     query below rather than assuming there are none.
--   * whether the map has since been re-registered with a different origin. The comparison is
--     against metadata as it stands NOW, not as it stood at confirmation time.
--
--   psql -f server/scripts/find_confirmations_with_origin_gap.sql

\echo '== confirmations whose map origin differs from the floor origin =================='

SELECT h.confirmation_uid,
       h.rule_name,
       h.unit_key,
       h.winner_frame,
       h.confirmed_at,
       s.source_table,
       s.map_id,
       (ms.grid_metadata ->> 'grid_start_x') AS map_start_x,
       (ms.grid_metadata ->> 'grid_start_y') AS map_start_y,
       (mr.grid_metadata ->> 'grid_start_x') AS floor_start_x,
       (mr.grid_metadata ->> 'grid_start_y') AS floor_start_y,
       s.shift_dx,
       s.shift_dy
FROM frame_confirmation h
JOIN frame_confirmation_source s
  ON s.confirmation_uid = h.confirmation_uid
JOIN wafer_map_metadata ms
  ON ms.target_table = s.source_table AND ms.map_id = s.map_id
JOIN wafer_map_metadata mr
  ON mr.target_table = h.reference_table AND mr.map_id = h.reference_map_id
WHERE h.superseded_by IS NULL
  AND s.excluded_reason IS NULL
  AND ( (ms.grid_metadata ->> 'grid_start_x') IS DISTINCT FROM (mr.grid_metadata ->> 'grid_start_x')
     OR (ms.grid_metadata ->> 'grid_start_y') IS DISTINCT FROM (mr.grid_metadata ->> 'grid_start_y') )
ORDER BY h.confirmed_at;

\echo ''
\echo '== live source rows this check CANNOT assess (metadata row missing) ============='
\echo '-- absence here is not innocence: these rows simply cannot be judged by origin.'

SELECT h.confirmation_uid,
       s.source_table,
       s.map_id,
       h.reference_table,
       h.reference_map_id,
       s.shift_dx,
       s.shift_dy,
       (ms.map_id IS NULL) AS map_meta_missing,
       (mr.map_id IS NULL) AS floor_meta_missing
FROM frame_confirmation h
JOIN frame_confirmation_source s
  ON s.confirmation_uid = h.confirmation_uid
LEFT JOIN wafer_map_metadata ms
  ON ms.target_table = s.source_table AND ms.map_id = s.map_id
LEFT JOIN wafer_map_metadata mr
  ON mr.target_table = h.reference_table AND mr.map_id = h.reference_map_id
WHERE h.superseded_by IS NULL
  AND s.excluded_reason IS NULL
  AND (ms.map_id IS NULL OR mr.map_id IS NULL)
ORDER BY h.confirmed_at;
