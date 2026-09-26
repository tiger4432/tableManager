# -*- coding: utf-8 -*-
"""참조뷰의 «자기 자리» — 인리치 맵퍼 안에 묻혀 있지 않습니다.

> 소유자 2026-09-17: 「인리치는 참조뷰 기능은 «보존»해야 해. v2 로 «따로» 빼되」
> 「ㅇㅇ 여기에 참조뷰 «라우트»만 추가하고」

🔴 ONE GRAMMAR, ONE HOME (소유자 2026-09-23: 「enrich.json 아예 삭제라운드 만들어 삭제를
안해버리니 자꾸 문을 두개두네?」 · 「통합선언 무조건 돌게해라」). An enrich declaration lives
in ONE place - the `derive.decide` block in `chain_rules.json` - and this module is the one
seat every consumer asks. `rule_shape.expand_declaration` stands it exactly as the chain
loader does, so what a route sees and what the worker runs cannot be two lists.

⚰️ [2026-09-24] A SECOND GRAMMAR - `enrichment_rules.json` - WAS READ HERE TOO, first, and
won a name collision. This module was built (2026-09-17) because a view written in the
unified grammar was declared, carried and UNREACHABLE while every consumer read only the
flat file; the owner then retired the flat file itself, because keeping it meant keeping
the second door. Measured the day it went: the backfill RUN path still opened the flat
file by path while its dry-run went through here, so a rule the preview showed was one
the run could not find.

🔴 ONE SEAT, NOT A SECOND ENDPOINT. The fix is NOT a `/admin/chain/.../references/` beside
the one that is already there - that is 「같은 기능 두 경로」 with the operator left to guess
which grammar they wrote in. The existing pair of routes asks THIS module for the
declaration, and this module is the one place that knows where a declaration lives.

⚠️ THE PAIR IS A PAIR. `/enrichment/rules` names the views and `/…/references/{index}`
runs the index-th one, so the two must walk the SAME list or the index means different
things at the two ends - the index-alignment guarantee `_normalize_reference_views`
states in its own docstring. Both call `declarations()` here.

⚠️ AND WHAT IS **NOT** HERE IS SAID OUT LOUD. The reference view's ENGINE - the SQL
resolution, the bind checks, the server-enforced LIMIT, the failure sentence - stays in
`enrichment/config.py` (457 lines of it, counted). Moving it is a different round with a
different risk, and this module deliberately calls it rather than copying any of it:
`execute_reference_view` is 「유일한 정의」 and a second spelling of a LIMIT is how a screen
and a probe start seeing different rows.

⚰️ AND 「WHEN THEY MOVE」 WAS 2026-09-22 (판정 636, 소유자 컨펌). This paragraph read, in the
present tense: 「THE OTHER READERS ARE NOT WIDENED… the owner scoped this round to the
reference view (「참조뷰 라우트만」), so the other thirteen are UNCHANGED and counted here」.
That limit is lifted and the sentence is kept as the REASON the split existed, because a
reader who finds two shapes in git history deserves to know it was scoped, not forgotten.
Measured again on the day it lifted, with the instrument the ruling handed over:

    git grep -n "load_enrichment_rules(" -- server | grep -v "/tests/" | grep -v "def load_"
      -> 14 hits, one of them this module: **13 places saw only the flat file**

🔴 THE NAME IS THE SECOND HALF OF THE SAME FIX. This module was `chain/reference_view.py`,
and a name that says 「reference view」 is read as 「for reference views only」 - which is how
the next person puts their own copy beside it. That is exactly the path the defect took the
first time. It is `enrich_declarations` now: what it does is answer 「which enrich
declarations does this product stand, whichever grammar wrote them」, and the reference view
is one caller of that.
"""

import logging
import os

logger = logging.getLogger("Chain.EnrichDeclarations")


