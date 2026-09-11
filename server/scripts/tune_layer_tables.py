# -*- coding: utf-8 -*-
"""층 표의 배큠을 «파이썬 한 줄»로 — 무엇이 돌고 있나, 무엇을 바꿀 수 있나.

🔴 WHY THIS EXISTS (S-170). The owner cannot issue SQL, and the question was
「배큠 계속 나오는데 어케해」. A remedy that is a statement is not a remedy; this is the
command.

🔴 AND IT DOES NOT DECIDE ANYTHING. The owner's own correction (2026-09-11) removed the
obvious story: 「dead 는 거의 0 이야 다」. With no dead tuples a resident autovacuum is NOT
reclaiming space, so the two remaining candidates are autoANALYZE (an INSERT stream fills
the analyze threshold on a large table) and insert-triggered or anti-wraparound VACUUM
(PG13+ walks heap and indexes with no dead tuple in sight). Those are tuned by DIFFERENT
knobs, and nothing here guesses which: the dry run prints WHICH KIND actually ran, and the
operator names the knob. A script that picked for them would be the confident wrong number
this file exists to replace.

⚠️ THE COLLECTOR'S COUNTERS CAN BE LOST, AND THAT IS NOT A FOOTNOTE.
`pg_stat_user_tables` lives in the statistics collector's file, which is discarded on an
unclean shutdown and zeroed by `pg_stat_reset()`. The TABLE is untouched when that happens
-- only the bookkeeping about it disappears. Measured on this deployment 2026-08-06 by
`diagnose_db_health`: `cell_sources` read 5,722 live rows against a real 13,709,607, and a
report computed a confident bloat verdict out of a denominator that was simply missing.
So every counter below is printed BESIDE `pg_class.reltuples`/`relpages`, which vacuum and
analyze maintain rather than the collector, and the disagreement is NAMED instead of being
folded into an average.

⚠️ DRY RUN IS THE DEFAULT, and the read is pinned read-only, which is the shape every
operator script in this tree uses. `--apply`, `--reset` and `--vacuum` change something and
each says exactly what it ran.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text                                          # noqa: E402

import db_safety                                                     # noqa: E402

# 🔴 THE CONSOLE IS THE OUTPUT DEVICE, SO IT IS PART OF THE TOOL. Measured on this box the
# first live run died with `UnicodeEncodeError: 'cp949' codec cannot encode U+2014` before
# printing one table: a Korean Windows console defaults to cp949, and every operator line
# in this tree carries characters it does not have. A diagnostic that crashes on its own
# report is worse than no diagnostic -- the operator reads a traceback and concludes the
# database is broken. `errors="replace"` rather than a raise, because a mangled dash is a
# far smaller failure than a lost report.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

#: The three tables the layering engine writes on every ingest. Defaults, not a fixture:
#: `--table` takes any relation, because the next deployment's hot table is not this one.
LAYER_TABLES = ("cell_sources", "cell_overwrites", "audit_logs")

#: 🔴 THE THREE `--apply` WRITES, AND WHY THEY ARE THESE. A big table's autovacuum is paced
#: by a cost budget, and at the shipped delay it can spend longer on one pass than the
#: interval between passes -- so the worker is never NOT running and an operator reads that
#: as 「배큠이 계속 나온다」. Lowering the delay and raising the limit make ONE PASS FINISH;
#: the scale factor makes it start on a sensible fraction of a large table rather than on
#: the default 20%, which on ten million rows is two million dead tuples of waiting.
#: ⛔ THIS IS NOT 「덜 자주 돌게」. It is 「한 바퀴가 끝나게」, which is the opposite change.
#: ⚠️ `cost_delay` IS AN INTEGER OF MILLISECONDS HERE, NOT `2ms`. The GUC of the same name
#: takes a unit suffix and the storage parameter does not -- measured on this box, the
#: first live `--apply` came back
#: 「오류: 숫자 뒤에 쓸모 없는 값이 더 있음, "2ms" 부근」. The suffix is accepted from an
#: operator and normalised below, because `2ms` is the spelling the documentation and the
#: order both use and refusing it would be this tool being right at their expense.
VACUUM_DEFAULTS = {
    "autovacuum_vacuum_cost_delay": "2",
    "autovacuum_vacuum_cost_limit": "2000",
    "autovacuum_vacuum_scale_factor": "0.02",
}

#: Named ONLY when the operator asks, because which one to move is what the dry run is for.
#: `analyze_scale_factor` is the answer when the dry run shows autoANALYZE running;
#: `vacuum_insert_scale_factor` is the answer when it shows an insert-triggered VACUUM.
OPTIONAL_SETTINGS = {
    "analyze_scale_factor": "autovacuum_analyze_scale_factor",
    "insert_scale_factor": "autovacuum_vacuum_insert_scale_factor",
}

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quoted_identifier(name: str) -> str:
    """A relation name safe to interpolate, or a refusal.

    `ALTER TABLE` and `VACUUM` take no bind parameters, so the name is interpolated and
    therefore has to be judged first. Refused by pattern rather than escaped: every
    relation this tool is pointed at is a plain identifier, and accepting anything else
    would mean this file deciding what a quoted name means.
    """
    if not _IDENTIFIER.match(name or ""):
        raise ValueError(
            f"'{name}' 은(는) 평범한 테이블 이름이 아닙니다. "
            f"영문자/숫자/밑줄만 쓰는 이름을 지정하세요.")
    return '"%s"' % name


def autovacuum_kind(query: str) -> str:
    """Which KIND of autovacuum this worker is running, in words (owner, 2026-09-11).

    🔴 THE WORD IS THE ANSWER. 「배큠이 돈다」 covers four different jobs tuned by four
    different knobs, and PostgreSQL already writes which one it is into the worker's query
    text. Reading it is the whole discriminator; inferring it from dead-tuple counts is
    what produced the wrong story this tool was written to replace.
    """
    lowered = (query or "").lower()
    marker = "autovacuum:"
    if marker not in lowered:
        return "not an autovacuum worker"
    # ⛔ THE VERB IS READ, NOT SEARCHED FOR. `"vacuum" in query` is true of every line here
    # -- the PREFIX contains it -- so a substring test called every ANALYZE a
    # VACUUM + ANALYZE, and a relation named `vacuum_log` would have done the same in
    # reverse. The job words are the first one or two tokens after the prefix.
    job = lowered.split(marker, 1)[1].strip()
    if "to prevent wraparound" in job:
        return "VACUUM (anti-wraparound)"
    words = job.split()
    if words[:1] == ["vacuum"]:
        return "VACUUM + ANALYZE" if words[1:2] == ["analyze"] else "VACUUM"
    if words[:1] == ["analyze"]:
        return "ANALYZE"
    return "unknown"


def counter_note(n_live, reltuples) -> str:
    """⚠️ 「이 수를 믿어도 되나」 — 빈 문자열이면 두 출처가 대체로 같다는 뜻.

    The collector's `n_live_tup` and the catalogue's `reltuples` are maintained by
    different things, so a large gap means the collector's file was reset and every counter
    beside it is an artefact. Said in words rather than folded into a ratio: a confident
    number computed from a missing denominator already cost this project a round.
    """
    try:
        live = float(n_live or 0)
        catalogue = float(reltuples or 0)
    except (TypeError, ValueError):
        return ""
    if catalogue <= 0:
        return "" if live > 0 else "  ⚠️ 두 출처 모두 0 — 아직 한 번도 ANALYZE 되지 않았을 수 있음"
    if live <= 0 or live * 10 < catalogue:
        return ("  ⚠️ 수집기 카운터가 카탈로그와 크게 어긋남 — 통계가 리셋된 뒤일 수 있고, "
                "그렇다면 이 줄의 n_dead/last_* 는 «믿을 수 없습니다»")
    return ""


def milliseconds(value: str) -> str:
    """`2ms` -> `2`. A storage parameter takes the bare integer; the GUC takes the suffix."""
    text_value = str(value).strip()
    return text_value[:-2].strip() if text_value.lower().endswith("ms") else text_value


def setting_values(args) -> dict:
    """The reloptions `--apply` writes: the three defaults, plus what was NAMED."""
    settings = {
        "autovacuum_vacuum_cost_delay": milliseconds(args.cost_delay),
        "autovacuum_vacuum_cost_limit": args.cost_limit,
        "autovacuum_vacuum_scale_factor": args.vacuum_scale_factor,
    }
    for flag, option in OPTIONAL_SETTINGS.items():
        value = getattr(args, flag, None)
        if value is not None:
            settings[option] = value
    return settings


def set_sql(table: str, settings: dict) -> str:
    body = ", ".join(f"{name} = {settings[name]}" for name in sorted(settings))
    return f"ALTER TABLE {quoted_identifier(table)} SET ({body})"


def reset_sql(table: str, names) -> str:
    body = ", ".join(sorted(names))
    return f"ALTER TABLE {quoted_identifier(table)} RESET ({body})"


_STAT_SQL = """
    SELECT s.relname,
           s.n_live_tup, s.n_dead_tup,
           s.n_ins_since_vacuum, s.n_mod_since_analyze,
           s.last_autovacuum, s.autovacuum_count,
           s.last_autoanalyze, s.autoanalyze_count,
           c.reltuples::bigint AS reltuples, c.relpages,
           c.reloptions
      FROM pg_stat_user_tables s
      JOIN pg_class c ON c.oid = s.relid
     WHERE s.relname = ANY(:tables)
     ORDER BY c.relpages DESC
