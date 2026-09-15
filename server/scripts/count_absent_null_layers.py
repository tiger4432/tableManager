# -*- coding: utf-8 -*-
"""어제까지 쌓인 «파일의 NULL 층»을 «센다». 지우지 않는다 (S-243-b, 판정 405).

    python scripts/count_absent_null_layers.py

읽기만 한다. 아무것도 만들지 않고 아무것도 지우지 않는다. `--apply` 는 «없다».

🔴 판정 405 는 «앞으로의 쓰기»를 고쳤다. 파일의 빈 칸은 이제 층을 안 세운다. 그런데 어제까지
   세워진 층은 `cell_sources` 에 그대로 남아 있고, 파일 소스가 체인을 앞서므로(2 또는 99 대 4)
   조인이 «올바르게 쓴» 값을 오늘도 가린다. 이 스크립트는 그 수를 낸다 — 지우는 것은 데이터
   변경이라 소유자 승인 뒤이고, 승인을 받으려면 «수»가 먼저다.

🔴 「비울 수 있는 쓴 이」의 술어는 «다시 적지 않는다» — `crud.can_mean_emptied` 를 import 한다.
   쓰는 쪽과 세는 쪽이 「누가 칸을 비울 수 있나」에 다르게 답하면, 세는 수가 «다른 것의 수»가
   된다.

⚠️ 두 수를 «따로» 낸다. 「NULL 층의 수」와 「그중 실제로 무언가를 가리는 수」는 다른 사실이다 —
   아래에 다른 층이 없는 NULL 층은 지워도 화면이 안 바뀌고, 있는 것만 값을 가린다. 한 수로
   합치면 운영자가 「수천 건을 고쳐야 한다」를 보고 «아무것도 안 바뀌는» 일을 하게 된다.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # S-159: cp949 콘솔에서 한 글자에 죽지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass

#: 한 화면에 싣는 줄 수. 넘으면 세는 것은 계속하고 «나열»만 접는다 — 수는 절대 안 자른다.
MAX_ROWS_SHOWN = 40


def count(db) -> list:
    """(표, 컬럼, 소스, NULL 층 수, 그중 «가리는» 수). 큰 것부터.

    ⚠️ 「가린다」의 정의를 여기 적는다: 같은 (표, 행, 컬럼) 에 «값이 있는 다른 층»이 하나라도
    있으면 이 NULL 층이 그 위에 앉아 있을 수 있다. 서열까지 따지지 않는 이유는 그것이 이
    수의 «쓰임»이기 때문이다 — 이 수는 「지울 후보가 몇이냐」이지 「지금 무엇이 보이냐」가
    아니고, 후자는 지우기 전에 내보낼 목록이 답한다.
    """
    from sqlalchemy import text

    from database import crud

    # 🔴 A 「NULL LAYER」 IS THE JSON LITERAL `null`, NOT SQL NULL, AND THAT IS THE WHOLE
    # DIFFERENCE BETWEEN THIS SCRIPT AND A SCRIPT THAT ALWAYS ANSWERS 「없음」.
    # `cell_sources.value` is a JSON column, so a blank written through the real door lands
    # as the four characters `null`. Measured through `apply_batch_updates` on 2026-09-15:
    # a blank from `user`, from `chain_ingestion` and from a file ALL store `null`, and
    # `value IS NULL` is false for every one of them. The order for this round specified
    # `value IS NULL`; that predicate counts ZERO on a database full of exactly the rows it
    # is looking for, and a false zero here reads as 「치울 것이 없다」.
    #
    # ⚠️ SQL NULL IS KEPT IN THE FILTER ANYWAY. A row that never had a value set at all
    # is the same absence, and including it costs nothing.
    #
    # ⚠️ AND AN EMPTY STRING DOES NOT NEED A THIRD CASE: storage is canonical
    # (`normalize_stored_text`), and the same measurement shows `""` arriving as `null` too.
    rows = db.execute(text("""
        SELECT s.table_name, s.column_name, s.source_name,
               COUNT(*) AS layers,
               SUM(CASE WHEN EXISTS (
                     SELECT 1 FROM cell_sources o
                      WHERE o.table_name = s.table_name
                        AND o.row_id = s.row_id
                        AND o.column_name = s.column_name
                        AND o.source_name <> s.source_name
                        AND o.value IS NOT NULL
                        AND CAST(o.value AS TEXT) <> 'null'
                   ) THEN 1 ELSE 0 END) AS hiding
          FROM cell_sources s
         WHERE s.value IS NULL OR CAST(s.value AS TEXT) = 'null'
         GROUP BY s.table_name, s.column_name, s.source_name
    """)).fetchall()

    out = []
    for table_name, column_name, source_name, layers, hiding in rows:
        # 🔴 THE ONE PREDICATE, IMPORTED. A person's cleared cell and the chain's asserted
        # blank are ANSWERS and must not be counted as debris - they are the two layers
        # ruling 405 deliberately keeps.
        if crud.can_mean_emptied(source_name):
            continue
        out.append((table_name, column_name, source_name,
                    int(layers or 0), int(hiding or 0)))
    out.sort(key=lambda entry: (-entry[4], -entry[3], entry[0], entry[1]))
    return out


def render(found: list) -> str:
    """운영자가 읽는 것. 「수」와 「그 수가 무엇을 뜻하나」를 같이 낸다."""
    if not found:
        return ("파일 소스의 NULL 층: «없음». 판정 405 이전에 쌓인 것이 이 설치에는 "
                "남아 있지 않습니다 → 다음: 없음")

    layers = sum(entry[3] for entry in found)
    hiding = sum(entry[4] for entry in found)
    lines = ["파일 소스의 NULL 층 %d — 그중 «값을 가리는» 것 %d" % (layers, hiding),
             "",
             "%-24s %-20s %-24s %8s %8s" % ("표", "컬럼", "소스", "NULL 층", "가림"),
             "-" * 88]
    for entry in found[:MAX_ROWS_SHOWN]:
        lines.append("%-24s %-20s %-24s %8d %8d" % entry)
    if len(found) > MAX_ROWS_SHOWN:
        lines.append("... 그리고 %d 조합 더 (수는 위 합계에 «전부» 들어 있습니다)"
                     % (len(found) - MAX_ROWS_SHOWN))
    lines.append("")
    lines.append("→ 다음: " + (
        "없음 — 가리는 층이 0 입니다. 지워도 화면이 안 바뀝니다"
        if hiding == 0 else
        "이 수(가림 %d)를 총괄에게 전달하십시오. 지우기는 별 지시(S-243-c)이고, "
        "«먼저 내보낸 뒤» 되돌릴 수 있게 합니다" % hiding))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    from database.database import SessionLocal

    db = SessionLocal()
    try:
        print(render(count(db)))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
