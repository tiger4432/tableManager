# -*- coding: utf-8 -*-
"""총괄 10-11 (소유자 「노테이션 소급 엄청 빨리 해주는 스크립트 하나 줘」) — `fold_written_notation` folded by value
leaves what the row path leaves.

Two copies of one seed in the scratch schema. A: every page through the row path (`FOLD_BY_VALUE_DIALECTS`
emptied - what every other dialect takes). B: PostgreSQL's page by value (`_fold_by_values`), the rows whose
key part could move judged by the row path and written with the page, but a merging row and the row it merges
into through the ORM. Compared with ids and times left out: rows and keys, every layer,
overwrites, history lines, outbox events, the run's counts. The seed holds what a page by value has to get
right: one layer, two agreeing, two disagreeing, a person's layer, a pin, a shown value drifted from its
layers, a layer folded already under a stale shown value, a JSON number and a JSON null in a text column, a
blank, an alias, the time rule's three verdicts, the same spelling in two columns with different rules, an
orphan layer, key moves in two pages, merges into a holder in the same and in a later page and onto a key
moved by value a page before, a key part's layer stored as a JSON number under a clean key, a row whose cells
no longer spell its key, and a value that moves again."""
import json
import os
import sys

import pytest
from sqlalchemy import MetaData, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
import notation_norm as nn                                          # noqa: E402
from chain import keyset_scan, replay                               # noqa: E402
from conftest import PG_TEST_SCHEMA, _declared_as_test_database, _resolve_pg_test_url, retire_dynamic_model  # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from product_tables import NOTATION_ALIAS_TABLE, PRODUCT_TABLES     # noqa: E402

pytestmark = pytest.mark.pg

PLAIN, COMP, AGAIN = "pgqa_nf_plain", "pgqa_nf_comp", "pgqa_nf_again"
TABLES = {PLAIN: {"business_key": "k", "column_types": {"k": "string", "w": "string", "v": "string",
                                                        "seen": "string", "note": "string", "n": "number"}},
          COMP: {"business_key": "row_key", "composite_key_source": ["lot", "wafer"], "composite_key_separator": "_",
                 "column_types": {c: "string" for c in ("row_key", "lot", "wafer", "x")}},
          AGAIN: {"business_key": "k", "column_types": {"k": "string", "v": "string"}}}
OWNER = {"join": "-", "pad_last_number": 2}
ITEM = {"replace": [[" *[.] *", "."], [" *[(][0-9]+[)]\\Z", ""]], "collapse_repeats": "."}
DECLARED = {PLAIN: {"w": {"write": True, "rules": OWNER}, "v": {"write": True, "rules": ITEM},
                    "seen": {"write": True, "rules": {"time": {"from": ["%Y/%m/%d %H:%M:%S"]}}}},
            COMP: {"lot": {"write": True, "rules": {"join": "-"}}, "wafer": {"write": True, "rules": OWNER}},
            AGAIN: {"v": {"write": True, "rules": {"join": "-", "replace": [["x", "xx"]]}}}}
PAGE = 5
PARTS = ("rows", "layers", "overwrites", "history", "outbox")
SAID = ("rows_scanned", "pages", "cells_folded", "layers_folded", "keys_changed", "rows_merged",
        "keys_not_rebuilt", "moves_again", "time_left", "stopped", "stopped_on_moves_again")


def _declare(path, columns):
    path.write_text(json.dumps({"columns": columns}), encoding="utf-8")
    from database import config_watcher
    config_watcher.forget_held()


def _write(db, table, rows, source="f01.csv", by="seed"):
    from database.context import channel

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name=source, updated_by=by,
                                      business_key_val=r.get("k")) for r in rows], silent=True))
    db.commit()


def _sql(db, statement, **params):
    db.execute(text(statement.replace("{s}", '"%s"' % PG_TEST_SCHEMA)), params)