"""

_RUNNING_SQL = """
    SELECT a.pid, a.query, a.state, a.backend_start,
           p.relid::regclass::text AS relation, p.phase,
           p.heap_blks_scanned, p.heap_blks_total, p.index_vacuum_count
      FROM pg_stat_activity a
      LEFT JOIN pg_stat_progress_vacuum p ON p.pid = a.pid
     WHERE a.query ILIKE 'autovacuum:%' OR p.pid IS NOT NULL
     ORDER BY a.backend_start
"""


def report(conn, tables) -> None:
    """① 기본 동작 — 값만 낸다. 판단은 사람이 한다."""
    rows = conn.execute(text(_STAT_SQL), {"tables": list(tables)}).fetchall()
    found = {row.relname for row in rows}
    print("== 층 표 상태 ==")
    for name in tables:
        if name not in found:
            print(f"{name}: pg_stat_user_tables 에 없음 (이 데이터베이스의 표가 아닙니다)")
    for row in rows:
        autovacuum_options = [
            option for option in (row.reloptions or [])
            if str(option).startswith("autovacuum_")]
        print(
            f"\n{row.relname}\n"
            f"  live {row.n_live_tup:,} · dead {row.n_dead_tup:,} "
            f"· 카탈로그 reltuples {row.reltuples:,} · relpages {row.relpages:,}"
            f"{counter_note(row.n_live_tup, row.reltuples)}\n"
            f"  vacuum 이후 INSERT {row.n_ins_since_vacuum:,} "
            f"· analyze 이후 변경 {row.n_mod_since_analyze:,}\n"
            f"  last_autovacuum {row.last_autovacuum or 'never'} (누적 {row.autovacuum_count})"
            f" · last_autoanalyze {row.last_autoanalyze or 'never'}"
            f" (누적 {row.autoanalyze_count})\n"
            f"  현재 reloptions: {autovacuum_options or '(없음 — 서버 기본값)'}")

    print("\n== 지금 도는 것 ==")
    running = conn.execute(text(_RUNNING_SQL)).fetchall()
    if not running:
        print("autovacuum 워커 없음 · 진행 중인 VACUUM 없음")
        return
    for row in running:
        line = f"pid {row.pid} · {autovacuum_kind(row.query)}"
        if row.relation:
            scanned, total = row.heap_blks_scanned or 0, row.heap_blks_total or 0
            share = f" {scanned * 100 // total}%" if total else ""
            line += (f" · {row.relation} · phase {row.phase}"
                     f" · heap {scanned:,}/{total:,}{share}"
                     f" · index pass {row.index_vacuum_count}")
        print(line)
        # ⛔ THE QUERY TEXT IS PRINTED VERBATIM AND NOT SUMMARISED. It is the only place
        # PostgreSQL says which job this is, and a paraphrase of it is a place to be wrong.
        print(f"    {row.query}")


def _write_engine():
    """A THROWAWAY engine with its own pool, outside the application's (S-167).

    `--vacuum` needs AUTOCOMMIT -- `VACUUM` cannot run inside a transaction block -- and
    the lesson that cost this project a day is that switching a connection BORROWED from
    the app pool leaves it switched for whoever checks it out next. An engine of our own
    has no next checkout to poison, and it is disposed when the run ends.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from database.database import SQLALCHEMY_DATABASE_URL

    return create_engine(
        SQLALCHEMY_DATABASE_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT",
        connect_args={"application_name": "assy_tune_layer_tables"})


