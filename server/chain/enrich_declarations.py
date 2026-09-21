# -*- coding: utf-8 -*-
"""참조뷰의 «자기 자리» — 인리치 맵퍼 안에 묻혀 있지 않습니다.

> 소유자 2026-09-17: 「인리치는 참조뷰 기능은 «보존»해야 해. v2 로 «따로» 빼되」
> 「ㅇㅇ 여기에 참조뷰 «라우트»만 추가하고」

🔴 WHAT WAS MISSING, AND IT WAS MEASURED BEFORE IT WAS BUILT. A reference view can be
declared in two grammars - `enrichment_rules.json`, and the unified `derive.decide` block
in `chain_rules.json` - and `rule_shape.expand_declaration` carries the views through for
both (probed: `params.reference_views` has the declared label). But every consumer of an
enrich declaration reaches for `enrichment.config.load_enrichment_rules`, which reads ONE
file, so a view written in the unified grammar was declared, carried, and UNREACHABLE.
That is not a route that behaved badly; it is a route that did not exist for half the
declarations, and 「보존」 is not satisfied by a capability that only one grammar can reach.

🔴 ONE SEAT, NOT A SECOND ENDPOINT. The fix is NOT a `/admin/chain/.../references/` beside
the one that is already there - that is 「같은 기능 두 경로」 with the operator left to guess
which grammar they wrote in. The existing pair of routes asks THIS module for the
declaration, and this module is the one place that knows a declaration can be written in
more than one file.

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

logger = logging.getLogger("Chain.EnrichDeclarations")


def declarations(known_tables: dict = None, chain_rules_path: str = None,
                 enrichment_path: str = None, rejections: list = None) -> list:
    """Every enrich declaration this product stands, whichever grammar wrote it.

    Returns the NORMALIZED declarations (the shape `load_enrichment_rules` returns), so a
    caller reads `reference_views`, `decision_key` and the rest under the names they
    already know.

    ⚠️ THE ENRICHMENT FILE WINS A NAME COLLISION, and cannot silently do so: the chain
    loader already refuses a name claimed by two files (`_refuse_names_claimed_twice`), so
    a name reaching here twice has been reported at load. Skipping the second is what
    keeps this list the same length as the list the loader stood.
    """
    from chain import ingestion_worker, rule_shape
    from chain.enrichment import config as enrichment_config

    seen, out = set(), []
    for rule in enrichment_config.load_enrichment_rules(
            path=enrichment_path, known_tables=known_tables, rejections=rejections):
        name = rule.get("name")
        if name and name not in seen:
            seen.add(name)
            out.append(rule)

    read = ingestion_worker.read_rules_document(chain_rules_path)
    for raw in (read.get("rules") or ()):
        # 🔴 THE DISCRIMINATOR IS `derive`, THE SAME ONE THE LOADER USES (S-234 2단계).
        #    Asking anything else here would be a second answer to 「is this the new
        #    grammar」, free to disagree with the loader about which rules exist.
        if not isinstance(raw, dict) or not isinstance(raw.get("derive"), dict):
            continue
        name = raw.get("name")
        if not name or name in seen:
            continue
        stood, refusal, _notes = rule_shape.expand_declaration(raw, known_tables)
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
         enrichment_path: str = None, rejections: list = None):
    """The declaration a route was asked about, or None — 「없다」 is a value, not an error.

    ⚠️ [판정 636] THE CALLER KEEPS SAYING 「없다」 IN ITS OWN WORDS. Six seats ask this and
    each refuses differently - an HTTP 404, an `AlignmentViewRequestError`, a sentence that
    lists what IS available. Folding those into one line here would put the product's voice
    where the operator's context is; what this changes is only WHAT THEY LOOKED AT.
    """
    for rule in declarations(known_tables=known_tables,
                             chain_rules_path=chain_rules_path,
                             enrichment_path=enrichment_path,
                             rejections=rejections):
        if rule.get("name") == rule_name:
            return rule
    return None
