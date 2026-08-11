"""한 업무키에 여러 행이 있는 그룹을 **한 행으로 접는다.** 기본은 읽기 전용.

🔴 「그냥 지우면 된다」는 데이터에 대한 **가설**이다. 이 스크립트는 그 가설을 먼저 검증한다.

    한 그룹의 행들은 서로 다른 행이 아니라 **같은 논리적 행의 재입고**다
    (`818c9c0` 본문: "push 1은 네 행에 키 넷, push 2는 네 행에 키 제로, push 3은
    여덟 행"). 재입고끼리 값이 같으면 접는 것은 무손실이다. **다르면 지우는 쪽이
    가진 값이 같이 사라진다** — 나중 배송이 안 준 컬럼을 앞 배송이 갖고 있을 수 있다.

    그래서 그룹을 둘로 가른다:

      identical   선언된 컬럼 전부가 같다            -> 접어도 무손실
      differing   하나라도 다르다                    -> **기본으로 건너뛴다.**
                                                       어느 컬럼이 다른지 이름으로 낸다

    `--allow-differing` 없이는 differing 그룹을 절대 건드리지 않는다. 그 플래그를
    쓰려면 **어느 컬럼이 다른지 보고 나서** 쓰는 것이고, 그때도 남는 행은 아래 규칙이
    고른다.

🔴 삭제는 `crud.delete_rows_batch`가 정본이다. 생 `DELETE`를 쓰면
   `cell_sources`·`cell_overwrites`가 **고아로 남고** DELETE 감사 로그가 안 남는다 —
   즉 이 시스템에서 행이 사라진 기록 자체가 없어진다. 그 함수는 연쇄 삭제와 감사
   기록을 한 트랜잭션에 묶는다.

남길 행을 고르는 규칙 (그리고 그것을 출력에 적는다):
    1. `cell_sources` 행이 가장 많은 것 — 출처를 가장 많이 가진 행
    2. 동수면 `row_id`가 가장 이른 것 — uuid7이라 시간 순서다

⚠️ 이 스크립트는 재조립(`rebuild_blank_business_keys.py`) **다음**이다. 먼저 재조립하면
   상당수 그룹이 스스로 풀려서 여기 올 그룹이 줄어든다. 순서를 바꾸면 **원래 다른 행이었던
   것들을 같은 것으로 보고 접게 된다.**

Usage
-----
    python server/scripts/dedupe_business_key_rows.py --table <표>
    python server/scripts/dedupe_business_key_rows.py --table <표> --apply
    python server/scripts/dedupe_business_key_rows.py --table <표> --apply --allow-differing
"""

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import text                                    # noqa: E402
from database.database import engine, SessionLocal             # noqa: E402
from database import crud, models                              # noqa: E402

STATEMENT_TIMEOUT_MS = 120_000
CHUNK = 200
SAMPLE = 5


def _norm(v):
    """비교용 정규화. None 과 '' 를 같게 보지 않는다 — 이 시스템에서 그 둘은
    다른 뜻이고(`818c9c0`), 같다고 보면 실제 손실을 무손실로 오판한다."""
    return v


def _write_dump(path: str, table: str, cols: list, diff: list, same: list):
    """🔴 JSON 이지 TSV 가 아니다. 이 시스템에서 `None` 과 `''` 는 서로 다른 뜻인데
    (`818c9c0`), TSV 는 둘 다 빈 칸으로 찍어 **그 차이를 지운다** — 이 파일을 보는
    이유가 바로 그 차이일 수 있다. 인코딩도 명시한다(cp949 로 문서를 한 번 잃었다)."""
    import json
    payload = {"table": table, "columns": cols,
               "keep_rule": "cell_sources 최다 -> row_id 최소(uuid7 시간순)",
               "differing_groups": diff, "identical_groups": same}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n덤프: {path}  (differing {len(diff)}군 / identical {len(same)}군)")
    print("  `_keep: true` 가 남길 행이다. null 과 \"\" 는 파일에서 구분된다.")


