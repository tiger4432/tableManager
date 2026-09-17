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

🔴 THE OTHER READERS ARE NOT WIDENED, AND THE COUNT IS THE POINT. `load_enrichment_rules`
is read from **15 places** (measured with `git grep`, product code): this module, the two
reference-view routes, the dashboard summary, the two alignment routes, the candidate
prober, the graph, the resolve report, models, retroactive, the alignment view service,
and two scripts. All of them are blind to a unified `decide` declaration in exactly the
way these two routes were. The owner scoped this round to the reference view
(「참조뷰 라우트만」), so the other thirteen are UNCHANGED and counted here rather than
quietly widened - and when they move, they move onto this seat instead of each learning
about two files.
"""

import logging

logger = logging.getLogger("Chain.ReferenceView")


def declarations(known_tables: dict = None, chain_rules_path: str = None,
                 enrichment_path: str = None) -> list:
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
    from enrichment import config as enrichment_config

    seen, out = set(), []
    for rule in enrichment_config.load_enrichment_rules(
            path=enrichment_path, known_tables=known_tables):
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
        if refusal or not stood:
            continue
        declared = (stood[0].get("params") or {})
        if declared.get("name"):
            seen.add(name)
            out.append(declared)
    return out


def find(rule_name: str, known_tables: dict = None, chain_rules_path: str = None,
         enrichment_path: str = None):
    """The declaration a route was asked about, or None — 「없다」 is a value, not an error."""
    for rule in declarations(known_tables=known_tables,
                             chain_rules_path=chain_rules_path,
                             enrichment_path=enrichment_path):
        if rule.get("name") == rule_name:
            return rule
    return None
