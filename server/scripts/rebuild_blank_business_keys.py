"""블랭크 컴포넌트가 든 `business_key_val`을 원본 컬럼에서 **다시 조립**한다.

배경 (제품 소유자 2026-08-11, 운영 실측):
    `add_business_key_unique_index.py`가 한 표에서 중복 키 90,000 / 잉여 행 170,000 /
    전체 370,000을 보고했다. 중복 그룹 안 행이 전체의 70%, 키당 평균 2.89행 —
    경합 사고라면 정확히 2가 나오므로 그 모양이 아니다. 실제 원인은 **키 컴포넌트가
    비어 있던 시절의 잔재**이고, 신규 발생은 `818c9c0`이 이미 막았다.

    `818c9c0`의 본문이 그 기전을 적어 놨다 — "push 1은 네 행에 키 넷, push 2는 네 행에
    키 제로, push 3은 여덟 행". 키를 잃은 행은 업서트가 찾지 못해 **새 행으로 다시
    들어온다.** 그래서 한 그룹은 서로 다른 행이 아니라 **같은 논리적 행의 재입고**다.

🔴 그래서 이 스크립트는 지우지 않는다. 재조립이 성공하면 각 행이 제 키를 되찾아
   **중복이 스스로 풀린다.** 병합도 삭제도 필요 없어진다. 재조립으로 안 풀리는 그룹만
   사람이 판정하면 되고, 그 목록이 이 스크립트의 출력이다.

⚠️ 조합은 `crud.assemble_composite_business_key`가 정본이다.
   [check_missing_business_key.py](./check_missing_business_key.py)가 같은 이유로
   조합을 거부했다 — 여기서 `a || '_' || b`를 쓰면 그것이 **두 번째 철자**가 되고,
   조합 규칙이 바뀌는 날 이 스크립트만 옛 규칙으로 남는다. 그래서 SQL로 잇지 않고
   그 함수를 부른다.

🔴 The default pass is read-only, and the SERVER is what enforces it - not the absence
   of an UPDATE in the code below, which an operator would otherwise have to take on
   trust. Use `--apply` to write.

   ⚠️ THIS PARAGRAPH USED TO CALL THAT PROTECTION "STRUCTURAL" AND THE WORD WAS WRONG.
   What stood here was `SET SESSION default_transaction_read_only = on`, issued on a
   connection that `execution_options` had already put into AUTOCOMMIT. Measured on the
   isolated `assy_qa` (PostgreSQL 18.3 / SQLAlchemy 2.0.49 / psycopg2 2.9.11) on
   2026-08-13, IN THAT ORDER IT DID ENGAGE: writes were refused, before and after a
   rollback. Nothing was ever written that should not have been.

   It engaged only BECAUSE the connection happened to be in autocommit. Under the
   ordinary isolation level the identical statement lands inside an implicit
   transaction that began under the old default and keeps it - `transaction_read_only`
   stays `off`, a CREATE is ACCEPTED, and `default_transaction_read_only` reads `on`
   the whole time. Nothing in this file read the flag back, so the two arrangements
   were indistinguishable from inside it. A safety property resting on an unrelated
   setting that nobody declared, verified by nothing, is not structural.

   It is structural now: armed as a CONNECTION OPTION (independent of isolation level)
   and refused unless PostgreSQL itself reports `transaction_read_only = on`. See the
   guard section below the imports.

세 가지를 먼저 답한 뒤에야 쓴다:

  ① 재료가 있는가   — `composite_key_source` 컬럼이 비어 있으면 어떤 스크립트도 못 만든다
  ② 값이 바뀌는가   — 새 키가 옛 키와 같으면 그 행은 이 결함이 아니다
  ③ 충돌하는가      — 새 키가 **다른 행**의 키와 같으면 그 둘은 진짜 중복이고,
                      **사람이 어느 쪽을 남길지 정해야 한다.** 그런 행은 건너뛴다

Usage
-----
    python server/scripts/rebuild_blank_business_keys.py --table <표>
    python server/scripts/rebuild_blank_business_keys.py --table <표> --apply
"""

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import text                                    # noqa: E402
from database import crud, models, schemas                     # noqa: E402

