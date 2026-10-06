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


#: What a counted layer is (총괄 c773b0fed ③). A merge names its copy of a layer
#: `<writer> (<old key>_<row>)` (`crud.merged_layer_name`), and only those are split by writer.
ABSENT = "absent"
MERGED_ABSENT = "merged_absent"
MERGED_UNSURE = "merged_unsure"
KINDS = (ABSENT, MERGED_ABSENT, MERGED_UNSURE)
MEANING = {
    ABSENT: "비울 수 없는 쓴 이(파일 등)의 빈 층 (S-243-b) — 판정 405 이전에 쌓인 부재",
    MERGED_ABSENT: "합치기가 남긴 빈 사본, 비울 수 없는 쓴 이 — 부재로 확정 (판정 405)",
    MERGED_UNSURE: ("합치기가 남긴 빈 사본, 사람 · 체인 — 부재인지, 일부러 비운 칸의 사본인지 "
                    "구별이 안 된다"),
}


def count(db) -> list:
    """(종류, 표, 컬럼, 소스, 빈 층 수, 그중 «가리는» 수). 종류마다 큰 것부터.

    ⚠️ 「가린다」의 정의를 여기 적는다: 같은 (표, 행, 컬럼) 에 «값이 있는 다른 층»이 하나라도
    있으면 이 빈 층이 그 위에 앉아 있을 수 있다. 서열까지 따지지 않는 이유는 그것이 이
    수의 «쓰임»이기 때문이다 — 이 수는 「지울 후보가 몇이냐」이지 「지금 무엇이 보이냐」가
    아니고, 후자는 지우기 전에 내보낼 목록이 답한다.

    🔴 «빈 값»은 정본 하나로 — `blank_sql_condition(column_text_sql(value))`. JSON null · SQL
    NULL · "" 가 같은 답이다. 이 스크립트가 JSON null 만 세던 때, 합치기가 남긴 "" 층을
    0 으로 셌다 (총괄 c773b0fed, sqlite · PG 둘 다 잼).
    """
    from sqlalchemy import and_, case, exists, func
    from sqlalchemy.orm import aliased

    from database import crud, models

    s, o = models.CellSource, aliased(models.CellSource)
    hides = exists().where(and_(
        o.table_name == s.table_name, o.row_id == s.row_id, o.column_name == s.column_name,
        o.source_name != s.source_name,
        crud.not_blank_sql_condition(crud.column_text_sql(o.value))))
    rows = (db.query(s.table_name, s.column_name, s.source_name, func.count(),
                     func.sum(case((hides, 1), else_=0)))
            .filter(crud.blank_sql_condition(crud.column_text_sql(s.value)))
            .group_by(s.table_name, s.column_name, s.source_name).all())

    out = []
    for table_name, column_name, source_name, layers, hiding in rows:
        writer = crud.layer_writer(source_name)
        # 🔴 THE ONE PREDICATE, IMPORTED. A person's cleared cell and the chain's asserted
        # blank are ANSWERS and must not be counted as debris - they are the two layers
        # ruling 405 deliberately keeps. A merge's copy of one is not told apart from a copy
        # the merge made of nothing, so it is counted under its own kind.
        if writer == source_name:
            if crud.can_mean_emptied(source_name):
                continue
            kind = ABSENT
        else:
            kind = MERGED_UNSURE if crud.can_mean_emptied(writer) else MERGED_ABSENT
        out.append((kind, table_name, column_name, source_name,
                    int(layers or 0), int(hiding or 0)))
    out.sort(key=lambda entry: (KINDS.index(entry[0]), -entry[5], -entry[4],
                                entry[1], entry[2]))
    return out


def render(found: list) -> str:
    """운영자가 읽는 것. 종류마다 「수」와 「그 수가 무엇을 뜻하나」를 같이 낸다."""
    if not found:
        return ("빈 층: «없음». 판정 405 이전에 쌓인 것도, 합치기가 남긴 것도 이 설치에는 "
                "없습니다 → 다음: 없음")

    lines = []
    for kind in KINDS:
        entries = [entry[1:] for entry in found if entry[0] == kind]
        layers = sum(entry[3] for entry in entries)
        hiding = sum(entry[4] for entry in entries)
        lines += ["%s — 빈 층 %d, 그중 «값을 가리는» 것 %d" % (MEANING[kind], layers, hiding)]
        if entries:
            lines += ["%-24s %-20s %-24s %8s %8s" % ("표", "컬럼", "소스", "빈 층", "가림"),
                      "-" * 88]
            lines += ["%-24s %-20s %-24s %8d %8d" % entry for entry in entries[:MAX_ROWS_SHOWN]]
            if len(entries) > MAX_ROWS_SHOWN:
                lines.append("... 그리고 %d 조합 더 (수는 위 합계에 «전부» 들어 있습니다)"
                             % (len(entries) - MAX_ROWS_SHOWN))
        lines.append("")
    hiding = sum(entry[5] for entry in found)
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
