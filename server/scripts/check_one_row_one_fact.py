"""「행 하나는 사실 하나」를 이 설치에 대고 «한 번에» 묻는다 (소유자 명제 2026-09-15).

    python scripts/check_one_row_one_fact.py            # 선언만 (DB 안 붙음)
    python scripts/check_one_row_one_fact.py --db       # DB 까지 (유일 인덱스·중복·빈 키)

읽기만 한다. 아무것도 만들지 않고 아무것도 지우지 않는다.

🔴 왜 있나. 2026-09-14 에 조인이 꺼진 원인을 찾느라 하루가 갔고, 그 답은 «선언 두 줄»을
나란히 놓으면 나오는 것이었다 — 조인이 물은 키와 그 표가 선언한 신원. 그 비교를 사람이
매번 손으로 하게 두는 것이 이 도구가 없애려는 「복잡한 행위」다.

명제의 위반 넷을 그대로 묻는다:
    ② 한 행이 두 사실   조인 키가 그 표의 «신원보다 좁다»     -> 선언만으로 확정
    ①③ 두 행이 한 사실 / 어느 사실도 아닌 행                 -> DB 가 있어야 갈린다
    ④ 행이 없는 사실   읽기 시점 조인(실물화 아님)            -> 선언만으로 셀 수 있다
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # S-159: cp949 콘솔에서 한 글자에 죽지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", action="store_true",
                        help="DB 에 붙어 유일 인덱스·중복·빈 키까지 본다 (읽기만)")
    args = parser.parse_args(argv)

    from database import crud
    import virtual_join.config as vjc
    from chain import unique_key

    known = crud.TABLE_CONFIG
    rules = vjc.load_virtual_join_rules(known_tables=known)
    print("조인 선언 %d 건" % len(rules))

    narrow, read_time, fine = [], [], []
    for rule in rules:
        identity = unique_key.narrower_than_identity(
            rule["right_table"], rule["right_columns"], known)
        if identity:
            narrow.append((rule, identity))
        elif not rule.get("materialize"):
            read_time.append(rule)
        else:
            fine.append(rule)

    if narrow:
        print("\n[!] 키가 «신원보다 좁은» 조인 %d - 유일 인덱스가 «영원히» 설 수 없습니다."
              % len(narrow))
        print("    접기로는 못 고칩니다. 같은 키의 행들은 사본이 아니라 «다른 사실»입니다.")
        for rule, identity in narrow:
            print("    %s: 물은 키 (%s) / %s 의 신원 (%s)"
                  % (rule["name"], ", ".join(rule["right_columns"]),
                     rule["right_table"], ", ".join(identity)))
            print("       -> 이 조인의 키를 신원까지 넓히십시오")

    if read_time:
        print("\n읽기 시점 조인 %d - 값이 «행에 없습니다»(명제 위반 4)." % len(read_time))
        print("    원장이 그 값을 못 보므로 walk 의 주어도 마킹도 이력도 없습니다.")
        for rule in read_time:
            print("    %s: %s <- %s" % (rule["name"], rule["left_table"], rule["right_table"]))

    if fine:
        print("\n실물화된 조인 %d - 값이 행의 칸이고 출처가 층으로 붙습니다." % len(fine))

    if not args.db:
        print("\n(--db 를 주면 유일 인덱스·중복·빈 키까지 봅니다. 읽기만 합니다)")
        return 0

    from database.database import SessionLocal
    session = SessionLocal()
    try:
        print("\n--- DB 확인 (읽기만) ---")
        for rule in rules:
            if any(rule is entry[0] for entry in narrow):
                continue  # 선언이 이미 답했다. 데이터를 볼 이유가 없다
            report = unique_key.inspect(session, rule["right_table"],
                                        rule["right_columns"], rule.get("right_folds"))
            print("%s: %s" % (rule["name"],
                              unique_key.describe(rule["right_table"],
                                                  rule["right_columns"], report)))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