def run_statements(statements) -> int:
    """Print every statement, then run it. The operator cannot write SQL; they can READ
    what ran, and that is the difference between a command and a black box."""
    engine = _write_engine()
    try:
        with engine.connect() as conn:
            for statement in statements:
                print("RUN " + statement)
                conn.execute(text(statement))
    finally:
        engine.dispose()
    print(f"\n{len(statements)}개 문장을 실행했습니다. "
          f"현재 값은 인자 없이 다시 돌려 확인하세요.")
    return 0


def vacuum(tables) -> int:
    """③ 한 표씩, VERBOSE 로. 진행은 인자 없는 실행의 「지금 도는 것」에서도 보입니다."""
    engine = _write_engine()
    try:
        for name in tables:
            statement = f"VACUUM (VERBOSE, ANALYZE) {quoted_identifier(name)}"
            print(f"\n-- {name} --\nRUN {statement}")
            # 🔴 ONE CONNECTION PER TABLE, closed before the next. A VACUUM on a large
            # relation is long, and holding one connection across all three would keep a
            # slot open for the whole run for no gain.
            raw = engine.raw_connection()
            try:
                cursor = raw.cursor()
                cursor.execute(statement)
                cursor.close()
                # ⚠️ VERBOSE OUTPUT ARRIVES AS NOTICES, NOT AS ROWS. Reading it off the
                # driver is the only way to show the operator what the pass actually did;
                # a run that printed nothing would look identical to one that did nothing.
                for notice in list(getattr(raw, "notices", []) or []):
                    print("   " + str(notice).rstrip())
            finally:
                raw.close()
    finally:
        engine.dispose()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--table", action="append", dest="tables", metavar="NAME",
                        help="대상 표 (여러 번 지정 가능). 기본: " + " ".join(LAYER_TABLES))
    parser.add_argument("--apply", action="store_true",
                        help="② 표별 autovacuum reloptions 를 지정합니다")
    parser.add_argument("--reset", action="store_true",
                        help="④ 이 스크립트가 지정하는 reloptions 를 지웁니다")
    parser.add_argument("--vacuum", action="store_true",
                        help="③ VACUUM (VERBOSE, ANALYZE) 를 한 표씩 돌립니다")
    parser.add_argument("--cost-delay",
                        default=VACUUM_DEFAULTS["autovacuum_vacuum_cost_delay"],
                        help="밀리초. `2` 도 `2ms` 도 받습니다")
    parser.add_argument("--cost-limit",
                        default=VACUUM_DEFAULTS["autovacuum_vacuum_cost_limit"])
    parser.add_argument("--vacuum-scale-factor",
                        default=VACUUM_DEFAULTS["autovacuum_vacuum_scale_factor"])
    # ⛔ NO DEFAULTS ON THESE TWO, AND THAT IS THE OWNER'S RULE (2026-09-11):
    # 「무엇을 올릴지는 dry-run 이 «어느 종류가 돌았나»를 보여 준 뒤 사람이 고르는 인자로
    #  — 자동 판단 금지」. A default here would BE the automatic judgement.
    parser.add_argument("--analyze-scale-factor", default=None,
                        help="autoANALYZE 가 계속 돌 때 «사람이» 지정합니다 (예: 0.02)")
    parser.add_argument("--insert-scale-factor", default=None,
                        help="insert 유발 VACUUM 이 계속 돌 때 «사람이» 지정합니다 (예: 0.05)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    tables = tuple(args.tables or LAYER_TABLES)
    for name in tables:
        quoted_identifier(name)                  # 이름을 «먼저» 거절한다

    acting = [flag for flag in ("apply", "reset", "vacuum") if getattr(args, flag)]
    if len(acting) > 1:
        # ⛔ 「무엇을 했는지」가 한 낱말이어야 한다. 두 모드를 한 번에 받으면 그 답이 둘이 된다.
        print(f"--{' --'.join(acting)} 는 한 번에 하나만 쓸 수 있습니다.", file=sys.stderr)
        return 2

    if args.vacuum:
        return vacuum(tables)
    if args.apply:
        settings = setting_values(args)
        return run_statements([set_sql(name, settings) for name in tables])
    if args.reset:
        names = set(VACUUM_DEFAULTS) | set(OPTIONAL_SETTINGS.values())
        return run_statements([reset_sql(name, names) for name in tables])

    # ① 기본: 읽기 전용으로 핀 박은 연결에서 «값만» 낸다. 판단은 사람이 한다.
    engine = db_safety.open_readonly_engine(application_name="assy_tune_layer_tables")
    if engine.dialect.name != "postgresql":
        print(f"이 스크립트는 PostgreSQL 전용입니다 (지금 연결: {engine.dialect.name}).",
              file=sys.stderr)
        engine.dispose()
        return 2
    conn = db_safety.open_readonly_connection(engine)
    try:
        report(conn, tables)
    finally:
        db_safety.close_readonly_connection(conn)
        engine.dispose()
    print("\n바꾸려면: --apply (기본 셋) · 되돌리려면: --reset · 한 번 돌리려면: --vacuum")
    print("어느 종류가 돌고 있는지는 위 「지금 도는 것」이 말합니다 — "
          "ANALYZE 면 --analyze-scale-factor, insert 유발 VACUUM 이면 "
          "--insert-scale-factor 를 «값과 함께» 지정하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