def run(table: str, apply: bool, allow_differing: bool,
        dump_path: str = None, dump_groups: int = 20) -> dict:
    cfg = crud.TABLE_CONFIG.get(table) or {}
    cols = list((cfg.get("column_types") or {}).keys())
    if not cols:
        print(f"!! '{table}' 의 column_types 선언이 없다 - 비교할 컬럼을 모른다")
        return {"skipped": True}

    # 🔴 동적 테이블 모델은 서버 기동 때 만들어지므로 단독 스크립트엔 없다. 이 한 줄이
    #    없으면 `crud.delete_rows_batch` 가 "Table model ... is not initialized" 로 죽는다 -
    #    읽기 전용 패스는 생 SQL 이라 멀쩡히 통과하고 `--apply` 에서만 죽으므로, 없으면
    #    **점검은 초록인데 실행만 실패한다.** `backfill_enrichment.py` 등 여섯 스크립트가
    #    같은 줄로 시작한다.
    models.init_dynamic_models(crud.TABLE_CONFIG)
    if models.DYNAMIC_TABLES.get(table) is None:
        print(f"!! '{table}' 모델이 만들어지지 않았다 - table_config.json 에 선언이 있는지 "
              f"먼저 볼 것. 읽기 전용 패스에서 미리 막는다(그래야 --apply 에서만 죽는 일이 없다)")
        return {"skipped": True}

    mode ="APPLY" + (" +differing" if allow_differing else "") if apply else "CHECK (읽기 전용)"
    print(f"=== {table} | {mode} ===")
    print(f"비교 컬럼 {len(cols)}개, 남길 행 규칙: cell_sources 최다 -> row_id 최소\n")

    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    readonly = False
    try:
        if not apply:
            conn.execute(text("SET SESSION default_transaction_read_only = on"))
            readonly = True
        conn.execute(text(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}"))

        # 🔴 `SELECT *`. 처음엔 `column_types` 선언한 컬럼만 떠서 비교했는데, 그러면
        #    **선언 밖 컬럼이 달라도 identical 로 나온다.** 비교 모집단을 선언으로 좁히는
        #    것 자체가 가설이고, 그 가설이 반증을 먼저 지운다. 전부 떠서 분류한다.
        rows = conn.execute(text(
            f'SELECT * FROM public."{table}" WHERE business_key_val IS NOT NULL'
        )).mappings().all()
        if rows:
            present = list(rows[0].keys())
            declared = [c for c in cols if c in present]
            # 신원·시각처럼 행마다 다른 것이 당연한 컬럼은 「다르다」에 넣되 **따로** 센다.
            system = [c for c in present
                      if c not in declared and c not in ("row_id", "business_key_val")]
            print(f"실제 컬럼 {len(present)}개 = 선언 {len(declared)} + 시스템 {len(system)}")
            print(f"시스템 컬럼: {system}\n")
        else:
            declared, system = cols, []

        groups = {}
        for r in rows:
            groups.setdefault(r["business_key_val"], []).append(r)
        groups = {k: v for k, v in groups.items() if len(v) > 1}

        # 출처 수는 남길 행을 고르는 데만 쓴다. 그룹에 속한 row_id 만 센다.
        ids = [r["row_id"] for g in groups.values() for r in g]
        srccount = {}
        for i in range(0, len(ids), 5000):
            part = ids[i:i + 5000]
            for rid, n in conn.execute(text(
                'SELECT row_id, count(*) FROM cell_sources '
                'WHERE table_name = :t AND row_id = ANY(:ids) GROUP BY row_id'
            ), {"t": table, "ids": part}):
                srccount[rid] = n

        stat = {"groups": len(groups), "rows_in_groups": len(ids),
                "identical": 0, "differing": 0, "system_only": 0,
                "deletable": 0, "deleted": 0}
        diff_by_col, sys_by_col, diff_sample, victims = {}, {}, [], []
        dump_diff, dump_same = [], []

        for key, g in groups.items():
            base = g[0]
            differing_cols = [c for c in declared
                              if any(_norm(r[c]) != _norm(base[c]) for r in g[1:])]
            # 시스템 컬럼 차이는 **따로** 센다. 「선언 컬럼은 같은데 타임스탬프만 다르다」와
            # 「데이터가 다르다」는 전혀 다른 판정이고, 한 통에 넣으면 구분이 사라진다.
            sys_diff = [c for c in system
                        if any(_norm(r[c]) != _norm(base[c]) for r in g[1:])]
            if sys_diff:
                stat["system_only"] += 0 if differing_cols else 1
                for c in sys_diff:
                    sys_by_col[c] = sys_by_col.get(c, 0) + 1
            if differing_cols:
                stat["differing"] += 1
                for c in differing_cols:
                    diff_by_col[c] = diff_by_col.get(c, 0) + 1
                if len(diff_sample) < SAMPLE:
                    diff_sample.append((len(g), differing_cols[:4]))
                if not allow_differing:
                    continue
            else:
                stat["identical"] += 1
            keep = sorted(g, key=lambda r: (-srccount.get(r["row_id"], 0), r["row_id"]))[0]
            drop = [r["row_id"] for r in g if r["row_id"] != keep["row_id"]]
            victims.extend(drop)
            stat["deletable"] += len(drop)

            bucket = dump_diff if differing_cols else dump_same
            if dump_path and len(bucket) < dump_groups:
                bucket.append({
                    "business_key_val": key,
                    "verdict": "differing" if differing_cols else "identical",
                    "differing_columns": differing_cols,
                    "system_columns_differing": sys_diff,
                    # 🔴 남길 행을 표시해 둔다 - 규칙을 산문으로만 적으면 이 파일을 보는
                    #    사람이 규칙을 머릿속에서 다시 적용해야 한다.
                    "rows": [dict({"row_id": r["row_id"],
                                   "_keep": r["row_id"] == keep["row_id"],
                                   "_cell_sources": srccount.get(r["row_id"], 0)},
                                  # 선언 + 시스템 전부. 다른 것이 시스템 컬럼이면
                                  # 선언만 실었을 때 **파일에서도 안 보인다.**
                                  **{c: r[c] for c in declared + system})
                             for r in g],
                })

        if apply:
            for i in range(0, len(victims), CHUNK):
                part = victims[i:i + CHUNK]
                db = SessionLocal()
                try:
                    # 정본 경로. 연쇄 삭제 + DELETE 감사 로그를 같이 한다.
                    n = crud.delete_rows_batch(db, table, part, user_name="dedupe_script")
                    db.commit()
                    stat["deleted"] += n
                finally:
                    db.close()
                print(f"  .. {stat['deleted']}/{len(victims)}")

        print(f"\n{'항목':22s} {'건수':>10s}")
        for k in ("groups", "rows_in_groups", "identical", "differing",
                  "system_only", "deletable"):
            print(f"{k:22s} {stat[k]:10d}")
        if apply:
            print(f"{'deleted':22s} {stat['deleted']:10d}")

        if stat["differing"]:
            print(f"\n🔴 값이 다른 그룹 {stat['differing']}개"
                  f"{' - 건너뛰었다' if not allow_differing else ' - --allow-differing 이라 접었다'}."
                  f" 어느 컬럼이 다른가:")
            for c, n in sorted(diff_by_col.items(), key=lambda x: -x[1]):
                print(f"     {c:24s} {n:10d}")
            print(f"   예시(그룹 크기, 다른 컬럼): {diff_sample}")
            if not allow_differing:
                print("   이 그룹들을 접으려면 위 컬럼 목록을 보고 판단한 뒤"
                      " --allow-differing 을 붙인다. 붙이면 위 규칙이 고른 행만 남고"
                      " 나머지 행이 가진 값은 사라진다.")
        if sys_by_col:
            print(f"\n선언 밖(시스템) 컬럼 차이 — 「선언 컬럼은 같은데 이것만 다른」 그룹 "
                  f"{stat['system_only']}개. 접어도 데이터는 안 잃지만 이 값은 잃는다:")
            for c, n in sorted(sys_by_col.items(), key=lambda x: -x[1]):
                print(f"     {c:24s} {n:10d}")

        if dump_path:
            _write_dump(dump_path, table, declared + system, dump_diff, dump_same)

        if not apply and stat["deletable"]:
            print(f"\n실제로 지우려면 --apply. 삭제는 crud.delete_rows_batch 를 통하므로"
                  f" cell_sources·cell_overwrites 가 함께 지워지고 DELETE 감사 로그가 남는다.")
        return stat
    finally:
        if readonly:
            conn.invalidate()
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--table", required=True)
    p.add_argument("--apply", action="store_true", help="실제로 지운다. 없으면 읽기 전용.")
    p.add_argument("--allow-differing", action="store_true", dest="allow_differing",
                   help="값이 다른 그룹도 접는다. 남는 행이 가진 값만 남는다.")
    p.add_argument("--dump", dest="dump_path",
                   help="중복 그룹 실물을 JSON 으로 쓴다(로컬 파일). 값이 다른 그룹을 "
                        "먼저 담고, 없으면 같은 그룹을 담는다.")
    p.add_argument("--dump-groups", type=int, default=20, dest="dump_groups",
                   help="각 부류에서 담을 그룹 수 (기본 20)")
    args = p.parse_args(argv)
    out = run(args.table, args.apply, args.allow_differing,
              args.dump_path, args.dump_groups)
    return 1 if out.get("differing") and not args.allow_differing else 0


if __name__ == "__main__":
    sys.exit(main())
