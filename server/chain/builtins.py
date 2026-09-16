# -*- coding: utf-8 -*-
"""What the PRODUCT contributes to the chain: synthesised rules, and the kinds that run them.

🔴 ONE SYNTHESIS SEAT (판정 304). `load_chain_rules` calls `synthesize_chain_rules` and
nothing else, and that function calls each half. 판정 292 forbids two synthesisers; putting
the join half inside `load_enrichment_chain_rules` would have satisfied the letter of that
while making a function named `enrichment_…` read the virtual-join file — a name that lies is
a cost paid by whoever next looks for where a declaration becomes a chain rule. Each half
keeps an honest name and reads its own file; the SEAT is what is singular.

🔴 ONE TABLE OF `builtin:` KINDS (판정 305). Measured before building: `builtin:auto_confirm`
appeared exactly twice, both in `enrichment_config`, and NOTHING read it — S-179 declared the
kind for the loader and graph layers and left execution in the auto-confirm sweep. So this is
the FIRST dispatcher the `builtin:` vocabulary has ever had.

🔵 AND THE TEMPORARY IS OVER (S-195). It carried one kind while auto-confirm still ran from
its own sweep, so a follow-up kind had two ways to run; both are in the table now and there is
one route. What made that survivable in between was that it was WRITTEN DOWN and queued — a
temporary nobody records is just a drift with a date on it.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("Chain.Builtins")


#: (half, what stops running when that half does) - the sentence a failure has to be able
#: to say. 🔴 IT IS A TABLE AND NOT TWO `except` BLOCKS because the two must be reported the
#: same way: a half that fails quietly in a different voice is how 「what is not running」
#: becomes 「nothing is declared」.
_SYNTHESIS_HALVES = (
    ("enrichment", "dedup and auto-confirm rules are NOT running"),
    ("virtual join", "materialised join rules are NOT running"),
)


def synthesize_chain_rules(known_tables: dict = None, failures: list = None) -> list:
    """Every chain rule the product derives from a declaration the operator wrote.

    🔴 THE TWO HALVES FAIL SEPARATELY (판정 452 ②). They used to be one expression, so
    ANYTHING raising in the virtual-join half took the enrichment half down with it - and
    the caller's `except` logged one line and carried on with NO synthesised rules at all,
    dedup and auto-confirm included. That matters this round in particular: step 4 removes
    the `virtual_join` package, which makes that import raise, and the failure would have
    read as 「this box declares no enrichment」 rather than 「the join half is gone」.

    ⚠️ A FAILING HALF IS REPORTED, NEVER GUESSED AT. `failures` collects
    `(half, what stops running, the error)` the way `rejections` does elsewhere in this
    codebase; a caller that passes nothing still gets whichever half stood, because the
    alternative - raising - is what made one half able to kill the other.

    ⚠️ THE ENRICHMENT HALF IS UNCHANGED, BYTE FOR BYTE, and it still runs FIRST. This seat
    only moved its CALL; a test compares the list before against after, because a move that
    quietly reorders or drops a rule would be invisible until a chain stopped firing.
    """
    def _enrichment():
        import enrichment.config
        return enrichment.config.load_enrichment_chain_rules(known_tables=known_tables)

    def _joins():
        import virtual_join.config
        return virtual_join.config.synthesized_join_chain_rules(known_tables=known_tables)

    rules = []
    for (half, stops), produce in zip(_SYNTHESIS_HALVES, (_enrichment, _joins)):
        try:
            rules.extend(produce() or ())
        except Exception as exc:                                   # noqa: BLE001
            logger.error("[ChainRules] the %s half of synthesis failed, so %s: %s",
                         half, stops, exc)
            if failures is not None:
                failures.append({"half": half, "stops": stops, "error": str(exc)})
    return rules


def written_in(rule) -> str:
    """The file a rule THIS SEAT produced was written in, by basename (S-234 ①).

    🔴 FOR THE LOADER'S ONE-NAMESPACE REFUSAL: a name claimed twice is named with the files
    to look in. The join half emits `JOIN_MAPPER` and nothing else out of this seat does, so
    that one cell separates the two files.

    ⚠️ ONLY FOR RULES THAT CAME OUT OF `synthesize_chain_rules`. The loader tags what it read
    from `chain_rules.json` by position, never through here — a unified `decide` written in
    that file also carries `origin: synthesized:` and would otherwise be misfiled.

    🪦 `synthesized_kind_counts` sat here for the 「Synthesized N (a dedup · b auto-confirm ·
    c join)」 boot line. That line folded into the loader's set line, which names every rule
    with its origin and kind, so a count of kinds had no reader left.
    """
    import enrichment.config
    import virtual_join.config

    if (rule or {}).get("mapper") == virtual_join.config.JOIN_MAPPER:
        return os.path.basename(virtual_join.config.VIRTUAL_JOIN_RULES_PATH)
    return os.path.basename(enrichment.config.ENRICHMENT_RULES_PATH)


# ---------------------------------------------------------------------------
# the `builtin:` table
# ---------------------------------------------------------------------------

class UnknownBuiltinKind(ValueError):
    """⛔ REFUSED BY NAME, NEVER IGNORED. A rule naming a kind nothing implements would
    otherwise sit enabled, look live, and never run — the same silence
    `_report_unwatchable_trigger_columns` exists to break for a mistyped trigger column."""


def _run_join(db, rule, row_ids=None, key_values=None, done=None, **_):
    """`builtin:join` — materialise one join rule's answer onto its target rows.

    ⚠️ TWO TRIGGERS, ONE KIND. Target rows moved (cheap, no ceiling) or a reference row moved
    (counts first, refuses over the rule's declared ceiling). The caller says which by which
    argument it passes; both land in the same declaration.
    """
    from virtual_join import executor as vje

    joined = (rule or {}).get("params") or {}
    if key_values is not None:
        return vje.on_reference_rows_changed(db, joined, list(key_values))
    return vje.on_target_rows_changed(db, joined, list(row_ids or ()))


def _run_auto_confirm(db, rule, row_ids=None, done=None, **_):
    """`builtin:auto_confirm` — the enrichment sweep, now reached through the table (S-195).

    🔴 THE WORK IS UNCHANGED; WHAT MOVED IS HOW IT IS FOUND. It ran from
    `_auto_confirm_followed_rows`, called directly on the drain beside this dispatcher — so a
    `follow_up` kind had TWO ways to run and the prohibition on that was carrying a named
    temporary. This closes it: one table, one route.

    🔴 AND THE RULE COMES FROM THE DECLARATION, NOT FROM A SECOND LOOKUP.
    `AutoConfirmCollector` already accepted `rules`; left to itself it called
    `load_enrichment_rules` and re-found what the synthesised rule is already carrying in
    `params`. Two readers of one fact is how they come to disagree — and here the second one
    also re-read a file on a paced path.

    ⚠️ `.active` STILL DECIDES. The global switch, the per-rule knob and 「does any reference
    view declare `candidate_for`」 are the collector's gates and stay there; this seat only
    hands it the rule it was already going to use.

    ⚠️ CONTAINED. A failure here must not cost the ledger follow-up that already succeeded.
    """
    import enrichment.candidates

    table = (done or {}).get("table")
    rows = list(row_ids or ())
    if not table or not rows:
        return {"confirmed": 0, "refused": 0}

    declared = (rule or {}).get("params") or None
    collector = enrichment.candidates.AutoConfirmCollector(
        table, rules=[declared] if isinstance(declared, dict) else None)
    if not collector.active:
        return {"confirmed": 0, "refused": 0}

    collector.collect_rows(db, rows)
    stats = collector.flush(db) or {}
    confirmed = stats.get("confirmed") or 0
    refused = sum((stats.get("refused") or {}).values())
    if done is not None:
        # Values, not a verdict: 「큰 깊이는 값으로 보임」 — a follow-up that confirms nothing
        # and one that never ran are different facts, and the note carries both. The drain
        # loop reads these two keys, so they keep their names.
        done["auto_confirmed"] = confirmed
        done["auto_refused"] = refused
    # 🔴 [S-246] `written` IS WHAT A `builtin:` KIND CALLS ITS ROW COUNT.
    # `join_into.run` and `materialize_rows` already answer under that name, and this one
    # did not - so the follow-up line S-249 added printed `written=None` for auto-confirm,
    # and the registration below would have had nothing to read. `confirmed` and `refused`
    # keep their names for the readers that have them; this adds the count, it does not
    # rename the fact.
    return {"written": confirmed, "confirmed": confirmed, "refused": refused,
            "source_name": enrichment.candidates.SOURCE_NAME}


def ensure_declared_unique_keys(db, rules) -> dict:
    """[S-240] Make the unique key a unified join DECLARED, at load time. Returns a report.

    🔴 THE CELL WAS WRITTEN AND READ BY NOBODY. `key.unique: true` never survived the
    translation (`rule_shape` dropped it), and the only place that builds a `uq_vjoin_*` is
    the OLD read-time shell - so the plan's 「선언이 key.unique 라고 말하면 제품이
    성립시킨다」 and RUN.md's 「제품이 인덱스를 세웁니다」 were both false for a unified join.

    ⚠️ THE SHELL CALLS IT, NOT `join_into`. That module must not import `virtual_join` -
    a boundary its own test asserts - so it hands back the right table, its columns and the
    folds, and this seat, which already knows both halves, does the building.

    ⛔ LOAD TIME, NEVER THE READ PATH (§0-ter ①), and `enabled: false` means ZERO calls
    (판정 399 ③′): a switch that still probes is the defect that took the read path down
    on 2026-09-14.
    """
    from chain import join_key_index as vjc
    from chain import unique_key

    report = {"ensured": [], "skipped": []}
    seen = set()
    for name, table, columns, folds, skip in declared_unique_targets(rules):
        if skip:
            report["skipped"].append((name, skip))
            continue
        # ⚠️ ONE DECLARATION STANDS TWO RULES AND NEEDS ONE INDEX. The target half and
        # its `:reference` companion join the same two tables on the same key, so they ask
        # for the SAME index name - asking twice would probe `pg_index` twice at every
        # reload and report one index as two.
        index_name = vjc.required_index_name(table, columns, folds)
        if index_name in seen:
            continue
        seen.add(index_name)
        report["ensured"].append(
            (name, unique_key.ensure_once(db, name, table, columns, folds)))
    return report


def declared_unique_targets(rules):
    """(name, right table, columns, folds, skip reason) per unified join that DECLARED one.

    🔴 ONE WALKER, BECAUSE THEY ARE ONE QUESTION. 「which index do we build」 and
    「which index do we require」 must never be able to disagree - the day they do, the
    product builds an index at warmup and retracts it on the next read, forever.
    """
    from chain import join_into

    for rule in rules or ():
        if not isinstance(rule, dict):
            continue
        if rule.get("mapper") != join_into.JOIN_INTO_MAPPER:
            continue
        name = rule.get("name")
        if not rule.get("enabled", True):
            yield (name, None, None, None, "enabled=false")
            continue
        if not (rule.get("key") or {}).get("unique"):
            # ⚠️ ABSENT IS NOT 「no」 TO A QUESTION NOBODY ASKED. A declaration that says
            # nothing about uniqueness gets no index and no complaint; `join_into`'s own
            # row-level net still refuses a left row with two right answers.
            continue
        table, columns, folds = join_into.right_key(rule)
        if not table or not columns:
            yield (name, None, None, None, "no right key to cover")
            continue
        # ⚠️ `key.columns` IS A CHECK, NOT A CHOICE. The index has to be built over the
        # join's OWN right key or PostgreSQL will not use it (S-181) - so a list that names
        # other columns cannot be honoured, and honouring it silently would build an index
        # that covers nothing this join compares. It is read so that a typo is a sentence
        # rather than a cell nobody looks at, which is the whole defect of this round.
        declared = [str(column) for column in
                    ((rule.get("key") or {}).get("columns") or ()) if column]
        if declared and declared != list(columns):
            yield (name, table, columns, folds,
                   "key.columns %s is not this join's right key %s — the index covers "
                   "the right key" % (declared, list(columns)))
            continue
        yield (name, table, columns, folds, None)


def declared_unique_index_names(known_tables: dict = None) -> set:
    """Every `uq_vjoin_*` name the LIVE unified declarations require (S-240 · S-248).

    🔴 AN INDEX LIVES EXACTLY AS LONG AS THE JOIN THAT REQUIRES IT - and after S-240
    there are TWO kinds of join that require one. The retraction that enforces that lifetime
    computes 「required」 from the read-time declarations alone, so without this the index
    THIS module builds at warmup is dropped by the next read-path load, rebuilt at the next
    restart, and dropped again: a switch flapping on its own.

    ⚠️ THE DECLARATION IS EXPANDED BY THE SAME JUDGE THE LOADER USES (S-244). A second
    reading of the file would be a second answer to 「what does this declaration stand」,
    and this one has to agree with the seat that built the index.
    """
    from chain import ingestion_worker, rule_shape
    from database import crud
    from chain import join_key_index as vjc

    catalogue = known_tables if known_tables is not None else crud.TABLE_CONFIG
    names = set()
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        stood, refusal, _notes = rule_shape.expand_declaration(raw, catalogue)
        if refusal:
            # ⚠️ The loader already says this out loud; saying it again here would put a
            # refusal on the read path every few seconds - the flood 2026-09-14 was.
            continue
        for _name, table, columns, folds, skip in declared_unique_targets(stood):
            if skip:
                continue
            names.add(vjc.required_index_name(table, columns, folds))
    return names


#: kind -> callable. One table, the registry's posture: a name, a callable, nothing implicit.
BUILTIN_KINDS = {}

#: The kinds whose writer stamps `cell_sources.origin_row_id` — 「이 칸은 어느 행에서 왔나」
#: (판정 434). A kind that is NOT in here writes cells nothing can aim a retraction at, and
#: 판정 434 ④ says that must be answered BY NAME rather than by a quiet nothing.
#:
#: 🔴 REGISTERED BY THE SAME CALL AS THE IMPLEMENTATION, deliberately. A second table filled
#: from a second place is how 「이 종류가 무엇을 하나」 comes to have two answers; `_install`
#: below states both facts about a kind on one line, so they cannot drift apart.
ORIGIN_STAMPING_KINDS = set()


def register_builtin(kind: str, fn, stamps_origin: bool = False):
    existing = BUILTIN_KINDS.get(kind)
    if existing is not None and existing is not fn:
        raise UnknownBuiltinKind(
            "two implementations claim %r; a rule naming it could not say which it meant"
            % kind)
    BUILTIN_KINDS[kind] = fn
    if stamps_origin:
        ORIGIN_STAMPING_KINDS.add(kind)
    return fn


def _rows_handed(kwargs) -> int:
    """How many rows this call was handed. The two trigger arms name them differently."""
    for cell in ("row_ids", "key_values"):
        handed = kwargs.get(cell)
        if isinstance(handed, (list, tuple, set)):
            return len(handed)
    return 0


def run_builtin(kind: str, db, rule, **kwargs):
    """Route one synthesised rule to its implementation, or refuse by name.

    🔴 [S-246] AND REGISTER IT, THE SAME WAY THE OTHER DOOR DOES. 소유자
    2026-09-15: 「체인 대기열에서 안 뜨고 돌고 있었네」. `activity.registry` was started,
    recorded and finished inside `mapper_call.execute_custom_mapper` - the door a FILE
    mapper comes through - and this door did none of the three. So `join_into`,
    `builtin:join` and `auto_confirm` ran with no entry in the queue view, and because the
    loader SEEDS every declared rule as `never_evaluated`, a builtin that had run a
    thousand times still reported 「아직 평가 안 됨」 for the life of the process. 「같은
    기능에 두 경로」, and the half nobody could see was the half that was running.

    ⚠️ THE REFUSAL IS OUTSIDE THE REGISTRATION, deliberately. An unknown kind never ran,
    so an entry saying it did - even for the length of one raise - would be a false
    sentence about a rule this function is in the middle of refusing.
    """
    fn = BUILTIN_KINDS.get(kind)
    if fn is None:
        raise UnknownBuiltinKind(
            "no implementation for %r; known kinds: %s"
            % (kind, ", ".join(sorted(BUILTIN_KINDS)) or "none"))
    from chain import activity

    name = (rule or {}).get("name") or "<unnamed rule>"
    with activity.running(name, kind, (rule or {}).get("target_table") or "<none>",
                          _rows_handed(kwargs),
                          no_rows_reason="the rule wrote no rows") as run:
        result = fn(db, rule, **kwargs)
        # ⚠️ ONLY WHEN THE KIND SAID SO. A kind that reports no count leaves the outcome
        # alone rather than being recorded as 「ran, changed nothing」 - 「안 셌다」 and
        # 「0 이었다」 are different facts and this registry exists because they were being
        # confused.
        written = (result or {}).get("written") if isinstance(result, dict) else None
        if written is not None:
            run.produced(int(written))
        return result


def _install():
    import enrichment.config
    import virtual_join.config
    from chain import join_into

    # `stamps_origin`: `materialize_rows` carries the right row that answered into
    # `GeneralUpdateItem.origin_row_id` (S-280), so what it wrote can be withdrawn when
    # that row is deleted.
    register_builtin(virtual_join.config.JOIN_MAPPER, _run_join, stamps_origin=True)
    # 🔴 [S-237] THE UNIFIED DECLARATION'S `join` KIND, AND IT IS A DIFFERENT ENTRY ON
    # PURPOSE. `builtin:join` is the READ-TIME join and production runs on it; this one
    # WRITES what the declaration says into a column. `register_builtin` refuses two
    # claimants of one id by name, so the distinction is enforced here rather than trusted.
    register_builtin(join_into.JOIN_INTO_MAPPER, join_into.run, stamps_origin=True)
    # S-195: the kind S-179 declared finally has an implementation, so the table carries the
    # whole `builtin:` vocabulary and the named temporary two-path condition is over.
    # ⛔ NOT `stamps_origin`. The sweep's answer comes from a candidate PROBE over a
    # reference view, not from one reference row, so there is no single row to write down —
    # and 판정 434 forbids answering that with a NULL that already means 「기존 행」. The
    # seat names this kind instead (`rule_run.retraction_refusal`).
    register_builtin(enrichment.config.AUTO_CONFIRM_MAPPER, _run_auto_confirm)


_install()