def _seed(db, rules_path):
    _declare(rules_path, {})
    _write(db, NOTATION_ALIAS_TABLE, [{"table_name": PLAIN, "column_name": "w", "written": "WFR.3",
                                       "canonical": "wafer-03"}], source="user", by="op")
    _write(db, PLAIN, [
        {"k": "K01", "w": "wafer . 1", "v": "wafer . 1", "seen": "2026/01/02 03:04:05", "note": "hello", "n": 1},
        {"k": "K02", "w": "wafer-02", "v": "a.b", "seen": "garbage", "note": "x", "n": 2},
        {"k": "K03", "w": "W 3", "v": "a . b (2)", "seen": "2026-01-02T03:04:05+09:00", "n": 3},
        {"k": "K04", "w": "WFR.3", "v": "c.c.c"}, {"k": "K05", "w": "wafer.1"}, {"k": "K06", "w": "wafer.1"},
        {"k": "K07", "w": "wafer.1"}, {"k": "K08", "w": "wafer.1"}, {"k": "K09", "w": "wafer.1"},
        {"k": "K10", "w": "wafer.5"}, {"k": "K11", "note": "7"}, {"k": "K12", "w": "wafer-12"},
        {"k": "K13", "note": "keep"}, {"k": "K14", "w": "wafer-14", "note": "clean"}])
    _write(db, PLAIN, [{"k": "K05", "w": "wafer.1"}], source="f02.csv")          # two layers, one text
    _write(db, PLAIN, [{"k": "K06", "w": "W.2"}], source="f03.csv")              # two texts, the newer wins
    _write(db, PLAIN, [{"k": "K07", "w": "hand.9"}], source="user", by="op")     # a person's layer
    _write(db, PLAIN, [{"k": "K08", "w": "w.4"}], source="f04.csv")              # pinned below: f01 wins
    _write(db, COMP, [{"lot": "L1", "wafer": "wafer.1", "x": "shell of a later holder"},
                      {"lot": "L2", "wafer": "wafer.2", "x": "key moves"},
                      {"lot": "L3", "wafer": "wafer.3", "x": "first of two"},
                      {"lot": "L3", "wafer": "wafer 3", "x": "second of two"},
                      {"lot": "L 5", "wafer": "wafer.5", "x": "not rebuilt"},
                      {"lot": "L1", "wafer": "wafer-01", "x": "holder"},
                      {"lot": "L4", "wafer": "wafer-04", "x": "holder in the page"},
                      {"lot": "L4", "wafer": "wafer.4", "x": "shell in the page"},
                      {"lot": "L9", "wafer": "wafer-09", "x": "padded"},
                      {"lot": "L10", "wafer": "wafer-10", "x": "clean"},
                      {"lot": "7", "wafer": "wafer-07", "x": "number layer"},
                      {"lot": "8", "wafer": "wafer-08", "x": "number layer, x moves"},
                      {"lot": "L12", "wafer": "wafer.12", "x": "key moves in a later page"},
                      {"lot": "L2", "wafer": "wafer 2", "x": "onto a key moved by value a page before"}])
    _write(db, AGAIN, [{"k": "A%02d" % i, "v": "a.%d" % i} for i in range(1, 6)]
           + [{"k": "A06", "v": "bx"}, {"k": "A07", "v": "a.7"}])
    plain = {r.k: r.row_id for r in db.query(models.DYNAMIC_TABLES[PLAIN])}
    comp = {r.x: r.row_id for r in db.query(models.DYNAMIC_TABLES[COMP])}
    _sql(db, "INSERT INTO {s}.cell_overwrites (table_name, row_id, column_name, is_overwrite, updated_by, "
             "manual_priority_source) VALUES (:t, :r, 'w', false, 'op', 'f01.csv')", t=PLAIN, r=plain["K08"])
    _sql(db, "UPDATE {s}.pgqa_nf_plain SET w = 'wafer.1' WHERE row_id = :r", r=plain["K08"])
    _sql(db, "UPDATE {s}.pgqa_nf_plain SET w = 'drifted.7' WHERE row_id = :r", r=plain["K09"])
    _sql(db, "UPDATE {s}.cell_sources SET value = '\"wafer-05\"' WHERE table_name = :t AND row_id = :r "
             "AND column_name = 'w'", t=PLAIN, r=plain["K10"])
    _sql(db, "UPDATE {s}.cell_sources SET value = '7.0' WHERE table_name = :t AND row_id = :r "
             "AND column_name = 'note'", t=PLAIN, r=plain["K11"])
    _sql(db, "INSERT INTO {s}.cell_sources (table_name, row_id, column_name, source_name, value, updated_by) "
             "VALUES (:t, :r, 'note', 'f01.csv', 'null', 'seed')", t=PLAIN, r=plain["K12"])
    _sql(db, "UPDATE {s}.pgqa_nf_plain SET note = '   ' WHERE row_id = :r", r=plain["K13"])
    _sql(db, "UPDATE {s}.cell_sources SET value = '\"   \"' WHERE table_name = :t AND row_id = :r "
             "AND column_name = 'note'", t=PLAIN, r=plain["K13"])
    _sql(db, "INSERT INTO {s}.cell_sources (table_name, row_id, column_name, source_name, value, updated_by) "
             "VALUES (:t, 'orphan-row', 'w', 'f01.csv', '\"wafer.1\"', 'seed')", t=PLAIN)
    _sql(db, "UPDATE {s}.pgqa_nf_comp SET business_key_val = 'L5_old' WHERE row_id = :r", r=comp["not rebuilt"])
    _sql(db, "UPDATE {s}.pgqa_nf_comp SET x = '  padded  ' WHERE row_id = :r", r=comp["padded"])
    _sql(db, "UPDATE {s}.cell_sources SET value = '\"  padded  \"' WHERE table_name = :t AND row_id = :r "
             "AND column_name = 'x'", t=COMP, r=comp["padded"])
    # a key part's layer stored as a JSON number under a clean shown value and key (the ops trap: every
    # such row is `hard`, no key moves)
    for name in ("number layer", "number layer, x moves"):
        _sql(db, "UPDATE {s}.cell_sources SET value = to_json(CAST(lot AS int))::json FROM {s}.pgqa_nf_comp c "
                 "WHERE cell_sources.table_name = :t AND cell_sources.row_id = :r AND c.row_id = :r "
                 "AND column_name = 'lot'", t=COMP, r=comp[name])
    _sql(db, "UPDATE {s}.pgqa_nf_comp SET x = '  x moves  ' WHERE row_id = :r", r=comp["number layer, x moves"])
    _sql(db, "UPDATE {s}.cell_sources SET value = '\"  x moves  \"' WHERE table_name = :t AND row_id = :r "
             "AND column_name = 'x'", t=COMP, r=comp["number layer, x moves"])
    db.commit()
    _declare(rules_path, DECLARED)
    names = {row_id: name for name, row_id in plain.items()}
    names.update({row_id: name for name, row_id in comp.items()})
    names.update({r.row_id: r.k for r in db.query(models.DYNAMIC_TABLES[AGAIN])})
    after = {m.__tablename__: db.query(m.id).order_by(m.id.desc()).limit(1).scalar() or 0
             for m in (models.AuditLog, models.DatabaseOutbox)}
    return names, after


