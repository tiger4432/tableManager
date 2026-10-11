-- comp_id declared {"join": "-"}: the declared fold = notation_norm.fold_sql_text (separator run -> '-').
-- Replace <T> with the table name (3 places in the audit statement, 2 elsewhere). Stop the running notation op first.

-- PRE-CHECKS (all three must be 0 for the end state to equal the fast path's; measured, see report)
SELECT count(*) AS non_string_layers FROM cell_sources
 WHERE table_name = '<T>' AND column_name = 'comp_id' AND json_typeof(value) NOT IN ('string', 'null');
SELECT count(DISTINCT t.row_id) AS rows_where_a_layer_differs_from_shown FROM "<T>" t
  JOIN cell_sources c ON c.table_name = '<T>' AND c.column_name = 'comp_id' AND c.row_id = t.row_id
 WHERE (c.value #>> '{}') IS DISTINCT FROM t.comp_id;
SELECT count(*) AS user_overwrites FROM cell_overwrites WHERE table_name = '<T>' AND column_name = 'comp_id';

BEGIN;
INSERT INTO audit_logs (table_name, row_id, column_name, old_value, new_value, source_name, updated_by, transaction_id, timestamp, business_key)
  SELECT '<T>', row_id, 'comp_id', to_json(comp_id),
         to_json(regexp_replace("comp_id", '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g')),
         'notation_backfill', 'notation_backfill', 'notation_sql_20261012', now(), business_key_val
    FROM "<T>"
   WHERE comp_id <> regexp_replace("comp_id", '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g');
UPDATE cell_sources
   SET value = to_json(regexp_replace((value #>> '{}'), '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g'))
 WHERE table_name = '<T>' AND column_name = 'comp_id' AND json_typeof(value) = 'string'
   AND (value #>> '{}') <> regexp_replace((value #>> '{}'), '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g');
UPDATE "<T>"
   SET comp_id = regexp_replace("comp_id", '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g')
 WHERE comp_id <> regexp_replace("comp_id", '[\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f ._\u0085                 　-]+', '-', 'g');
COMMIT;