def declarations(known_tables: dict = None, chain_rules_path: str = None,
                 rejections: list = None, include_disabled: bool = False) -> list:
    """Every enrich declaration this product stands.

    Returns the NORMALIZED declaration (`params` of the dedup half), so a caller reads
    `reference_views`, `decision_key` and the rest under the names it already knows.

    `include_disabled` stands a declaration written `enabled: false` AS IF it were on. One
    caller wants that - an operator who asks the backfill CLI to sweep a rule they switched
    off (`--force-disabled`) - and it is the same move the flat loader made on its own
    file before that file was retired. Everyone else leaves it False, so OFF still stands
    no rule (판정 399).
    """
    from chain import ingestion_worker, rule_shape

    seen, out = set(), []
    read = ingestion_worker.read_rules_document(chain_rules_path)
    # 🔴 [2026-09-24] AN UNREADABLE FILE IS A REFUSAL, NOT 「NO RULES」. The retired flat
    #    loader put this entry in the collector for ITS file; with it gone, a broken
    #    chain_rules.json reached the report as 「0 rules read」, status ok. The loader
    #    already logs the failure - this only carries it to the list the caller brought.
    if read.get("error") and rejections is not None:
        rejections.append({"scope": "file", "subject": None,
                           "detail": "%s could not be read (%s) - NO enrich rule is in effect"
                                     % (os.path.basename(read["path"]), read["error"])})
    for raw in (read.get("rules") or ()):
        # 🔴 THE DISCRIMINATOR IS `derive`, THE SAME ONE THE LOADER USES (S-234 2단계).
        #    Asking anything else here would be a second answer to 「is this the new
        #    grammar」, free to disagree with the loader about which rules exist.
        if not isinstance(raw, dict) or not isinstance(raw.get("derive"), dict):
            continue
        name = raw.get("name")
        if not name or name in seen:
            continue
        if include_disabled and rule_shape.is_switched_off(raw):
            raw = {**raw, "enabled": True}
        # 🔴 [지시 0cae5199] `rejections` 가 «내려갑니다». 이 좌석이 수집기를 가진 유일한
        #    자리이고, 아래 :refusal 블록은 «규칙 하나가 통째로 안 선» 사실만 실었습니다.
        #    선언이 «서면서» 참조뷰 하나를 떨어뜨리는 것 같은 자리별 사실은 `_validate_rule`
        #    안의 `_record` 가 남기는데, 그 인자가 안 내려가 통합 문법에서는 사라졌습니다.
        #    둘은 겹치지 않습니다 — 거절 경로는 `_record` 를 안 부르고 사유만 돌려줍니다.
        stood, refusal, _notes = rule_shape.expand_declaration(
            raw, known_tables, rejections=rejections)
        # ⚠️ A REFUSED OR SWITCHED-OFF DECLARATION STANDS NO RULE, so it has no views to
        #    offer - and the loader has already said why, in its own words. Saying it
        #    again here would give one fact two authors.
        # 🔴 [판정 636] BUT A CALLER COLLECTING REFUSALS MUST SEE BOTH HALVES. The report
        #    and the graph hand a `rejections` list and render 「what did not stand and
        #    why」; before this seat existed that list could only ever carry the FLAT
        #    file's refusals, so a unified declaration that was refused looked to a
        #    reader exactly like one that was never written. The sentence is the
        #    expander's own - this only carries it to the list the caller brought.
        if refusal or not stood:
            if refusal and rejections is not None:
                rejections.append({"scope": "rule", "subject": name,
                                   "detail": str(refusal)})
            continue
        declared = (stood[0].get("params") or {})
        if declared.get("name"):
            seen.add(name)
            out.append(declared)
    return out


def find(rule_name: str, known_tables: dict = None, chain_rules_path: str = None,
         rejections: list = None, include_disabled: bool = False):
    """The declaration a route was asked about, or None — 「없다」 is a value, not an error.

    ⚠️ [판정 636] THE CALLER KEEPS SAYING 「없다」 IN ITS OWN WORDS. Six seats ask this and
    each refuses differently - an HTTP 404, an `AlignmentViewRequestError`, a sentence that
    lists what IS available. Folding those into one line here would put the product's voice
    where the operator's context is; what this changes is only WHAT THEY LOOKED AT.
    """
    for rule in declarations(known_tables=known_tables,
                             chain_rules_path=chain_rules_path,
                             rejections=rejections,
                             include_disabled=include_disabled):
        if rule.get("name") == rule_name:
            return rule
    return None
