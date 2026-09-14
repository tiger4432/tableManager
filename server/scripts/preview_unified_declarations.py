"""옛 선언 파일들을 «새 문법 한 파일»로 적어 본다 - 읽기만 하고, 미리보기만 쓴다 (S-234 3단계 준비).

    python scripts/preview_unified_declarations.py [--config <디렉터리>] [--out <파일>]

기본 입력은 «출하 샘플»이다. `--config` 로 다른 디렉터리를 주면 그것을 읽되 **절대 쓰지 않는다** -
쓰는 곳은 `--out` 뿐이고, 그것도 왕복이 «전건» 통과했을 때만이다.

🔴 왜 「미리보기」가 따로 있나. 2026-09-14 에 선언을 건드린 변경이 운영에서 넷을 터뜨렸고,
그날 없던 것은 「켜기 전에 무엇이 달라지는지 보는 자리」였다. 이행(3단계)은 «기계가» 하지만,
기계가 무엇을 쓸지 사람이 «먼저 본다». 그 둘은 모순이 아니다 - 손으로 옮기지 않는 것과
눈으로 확인하는 것은 다른 일이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import rule_shape  # noqa: E402

# 🔴 S-159 의 그 결함을 이 스크립트가 «그대로» 재현했다(2026-09-14): 윈도우 콘솔 기본이
#    cp949 라 em-dash 한 글자에 CLI 가 죽는다. 출력 인코딩을 여기서 한 번 세우고, 아래 문구는
#    cp949 가 아는 글자만 쓴다. 「운영자가 못 읽는 진단」은 진단이 아니다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # 아주 오래된 파이썬이나 리다이렉트된 스트림
    pass

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "config", "sample")
CHAIN_FILE = "chain_rules.json"
JOIN_FILE = "virtual_join_rules.json"


def _read(directory: str, filename: str):
    """`<이름>` 을 찾고, 없으면 `<이름>.sample` 을 찾는다. 둘 다 없으면 «빈 것»이 아니라 None."""
    for candidate in (filename, filename + ".sample"):
        path = os.path.join(directory, candidate)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return path, json.load(handle)
    return None, None


def _chain_rules(document):
    if document is None:
        return []
    rules = document.get("rules", document) if isinstance(document, dict) else document
    if isinstance(rules, dict):
        rules = list(rules.values())
    return [rule for rule in (rules or []) if isinstance(rule, dict)]


def _joins(document):
    if not isinstance(document, dict):
        return {}
    return {name: raw for name, raw in document.items()
            if isinstance(raw, dict) and not name.startswith("_")}


def build(config_dir: str):
    """(새 문법 문서, 보고) - 왕복이 깨진 선언이 하나라도 있으면 보고가 그것을 «이름»으로 든다."""
    chain_path, chain_doc = _read(config_dir, CHAIN_FILE)
    join_path, join_doc = _read(config_dir, JOIN_FILE)

    declarations, broken = [], []
    for raw in _chain_rules(chain_doc):
        internal = rule_shape.from_chain_rule(raw)
        written = rule_shape.to_declaration(internal)
        if rule_shape.as_chain_rule(rule_shape.from_declaration(written)) != raw:
            broken.append(("chain", raw.get("name")))
        declarations.append(written)

    for name, raw in _joins(join_doc).items():
        internal = rule_shape.from_join_rule(name, raw)
        written = rule_shape.to_declaration(internal)
        if rule_shape.as_join_rule(rule_shape.from_declaration(written)) != raw:
            broken.append(("join", name))
        declarations.append(written)

    kinds = {}
    for declaration in declarations:
        kind = (declaration.get("derive") or {}).get("kind", "unknown")
        lands = "read" if (declaration.get("into") or {}).get("read") else "table"
        kinds["%s→%s" % (kind, lands)] = kinds.get("%s→%s" % (kind, lands), 0) + 1

    return ({"rules": declarations},
            {"sources": [p for p in (chain_path, join_path) if p],
             "count": len(declarations), "kinds": kinds, "broken": broken})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    document, report = build(args.config)

    print("읽은 파일:", ", ".join(report["sources"]) or "(없음)")
    print("선언 %d 건 - %s" % (
        report["count"],
        " | ".join("%s %d" % (key, value) for key, value in sorted(report["kinds"].items()))))

    if report["broken"]:
        # 🔴 깨진 것이 하나라도 있으면 «쓰지 않는다». 반쯤 옳은 이행 파일은 없느니만 못하다
        print("🔴 왕복이 깨진 선언 %d - 쓰지 않습니다:" % len(report["broken"]))
        for grammar, name in report["broken"]:
            print("   %s %s" % (grammar, name))
        return 1

    print("✅ 왕복 전건 통과 - 모든 선언이 새 문법을 지나 «같은 것»으로 돌아옵니다")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        print("미리보기 씀:", args.out)
    else:
        print("(--out 을 주면 파일로 씁니다. 입력은 어떤 경우에도 «안» 건드립니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