def _state(db, names, after):
    """What a copy holds, every row id put back to its seed name and ids · times · transaction left out."""
    db.expire_all()

    def said(value):
        out = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        for row_id, name in names.items():
            out = out.replace(row_id, name)
        return out

    def outbox(payload):
        payload = {k: v for k, v in payload.items() if k not in ("timestamp", "transaction_id")}
        return said(payload)

    cs, co, al, ob = models.CellSource, models.CellOverwrite, models.AuditLog, models.DatabaseOutbox
    tables = (PLAIN, COMP, AGAIN)
    return {
        "rows": sorted((t, names.get(r.row_id, r.row_id), r.business_key_val,
                        said({c: getattr(r, c) for c in TABLES[t]["column_types"]}))
                       for t in tables for r in db.query(models.DYNAMIC_TABLES[t])),
        # a layer's JSON as stored - a number 7 and a text "7" are two layers
        "layers": sorted((c.table_name, names.get(c.row_id, c.row_id), c.column_name, said(c.source_name),
                          said(json.dumps(c.value, ensure_ascii=False, sort_keys=True)),
                          names.get(c.origin_row_id), c.updated_by)
                         for c in db.query(cs).filter(cs.table_name.in_(tables))),
        "overwrites": sorted((o.table_name, names.get(o.row_id, o.row_id), o.column_name, o.is_overwrite,
                              o.updated_by, o.manual_priority_source)
                             for o in db.query(co).filter(co.table_name.in_(tables))),
        "history": sorted((a.table_name, names.get(a.row_id, a.row_id), a.column_name, said(a.old_value),
                           said(a.new_value), a.source_name, a.updated_by, a.business_key)
                          for a in db.query(al).filter(al.table_name.in_(tables), al.id > after["audit_logs"])),
        "outbox": sorted((e.event_type, e.table_name, e.status, outbox(e.payload))
                         for e in db.query(ob).filter(ob.table_name.in_(tables), ob.id > after["database_outbox"])),
    }


def _counts(stats, names):
    out = {k: stats[k] for k in SAID}
    for key in ("merged", "not_rebuilt"):
        out[key] = sorted(json.dumps({k: names.get(v, v) for k, v in one.items()}, sort_keys=True)
                          for one in stats[key])
    out["again"] = sorted(json.dumps(one, ensure_ascii=False) for one in stats["again"])
    return out


def _public(engine):
    out = {}
    with engine.connect() as conn:
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": "public.%s" % table}).scalar():
                out[table] = conn.execute(text("SELECT count(*) FROM public.%s WHERE table_name = ANY(:t)" % table),
                                          {"t": list(TABLES)}).scalar()
        out["tables"] = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = "
                                          "'public' AND table_name = ANY(:t)"), {"t": list(TABLES)}).scalar()
    return out


