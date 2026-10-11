-- comp_id notation fold - the declared {"join": "-"}: a run of whitespace . _ - becomes one '-'.
-- ASCII only (the separators are written as chr(n)). Replace <T> with the table name everywhere.
-- Stop the running notation op first (stop_retroactive.bat).

-- PRE-CHECKS - all three must be 0
SELECT count(*) AS non_string_layers FROM cell_sources
 WHERE table_name = '<T>' AND column_name = 'comp_id' AND json_typeof(value) NOT IN ('string', 'null');
SELECT count(DISTINCT t.row_id) AS rows_where_a_layer_differs_from_shown FROM "<T>" t
  JOIN cell_sources c ON c.table_name = '<T>' AND c.column_name = 'comp_id' AND c.row_id = t.row_id
 WHERE (c.value #>> '{}') IS DISTINCT FROM t.comp_id;
SELECT count(*) AS user_overwrites FROM cell_overwrites WHERE table_name = '<T>' AND column_name = 'comp_id';

-- HOW MANY ROWS WILL MOVE (read only)
SELECT count(*) AS rows_to_fold FROM "<T>" WHERE comp_id <> regexp_replace(comp_id, '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g');

BEGIN;
INSERT INTO audit_logs (table_name, row_id, column_name, old_value, new_value, source_name, updated_by, transaction_id, timestamp, business_key)
  SELECT '<T>', row_id, 'comp_id', to_json(comp_id), to_json(regexp_replace(comp_id, '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g')),
         'notation_backfill', 'notation_backfill', 'notation_sql_20261012', now(), business_key_val
    FROM "<T>"
   WHERE comp_id <> regexp_replace(comp_id, '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g');
UPDATE cell_sources
   SET value = to_json(regexp_replace((value #>> '{}'), '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g'))
 WHERE table_name = '<T>' AND column_name = 'comp_id' AND json_typeof(value) = 'string'
   AND (value #>> '{}') <> regexp_replace((value #>> '{}'), '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g');
UPDATE "<T>"
   SET comp_id = regexp_replace(comp_id, '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g')
 WHERE comp_id <> regexp_replace(comp_id, '[' || chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(28) || chr(29) || chr(30) || chr(31) || chr(32) || chr(46) || chr(95) || chr(133) || chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || chr(8239) || chr(8287) || chr(12288) || '-]+', '-', 'g');
COMMIT;