STATEMENT_TIMEOUT_MS = 120_000
CHUNK = 1_000


# =============================================================================
# The read-only guard
# =============================================================================
# 🔴 THIS SPELLING IS NOT NEW AND MUST NOT BE RE-INVENTED. It is the one
# `server/scripts/diagnose_wal_headroom.py` (class `RO`) and
# `server/scripts/diagnose_slow_after_ingest.py` already use: the setting goes in as a
# CONNECTION OPTION, which the server applies before this session's first transaction
# exists and re-applies to every transaction after it. That is what makes it survive a
# rollback, and what makes it independent of the isolation level. See the module
# docstring for what stood here before and what was measurably true about it.
#
# `transaction_read_only` is the flag PostgreSQL enforces and it is READ BACK below
# rather than trusted. `default_transaction_read_only` is deliberately NOT what gets
# checked: it reads `on` even in the arrangement that accepts writes.
#
# `statement_timeout` moves in here from the `SET` it used to be. It covered the
# counting pass and only the counting pass before (the writes went out on other
# connections), and it still does.
READONLY_OPTIONS = ("-c default_transaction_read_only=on "
                    f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                    "-c client_encoding=utf8")

READONLY_REFUSAL = "[read-only guard] REFUSED"


def open_readonly_engine(url: str = None):
    """An engine every one of whose transactions is read-only, armed at connect time.

    `NullPool` is load-bearing rather than tidiness: a connection carrying this flag
    must never re-enter a pool that something else draws from. It is also what retires
    the `invalidate()` this script used to need on the way out - measured on `assy_qa`,
    a pinned connection returned to a pooled engine hands the NEXT checkout a session
    that still refuses writes, so a missed `invalidate()` would have broken the next
    user of the application pool. An engine of our own has no next checkout.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    if url is None:
        from database.database import SQLALCHEMY_DATABASE_URL
        url = SQLALCHEMY_DATABASE_URL
    return create_engine(
        url, poolclass=NullPool,
        connect_args={"options": READONLY_OPTIONS,
                      "application_name": "assy_rebuild_bk_check"})


def assert_readonly(conn):
    """Refuse unless POSTGRESQL ITSELF reports that this connection cannot write."""
    try:
        armed = conn.execute(text("SHOW transaction_read_only")).scalar()
    except Exception as exc:
        raise RuntimeError(
            f"{READONLY_REFUSAL}: `transaction_read_only` could not be read from this "
            f"connection ({type(exc).__name__}: {str(exc).strip().splitlines()[0]}). "
            f"This is a PostgreSQL operator script and it will not run a pass it "
            f"cannot prove is read-only.") from exc
    if str(armed).lower() != "on":
        raise RuntimeError(
            f"{READONLY_REFUSAL}: PostgreSQL reports transaction_read_only={armed!r} "
            f"on the connection this run counts with. Refusing to run a check pass "
            f"that is not actually protected.")
    return conn


def assert_writable(conn):
    """The mirror, for `--apply`. Fails before the first chunk instead of during it."""
    armed = conn.execute(text("SHOW transaction_read_only")).scalar()
    if str(armed).lower() != "off":
        raise RuntimeError(
            f"{READONLY_REFUSAL} (inverted): --apply was asked for but PostgreSQL "
            f"reports transaction_read_only={armed!r} on the connection that would do "
            f"the writing. Nothing was attempted.")
    return conn


def open_readonly_connection(engine):
    """THE ONLY DOOR to a counting-pass connection: connect, then prove it, or refuse."""
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        assert_readonly(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def _blank_parts(value, sep: str) -> bool:
    """참고용 표시. **판정에 쓰지 않는다.**

    🔴 처음엔 이것이 관문이었고 틀렸다. 「옛 조합기가 빈 컴포넌트를 «남겼을» 것」이라고
    가정했는데, 빈 조각을 **아예 빼고** 이었다면 `a_b`가 그냥 `a`가 되어 빈 조각이
    하나도 없다. 그 가정 때문에 운영 실행에서 blank 가 0으로 떴다.

    손상의 «모양»을 맞히려 하지 않는다. 전부 재조립해서 **옛 키와 다른 것**을 찾으면
    모양과 무관하게 걸린다.
    """
    if value is None:
        return False
    return any(p == "" for p in str(value).split(sep))


def _compose(table: str, row: dict, sources: list):
    """정본 조합기를 통해서만 키를 만든다. 재료가 모자라면 None."""
    item = schemas.GeneralUpdateItem(row_id=None, business_key_val=None,
                                     updates={c: row.get(c) for c in sources})
    if not crud.assemble_composite_business_key(table, item):
        return None
    return item.business_key_val


def run(table: str, apply: bool) -> dict:
    cfg = crud.TABLE_CONFIG.get(table) or {}
    sources = cfg.get("composite_key_source") or []
    sep = cfg.get("composite_key_separator", "_")
    if not sources:
        print(f"!! '{table}' 는 composite_key_source 를 선언하지 않았다 - 대상이 아니다")
        return {"skipped": True}

    # 동적 모델은 서버 기동 때 만들어진다. 이 스크립트는 생 SQL 과 config 만 쓰지만,
    # 조합기가 언젠가 모델을 보게 되면 조용히 갈리므로 형제 스크립트들과 같은 줄로 연다.
    models.init_dynamic_models(crud.TABLE_CONFIG)

    print(f"=== {table} | {'APPLY' if apply else 'CHECK (읽기 전용)'} ===")
    print(f"조합 재료: {sources}  구분자: {sep!r}\n")

    # THE WRITABLE ENGINE IS RESOLVED ONLY WHEN SOMETHING IS GOING TO BE WRITTEN. A
    # check run never imports it, never opens it, and therefore has no writable
    # connection anywhere in this process for the counting pass to reach for.
    write_engine = None
    if apply:
        from database.database import engine as _app_engine
        write_engine = _app_engine
        # 🔴 PROVE THE APPLY PATH BEFORE THE COUNTING PASS, NOT AFTER IT. The trap is
        # already recorded in the sibling `dedupe_business_key_rows.py`: its read-only
        # pass was raw SQL while its write path needed `models.init_dynamic_models`, so
        # the check ran clean and only `--apply` died. The general shape is "the check
        # exercised less setup than the apply needs". Here that setup is the assembler
        # (`_compose`, run over every row by the counting pass below), the dynamic
        # models (initialised above), and a connection that PostgreSQL will accept
        # writes on - which is what this asks, up front, on a connection it then drops.
        with write_engine.connect() as w:
            assert_writable(w)

    # The counting pass gets a connection PROVEN read-only by the server, in BOTH modes
    # - `--apply` does not make the counting half writable, it only adds a second,
    # separate connection that writes.
    ro_engine = open_readonly_engine()
    try:
        conn = open_readonly_connection(ro_engine)
    except BaseException:
        ro_engine.dispose()
        raise
    try:
        cols = ", ".join(f'"{c}"' for c in ["row_id", "business_key_val"] + sources)
        # 🔴 NULL 키도 대상이다. 처음엔 `WHERE business_key_val IS NOT NULL` 로 걸렀는데
        #    그것이 정확히 고쳐야 할 행들을 빼고 있었다 — 제품 소유자가 운영에서 확인.
        #    NULL 은 유니크 인덱스를 막지도 않으므로 「중복 키」와는 **다른 결함**이고,
        #    둘 다 같은 연산(원본 컬럼에서 재조립)으로 풀린다.
        rows = conn.execute(text(f'SELECT {cols} FROM public."{table}"')).mappings().all()

        # 살아 있는 키 전부. 새 키가 이 안에 있고 주인이 내가 아니면 그것이 충돌이다.
        # NULL 은 넣지 않는다 - 여러 행이 공유하므로 주인을 정할 수 없고, 애초에
        # 유니크 제약의 대상이 아니다.
        owner = {r["business_key_val"]: r["row_id"]
                 for r in rows if r["business_key_val"] is not None}

        stat = {"scanned": len(rows), "null_key": 0, "blank_shape": 0,
                "no_material": 0, "unchanged": 0, "collides": 0,
                "rebuilt": 0, "failed": 0}
        collide_sample, pending, empty_by_col = [], [], {}

        for r in rows:
            # 🔴 관문 없이 전부 재조립한다. 손상의 모양을 미리 맞히려 들면
            #    (예: "빈 컴포넌트가 남았을 것") 그 모양이 아닌 손상을 통째로 놓친다.
            if r["business_key_val"] is None:
                stat["null_key"] += 1             # 표시일 뿐 관문이 아니다
            elif _blank_parts(r["business_key_val"], sep):
                stat["blank_shape"] += 1          # 이것도 마찬가지
            new = _compose(table, r, sources)
            if new is None:
                stat["no_material"] += 1          # ② 사람이 값을 넣어야 한다
                # 🔴 「못 만든다」로 끝내지 않는다 - **어느 컬럼이 비어서** 못 만드는지
                #    세어 둔다. 그 이름이 없으면 운영자는 370,000 을 손에 들고
                #    다음에 무엇을 할지 알 수 없다.
                empty = [c for c in sources
                         if r.get(c) is None or str(r.get(c)).strip() == ""]
                for c in (empty or ["(재료는 다 찼는데 조합기가 거절)"]):
                    empty_by_col[c] = empty_by_col.get(c, 0) + 1
                continue
            if new == r["business_key_val"]:
                stat["unchanged"] += 1
                continue
            holder = owner.get(new)
            if holder is not None and holder != r["row_id"]:
                stat["collides"] += 1             # ③ 진짜 중복 - 사람이 정한다
                if len(collide_sample) < 5:
                    collide_sample.append(r["row_id"])
                continue
            pending.append((r["row_id"], new))
            owner[new] = r["row_id"]              # 같은 실행 안에서의 충돌도 잡는다

        if apply:
            for i in range(0, len(pending), CHUNK):
                chunk = pending[i:i + CHUNK]
                # A different engine from the one `conn` came from. `conn` cannot run
                # this statement and PostgreSQL, not this file, is what says so.
                with write_engine.begin() as w:
                    for row_id, new in chunk:
                        w.execute(text(
                            f'UPDATE public."{table}" SET business_key_val = :k '
                            f'WHERE row_id = :r AND business_key_val IS DISTINCT FROM :k'
                        ), {"k": new, "r": row_id})
                stat["rebuilt"] += len(chunk)
                print(f"  .. {stat['rebuilt']}/{len(pending)}")
        else:
            stat["rebuilt"] = 0

        print(f"\n{'항목':22s} {'건수':>10s}")
        for k in ("scanned", "null_key", "blank_shape", "no_material",
                  "unchanged", "collides"):
            print(f"{k:22s} {stat[k]:10d}")
        print(f"{'rebuildable' if not apply else 'rebuilt':22s} "
              f"{len(pending) if not apply else stat['rebuilt']:10d}")

        if stat["collides"]:
            print(f"\n🔴 충돌 {stat['collides']}건은 건너뛰었다 - 재조립해도 다른 행과 같은 "
                  f"키가 되므로 **진짜 중복**이다. 어느 쪽을 남길지는 사람이 정한다.")
            print(f"   예시 row_id: {collide_sample}")
        if stat["no_material"]:
            print(f"\n⚠️ 재료 없음 {stat['no_material']}건 - 어느 컬럼이 비어서인지:")
            for c, n in sorted(empty_by_col.items(), key=lambda x: -x[1]):
                print(f"     {c:24s} {n:10d}")
        if not apply and pending:
            print(f"\n실제로 쓰려면 --apply. 그 전에 위 세 줄(no_material / unchanged / "
                  f"collides)이 납득되는지 먼저 볼 것.")
        return stat
    finally:
        # No `invalidate()` any more, and nothing to remember: the flag lives on a
        # NullPool engine of our own, so there is no pooled connection to poison.
        conn.close()
        ro_engine.dispose()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--table", required=True)
    p.add_argument("--apply", action="store_true",
                   help="실제로 쓴다. 없으면 읽기 전용.")
    args = p.parse_args(argv)
    out = run(args.table, args.apply)
    return 1 if out.get("collides") else 0


if __name__ == "__main__":
    sys.exit(main())