@pytest.fixture(scope="module")
def copies(pg_engine, tmp_path_factory):
    from sqlalchemy.orm import sessionmaker

    from database.context import channel, retroactive_run

    url, _ = _resolve_pg_test_url()
    had_alias = NOTATION_ALIAS_TABLE in models.DYNAMIC_TABLES
    tables = dict(TABLES, **{NOTATION_ALIAS_TABLE: PRODUCT_TABLES[NOTATION_ALIAS_TABLE]})
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for t in tables:
        models.DYNAMIC_TABLES[t].__table__.to_metadata(scratch, schema=None)
    emptied = ", ".join('"%s"."%s"' % (PG_TEST_SCHEMA, t) for t in
                        ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox", *tables))
    Session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    rules_path = tmp_path_factory.mktemp("nf") / "notation_rules.json"
    out = {"public_before": _public(pg_engine), "by_value": []}
    real_by_values, real_write = replay._fold_by_values, replay._write_by_values
    out["keys_by_value"] = []

    def by_values(*args, **kwargs):
        answer = real_by_values(*args, **kwargs)
        out["by_value"].append((args[1], len(answer["hard"]), len(answer["cells"]), len(answer["layers"])))
        return answer

    def write(db, table, model, values, tx_id):
        out["keys_by_value"].append((table, len(values["keys"]),
                                     len({row_id for row_id, _column in values["cells"]} & values["hard"])))
        return real_write(db, table, model, values, tx_id)

    def run(db, table, **kwargs):
        with channel(event_constants.CHANNEL_RETROACTIVE), retroactive_run("nf-run"):
            return replay.fold_written_notation(db, table, chunk_size=PAGE, log=lambda m: None, **kwargs)

    with pg_engine.connect() as conn:
        existed = {t for t in tables if conn.execute(text("SELECT to_regclass(:t)"),
                                                     {"t": '"%s"."%s"' % (PG_TEST_SCHEMA, t)}).scalar()}
    with _declared_as_test_database(url), pytest.MonkeyPatch.context() as mp:
        mp.setattr(nn, "NOTATION_RULES_PATH", str(rules_path))
        mp.setattr(replay, "_fold_by_values", by_values)
        # pages of PAGE from the first - the cells below read which page a key lands on (a02ad0f2b: under pages from
        # one row, A = B held and only those two moved)
        mp.setattr(keyset_scan, "FIRST_PAGE", 10 ** 9)
        mp.setattr(replay, "_write_by_values", write)
        scratch.create_all(pg_engine)
        try:
            for copy, dialects in (("A", ()), ("B", replay.FOLD_BY_VALUE_DIALECTS)):
                with pg_engine.begin() as conn:
                    conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
                mp.setattr(replay, "FOLD_BY_VALUE_DIALECTS", dialects)
                db = Session()
                out["schema"] = db.execute(text("SELECT current_schema()")).scalar()
                names, after = _seed(db, rules_path)
                out[copy + "_names"] = names
                out[copy + "_seed"] = _state(db, names, after)
                start = len(out["by_value"])
                for table in (PLAIN, COMP, AGAIN):
                    out[copy, table, "dry"] = _counts(run(db, table), names)
                out[copy + "_after_dry"] = _state(db, names, after)
                for table in (PLAIN, COMP, AGAIN):
                    out[copy, table, "apply"] = _counts(run(db, table, apply=True), names)
                out[copy] = _state(db, names, after)
                for table in (PLAIN, COMP):
                    out[copy, table, "again"] = _counts(run(db, table), names)
                out[copy + "_by_value"] = out["by_value"][start:]
                db.close()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            scratch.drop_all(pg_engine, tables=[scratch.tables["%s.%s" % (PG_TEST_SCHEMA, t)]
                                                for t in tables if t not in existed])
            from database import config_watcher
            config_watcher.forget_held()
            for t in tables:
                crud.TABLE_CONFIG.pop(t, None)
                if t != NOTATION_ALIAS_TABLE or not had_alias:
                    retire_dynamic_model(t)
    out["public_after"] = _public(pg_engine)
    return out


def test_the_writes_land_in_the_scratch_schema_and_public_does_not_move(copies):
    assert copies["schema"] == PG_TEST_SCHEMA
    assert copies["public_after"] == copies["public_before"], (copies["public_before"], copies["public_after"])


def test_b_folds_by_value_and_a_does_not(copies):
    """So the comparison below is of two paths, not of one path twice."""
    assert copies["A_by_value"] == []
    by_table = {}
    for table, hard, cells, layers in copies["B_by_value"]:
        one = by_table.setdefault(table, [0, 0, 0])
        one[0], one[1], one[2] = one[0] + hard, one[1] + cells, one[2] + layers
    assert by_table[PLAIN][0] == 0 and by_table[PLAIN][1] > 10, "every PLAIN row by value"
    assert by_table[COMP][0] >= 6 and by_table[COMP][1] >= 1, "the key rows judged by the row path"
    written = [(keys, hard) for table, keys, hard in copies["keys_by_value"] if table == COMP]
    assert sum(keys for keys, _hard in written) == 2, "the keys that move onto nothing are written by value"
    assert sum(hard for _keys, hard in written) >= 3, "and so are the hard rows whose cells move"


def test_the_row_path_copy_folds_the_seed(copies):
    """The reference itself, so a comparison of two empty answers cannot pass."""
    rows = {name: json.loads(cells) for t, name, _key, cells in copies["A"]["rows"] if t == PLAIN}
    assert (rows["K01"]["w"], rows["K01"]["v"]) == ("wafer-01", "wafer.1"), "one spelling, two rules"
    assert rows["K04"]["w"] == "wafer-03", "the alias"
    assert rows["K06"]["w"] == "W-02", "the newer of two texts"
    assert rows["K07"]["w"] == "hand-09", "the person's layer"
    assert rows["K08"]["w"] == "wafer-01", "the pin"
    assert rows["K09"]["w"] == "wafer-01", "a drifted shown value takes what its layers decide"
    assert rows["K10"]["w"] == "wafer-05", "a stale shown value is folded"
    assert rows["K13"]["note"] is None, "a blank"
    assert ("pgqa_nf_plain", "orphan-row", "w", "f01.csv", "\"wafer.1\"", None, "seed") in copies["A"]["layers"]
    comp = copies["A", COMP, "apply"]
    assert (comp["keys_changed"], comp["rows_merged"], comp["keys_not_rebuilt"]) == (3, 4, 1)
    keys = {name: key for t, name, key, _cells in copies["A"]["rows"] if t == COMP}
    assert (keys["key moves"], keys["key moves in a later page"]) == ("L2_wafer-02", "L12_wafer-12")
    assert "onto a key moved by value a page before" not in keys, "merged into the L2 row"
    lot = {name: value for t, name, column, _s, value, _o, _u in copies["A"]["layers"] if t == COMP and column == "lot"}
    assert (lot["number layer"], lot["number layer, x moves"]) == ('"7"', '"8"'), "a number layer of a key part"
    assert keys["number layer, x moves"] == "8_wafer-08"
    assert copies["A", PLAIN, "dry"]["time_left"] == {"unmatched": 2, "zoned": 2}
    assert copies["A"]["history"] and copies["A"]["outbox"]


@pytest.mark.parametrize("part", PARTS)
def test_folding_by_value_leaves_what_the_row_path_leaves(copies, part):
    assert copies["A"][part] != copies["A_seed"][part] or part == "overwrites", "CANARY: A moved %s" % part
    assert copies["B"][part] == copies["A"][part]


@pytest.mark.parametrize("table", [PLAIN, COMP, AGAIN])
@pytest.mark.parametrize("run", ["dry", "apply"])
def test_the_counts_are_the_row_paths(copies, table, run):
    assert copies["B", table, run] == copies["A", table, run]


def test_the_dry_run_writes_nothing(copies):
    for copy in ("A", "B"):
        assert copies[copy + "_after_dry"] == copies[copy + "_seed"], copy


def test_a_rerun_folds_nothing(copies):
    for table in (PLAIN, COMP):
        again = copies["B", table, "again"]
        assert copies["B", table, "apply"]["cells_folded"] > 0, "CANARY: the first run folded"
        assert (again["cells_folded"], again["layers_folded"], again["keys_changed"], again["rows_merged"]) == \
            (0, 0, 0, 0), table


def test_a_value_that_moves_again_stops_both_before_its_page(copies):
    dry, run = copies["B", AGAIN, "dry"], copies["B", AGAIN, "apply"]
    assert dry["moves_again"] == 2, "the cell and its layer"
    assert run["stopped_on_moves_again"] and run["cells_folded"] == PAGE, "the first page is written"
    rows = {name: json.loads(cells)["v"] for t, name, _key, cells in copies["B"]["rows"] if t == AGAIN}
    assert (rows["A01"], rows["A06"], rows["A07"]) == ("a-1", "bx", "a.7")
