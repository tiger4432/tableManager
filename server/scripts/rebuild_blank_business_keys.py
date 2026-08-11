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

🔴 기본은 읽기 전용이고, 세션에 `default_transaction_read_only`를 걸어 **구조적으로**
   못 쓰게 한다 — 아래 코드에 UPDATE가 없다는 것을 운영자가 믿어야 하는 상태로 두지
   않는다. 쓰려면 `--apply`.

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
from database.database import engine                           # noqa: E402
from database import crud, schemas                             # noqa: E402

STATEMENT_TIMEOUT_MS = 120_000
CHUNK = 1_000


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

    print(f"=== {table} | {'APPLY' if apply else 'CHECK (읽기 전용)'} ===")
    print(f"조합 재료: {sources}  구분자: {sep!r}\n")

    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    readonly = False
    try:
        if not apply:
            # 관례가 아니라 구조로 막는다. 끝나면 invalidate 로 커넥션을 버린다 -
            # close() 는 풀로 돌려보내므로 다음 사용자가 이 플래그를 물려받는다
            # (add_business_key_unique_index.py 가 실제로 그 사고를 겪었다).
            conn.execute(text("SET SESSION default_transaction_read_only = on"))
            readonly = True
        conn.execute(text(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}"))

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
                with engine.begin() as w:
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
        if readonly:
            conn.invalidate()
        conn.close()


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
