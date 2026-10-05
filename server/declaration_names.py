# -*- coding: utf-8 -*-
"""선언의 이름을 «원장이 쓰는 이름»으로 — 한 자리.

🔴 이름은 «맨이름» 하나다(소유자 10-04 「노드 엣지 명칭에 @1 요고 필요 없어 보이는데」, 총괄
4eb1fe98f). 원장은 처음부터 맨이름(`of_kind` · `wafer`)을 썼고, 선언만 버전을 붙였다(`of_kind@1`).
그 차이가 결함 둘을 낳았다. 이제 옛 파일의 `x@1` 은 «읽을 때» `fold_versions` 가 접고, 저장은
맨이름으로 된다 — 운영자가 파일을 고칠 일은 없다.

실측 2026-09-07 — 이 번역을 하는 자리가 «서른둘»이었고, 그중 «넷»이 `_bare` 라는 «같은
이름»에 «다른 본체»를 갖고 있었다:

    ledger/gaps.py               str(name).split("@")[0]
    ledger_api/ledger_subgraph.py  str(name or "").split("@", 1)[0]
    ledger_admin.py              str(name or "").split("@", 1)[0].strip()
    ledger_api/declared_entities.py  str(...).split("@", 1)[0].strip().lower()

🔴 넷 다 docstring 이 «같은 말»을 한다. 그래서 읽는 사람 쪽에서 「같은 함수겠지」가 일어나고,
   실제로 그렇게 읽혔다 — 이 부류를 지시서에 「모듈 둘」로 적은 것이 그 오독이다(이름으로 셌다).
   본체로 세면 넷이고, 넷은 «공백 · 대소문자 · None» 에서 갈린다. 오늘은 안 갈려 있을 뿐이다.

⚠️ 여기가 «공통 몸통»이다. `declared_entities` 의 «소문자 접기»는 그 모듈의 «추가»이고 그쪽에
   남는다 — 그것까지 여기 넣으면 나머지 셋의 답이 조용히 바뀐다. 공통이 아닌 것을 공통에
   넣는 것은 사본을 만드는 것과 같은 종류의 실수다.

⛔ 그리고 이것은 «파싱»이 아니다. 버린 버전을 «쓰는» 자리(`setup_registry` 가 이름과 버전을 둘 다
   바인드하고, `source_profile` 이 `version_text` 를 읽는다)는 이 부류가 아니며 여기를 부르지
   않는다. 판별식은 「버린 버전을 «쓰나»」이고, 쓰면 파싱이다.
"""

import re

#: 옛 선언이 이름에 버전을 붙일 때 쓰던 글자. 여기 말고 다른 곳에서 이 글자를 «의미로» 쓰지 않는다.
VERSION_SEPARATOR = "@"
#: `name@N` - the spelling a declaration gave its names until 10-04.
_VERSIONED = re.compile(r"^([^@/\s]+)@[1-9][0-9]*$")


def bare_name(value):
    """`wafer@1` -> `wafer`. 버전을 «버린다» — 쓰지 않는다.

    `None` 은 «빈 이름»이다. 종전 `gaps.py` 판은 `str(None)` 을 태워 `"None"` 이라는 «실재하는
    것처럼 보이는» 이름을 만들었다 — 그 문자열은 선언에도 원장에도 없으므로 조용히 아무것도
    매치하지 않는다. 빈 문자열은 최소한 «비어 있음»으로 읽힌다.

    앞뒤 공백을 턴다. 넷 중 둘이 이미 그렇게 했고, 안 털던 둘은 「선언 파일이 공백을 안 낳는다」에
    기대고 있었다 — 그 전제는 선언이 «사람이 쓰는 파일»이 되는 날 깨진다.
    """
    return str(value or "").split(VERSION_SEPARATOR, 1)[0].strip()


def fold_versions(document):
    """A declaration with its names spelled bare - THE ONE FOLD, at every read of a declaration.

    Every dict key and every string that is `name@N` of a name `vocabulary` or `entities`
    declares becomes `name`, wherever it sits (subjects, object types, a mapping's predicate, an
    `entity_type`, `bind.entities`, references). A string naming nothing declared is left alone -
    `SYN-RCP-BOND@4` is a value. Not a declaration (neither section) -> returned as given.

    ⛔ Two spellings of one name in one section (`x@1` and `x@2`, or `x` beside `x@1`) are not
    merged - which one a source meant is not this function's to guess. The document comes back
    unfolded and the validator refuses each `@` name by its path.
    """
    if not isinstance(document, dict):
        return document
    declared = set()
    for section in ("vocabulary", "entities"):
        names = document.get(section)
        if not isinstance(names, dict):
            continue
        spellings = {}
        for name in names:
            spellings.setdefault(bare_name(name), []).append(str(name))
        if any(len(each) > 1 for each in spellings.values()):
            return document
        declared |= set(spellings)
    if not declared:
        return document

    def fold(value):
        if isinstance(value, dict):
            return {fold(key): fold(item) for key, item in value.items()}
        if isinstance(value, list):
            return [fold(item) for item in value]
        if isinstance(value, str):
            match = _VERSIONED.match(value)
            if match and match.group(1) in declared:
                return match.group(1)
        return value
    return fold(document)
