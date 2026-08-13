"""Lot lineage trace over the canonical ledger — the resolver, the lookup, the walk.

Design source: `docs/architecture/CANONICAL_LEDGER_DESIGN.md` §6 (resolution order)
and `docs/process/LEDGER_SLICE_1_BRIEF.md` §3-2 (query-time resolution, per-hop state).
Neither is edited from here; this module implements them.

🔴 **THREE THINGS LIVE HERE AND TWO OF THEM MUST NOT KNOW ABOUT EACH OTHER.**

    RESOLUTION   `claim_class` / `claim_rank_key` / `resolve`
                 Pure Python over `Claim` objects. Contains no SQL, no table
                 name, no connection. This is "THE resolver" of §6 — there is
                 exactly one, and every hop state in the answer comes out of it.

    LOOKUP       `ClaimLookup` and its subclasses.
                 Fetches claims. Does NOT rank, does NOT decide, does NOT know
                 what a class is. `SqlClaimLookup` runs the recursive CTE against
                 `ledger_events`; `InMemoryClaimLookup` serves a list.

    WALK         `trace`
                 Asks the lookup once, then asks the resolver one question per
                 hop. Its output is the pinned response shape.

**Why the separation is a structural requirement and not a style note.** Measured
2026-08-12 on a 1000-lot synthetic probe (`agent_workspace/reports/
Incremental_materialization_1000lots.md`, synthetic — not production evidence):
query-time resolution holds for LOT-level tracing (0.95 ms/hop) and COLLAPSES for
SLOT-level lineage — 452 ms inline against 0.58 ms materialised, a 780x gap that
goes superlinear (34.8x at 20x the ledger). This slice is lot-level, so it goes
query-time and NOTHING is materialised here. Week 2's void work needs the
slot-level `slot_map` chain and that one cannot go query-time. So the lookup is a
replaceable object: swapping `SqlClaimLookup` for a lookup backed by a
materialised closure table changes ONE constructor argument and rewrites NONE of
the resolver, because the resolver never learns where a `Claim` came from.
`InMemoryClaimLookup` exists to make that swappability a *checked* property
rather than a claim — `test_ledger_trace_pg.py` runs the same trace through both
lookups and asserts the two answers are identical.
"""

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:                                    # same guard crud.py and database.py use
    import paths as _paths
except ImportError:                     # pragma: no cover - import-path fallback
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import paths as _paths


# --------------------------------------------------------------------------
# The claim — one ledger atom as the resolver sees it
# --------------------------------------------------------------------------

#: The v0 lineage vocabulary this slice reads (design §4.2). The translator emits
#: exactly these four; asking for anything else is how the vocabulary grows in
#: silence (brief §5 risk 4), so the walk names them explicitly.
LINEAGE_PREDICATES = ("derived_from", "slot_map", "has_wafer", "register")

#: How deep the walk goes before it stops and SAYS it stopped. A cap that ends
#: the answer without a `terminal_reason` would be indistinguishable from a root.
DEFAULT_MAX_DEPTH = 20


@dataclass(frozen=True)
class Claim:
    """One ledger atom. Field names are the `ledger_events` column names verbatim.

    The envelope is design §3's seven fields and this dataclass adds nothing to
    it — no confidence, no priority, no processed flag. §3's "일부러 뺀 것" list
    says priority belongs to the resolver's config, and that is exactly where it
    is here (`ResolverConfig`), not on the atom.
    """
    id: str
    subject_type: str
    subject_keys: Dict[str, Any]
    predicate: str
    object_kind: str
    object_payload: Dict[str, Any]
    occurred_at: Optional[datetime] = None
    source_who: Optional[str] = None
    source_translator_ver: Optional[str] = None
    source_raw_ref: Optional[str] = None
    supersedes: Optional[str] = None

    @property
    def subject_lot(self):
        return _as_text(self.subject_keys.get("lot")) if self.subject_keys else None


# --------------------------------------------------------------------------
# Resolver config — the class table (design §3: "priority = 해결기 config")
# --------------------------------------------------------------------------

#: Class assignment for §6's four ranks. It is DECLARED data, not a chain of
#: `if` statements buried in the ranking function, because §6 calls the class
#: boundary an invariant and an invariant that is spelled inline gets edited by
#: someone fixing an unrelated tie.
#:
#: An operator can override it with `config/ledger_resolver.json` (config-over-
#: hardcode); the file is optional and a malformed one is refused loudly rather
#: than half-applied.
DEFAULT_RESOLVER_CONFIG = {
    # class 0 — a human's pin. §4.1 canonical vocabulary.
    "pin_predicates": ["pin"],
    # class 1 — a confirmed chain claim.
    "confirmed_predicates": ["frame_confirmed"],
    "confirmed_sources": [],
    "confirmed_payload_flag": "confirmed",
    # class 3 — inference. §3 puts confidence INSIDE the object payload, so the
    # flag is read from there and never from the envelope.
    "inference_sources": [],
    "inference_payload_flag": "inferred",
    # 🔴 class 3 — DERIVATIONS THAT ARE ASSUMPTIONS. Ontology owner's ruling,
    # 2026-08-13. See `CONVENTION_DERIVATIONS_RULE` below for why, and for the
    # standing rule that keeps this list from silently falling behind.
    "inference_derivations": ["slot_preserving"],
    # 🔴 The zone every instant in the response is rendered in. DECLARED — see
    # `DISPLAY_TIMEZONE_RULING`.
    "display_timezone": "Asia/Seoul",
}

#: 🔴 **RULING: the response renders instants in a DECLARED zone (2026-08-13).**
#:
#: The choice was between rendering in a declared zone and emitting UTC for the
#: client to localise. Declared zone, and the reasoning matters more than the
#: choice:
#:
#: **What it replaced was an accident.** `_iso` used to `isoformat()` an aware
#: value verbatim, which meant the offset came from the **PostgreSQL session's**
#: TimeZone. `assy_qa`'s default happens to be `Asia/Seoul` (measured, with no
#: `SET`), so the acceptance datum — source `2026-05-03 02:17:00`, stored
#: `2026-05-02T17:17:00+00:00`, rendered `2026-05-03T02:17:00+09:00` — passed
#: while nothing the ledger declares was doing the work. On a box whose
#: PostgreSQL `TimeZone` is UTC the identical atom serialises as `17:17+00:00`
#: and the operator sees the same nine-hour error that was just repaired, from a
#: different cause, with the ledger's own declaration innocent.
#:
#: **Why not "emit UTC, let the client localise".** It moves the correctness of a
#: fab record onto the viewer's machine zone. The acceptance condition is that
#: the string MATCHES THE SOURCE DOCUMENT on a fab clock, and an operator on a
#: laptop set to another zone would read a different time for the same record
#: with nothing on screen admitting it. A declared zone makes the server's answer
#: self-describing and identical everywhere.
#:
#: **It is the symmetric move.** The translator already DECLARES
#: `occurred_at_timezone` on the write side and refuses the source without it.
#: The read side declaring its render zone is the same discipline, and an
#: unusable declaration is refused loudly here too rather than falling back.
#:
#: ⚠️ Deliberately NOT `utils.time_format.LOCAL_TIMEZONE`: that is the machine's
#: ambient zone resolved at import, which is the same class of defect one step
#: over — a server process started on a differently configured host would render
#: differently with nothing declared anywhere.
DISPLAY_TIMEZONE_RULING = __doc__

#: 🔴 **THE STANDING RULE, so this decision never has to be referred again.**
#:
#: > Any atom whose content depends on a config-declared ASSUMPTION not present
#: > in the source row carries a `#<derivation>` suffix and resolves at CLASS 3
#: > (inference), never class 2 (observation).
#:
#: The class split in §6 is EPISTEMIC, not mechanical. Class 2 is what a source
#: uttered about the world; class 3 is what we concluded under a rule. Measured
#: on the first backfill: across all 14 splits the wafer overlap between the two
#: post-event rows is ZERO, so the slot chain of a split is not in the data at
#: all — it exists only under the declared convention "a split keeps its slot
#: numbers". A conclusion ranks as inference no matter how good the convention is.
#:
#: **The consequence that decides it.** If a real observation ever asserts a
#: different slot mapping for one of those atoms — a bonding log row, a dt
#: inventory row, a hand entry — the observation MUST win automatically, with
#: nobody un-pinning anything. Rank the convention as observation and a config
#: assumption outranks measured reality, which is the exact inversion the
#: layering value exists to prevent (수동 > 자동, generalised: 실측 > 가정).
#:
#: The list is DECLARED here rather than derived, because nothing in the
#: translator config marks a pairing strategy as an assumption — that is a
#: judgement, and judgements are declared. What stops it going stale is not care
#: but a test: `test_ledger_trace_contract.py::
#: test_every_declared_derivation_is_explicitly_classified` enumerates every
#: derivation the translator config can emit and fails on any this resolver has
#: not explicitly placed. A new convention therefore turns the suite red instead
#: of quietly resolving at class 2.
CONVENTION_DERIVATIONS_RULE = __doc__

RESOLVER_CONFIG_FILENAME = "ledger_resolver.json"

_config_lock = threading.Lock()
_config_cache = None            # type: Optional[Dict[str, Any]]


class ResolverConfigError(RuntimeError):
    """The declared resolver config is unusable. Refused at the door, loudly."""


def load_resolver_config(force_reload=False):
    """The resolver's class table. Read once, cached, overridable by config file."""
    global _config_cache
    with _config_lock:
        if _config_cache is not None and not force_reload:
            return _config_cache
        merged = dict(DEFAULT_RESOLVER_CONFIG)
        path = _paths.config_path(RESOLVER_CONFIG_FILENAME)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    declared = json.load(fh)
            except Exception as exc:
                raise ResolverConfigError(
                    f"{RESOLVER_CONFIG_FILENAME} is not readable JSON: {exc}")
            if not isinstance(declared, dict):
                raise ResolverConfigError(
                    f"{RESOLVER_CONFIG_FILENAME} must be a JSON object")
            unknown = set(declared) - set(DEFAULT_RESOLVER_CONFIG)
            if unknown:
                raise ResolverConfigError(
                    f"{RESOLVER_CONFIG_FILENAME} declares unknown keys: "
                    f"{sorted(unknown)}")
            merged.update(declared)
        _config_cache = merged
        return merged


def set_resolver_config(config):
    """Install a config for this process. Tests use it; nothing else should."""
    global _config_cache
    with _config_lock:
        _config_cache = dict(DEFAULT_RESOLVER_CONFIG) if config is None else dict(config)
        return _config_cache


# --------------------------------------------------------------------------
# THE RESOLVER — §6, one of them, total
# --------------------------------------------------------------------------

CLASS_PIN = 0
CLASS_CONFIRMED = 1
CLASS_OBSERVATION = 2
CLASS_INFERENCE = 3

CLASS_NAMES = {0: "pin", 1: "confirmed", 2: "observation", 3: "inference"}


def is_convention_backed(claim, config=None):
    """True when this atom's content rests on a DECLARED ASSUMPTION.

    Read off the `#<derivation>` suffix the translator already writes into
    `source_translator_ver` — no twelfth column, and no second place for the
    fact to live. See `CONVENTION_DERIVATIONS_RULE`.
    """
    cfg = config or load_resolver_config()
    basis = claim_basis(claim)
    return basis is not None and basis in tuple(cfg["inference_derivations"])


def claim_class(claim, config=None):
    """§6's four ranks: 0 pin > 1 confirmed chain claim > 2 observation > 3 inference."""
    cfg = config or load_resolver_config()
    if claim.predicate in tuple(cfg["pin_predicates"]):
        return CLASS_PIN
    payload = claim.object_payload or {}
    if (claim.predicate in tuple(cfg["confirmed_predicates"])
            or (claim.source_who or "") in tuple(cfg["confirmed_sources"])
            or payload.get(cfg["confirmed_payload_flag"]) is True):
        return CLASS_CONFIRMED
    # 🔴 A conclusion drawn under a declared convention is INFERENCE, however
    # good the convention is. `CONVENTION_DERIVATIONS_RULE` carries the reasoning
    # and, more importantly, the consequence: this is what makes a later real
    # observation of the same slot mapping win AUTOMATICALLY, with nobody
    # un-pinning anything.
    if is_convention_backed(claim, cfg):
        return CLASS_INFERENCE
    if ((claim.source_who or "") in tuple(cfg["inference_sources"])
            or payload.get(cfg["inference_payload_flag"]) is True):
        return CLASS_INFERENCE
    return CLASS_OBSERVATION


def claim_rank_key(claim, config=None):
    """The TOTAL order of §6. Smaller wins. Five levels, one tuple.

    🔴 **THIS IS THE SAME OPERATION AS `crud.compute_priority_value`, AND IT IS
    DELIBERATELY THE SAME SHAPE.** That function ranks cell source layers; this
    one ranks ledger claims. Both are a lexicographic tuple whose OUTERMOST
    element is the authority level, with every tiebreak sealed INSIDE the tuple
    after it — which is precisely what makes "a tiebreak can never promote a
    lower authority over a higher one" true by construction rather than by a
    reviewer remembering to check. §6 says so in words ("2·3층은 계급을 넘지
    못한다 — SSOT §4 「우선순위 결정」과 동일 규칙"); this is those words as a
    tuple. `test_ledger_trace.py::test_rank_key_matches_crud_tuple_shape` pins
    the correspondence so the two cannot drift into two spellings of one rule.

    Two levels are not re-implemented at all but CALLED:

      * the registration priority is `crud.get_source_priority`, i.e. the SAME
        `SOURCE_PRIORITY` map the display layering uses (user 0 < collision_merge
        1 < pipeline_parser 2 < custom_script 3 < chain_ingestion 4, unregistered
        99). A second ranking map would be the "서열 이원화" `resolve_priority_map`
        was written to prevent.
      * the timestamp normalisation is `crud.resolution_ingested_at`, which
        already encodes the naive-vs-aware rule (`datetime.now()` is local, a
        `timestamptz` read-back is aware, comparing them raises TypeError).

    The levels:

      0. **class** — §6's 0/1/2/3. The boundary. Nothing below can cross it.
      1. **registration priority** — the declared ranking of `source_who`.
      2a. **dated beats undated** — a claim with no `occurred_at` sorts AFTER one
          that has it. Without 2a the next level would have to order `None`
          against a float, and a legacy undated atom could displace a dated one.
      2b. **`occurred_at` descending** — the most recent claim within one rank is
          the current statement of fact.
      3. **event id ascending** — the level that makes the order TOTAL. Two atoms
          CAN carry the same `occurred_at`: one source event translates to nine
          atoms and they all inherit one `event_time`. Without this level the
          answer would fall back to whatever order the SELECT returned rows in,
          which is physical heap order — the exact defect measured on `assy_qa`
          2026-08-11, where a VACUUM FULL could change a displayed value with no
          write and no audit entry.

    🔴 **Why (2b, 3) is jointly total, which is not the obvious argument.** The
    obvious one is "`id` is a unique primary key, so level 3 always decides", and
    it is WRONG. `ledger_events` is partitioned on `occurred_at`, and PostgreSQL
    requires the partition key to appear in every unique constraint on a
    partitioned table — `PRIMARY KEY (id)` is REFUSED outright (verified on the
    isolated `assy_qa`, PostgreSQL 18.3, 2026-08-13). The key can only be
    `(id, occurred_at)`, so a repeated `id` at a different `occurred_at` is a row
    the database will happily accept.

    The order survives that, and by the constraint rather than by hope: two
    claims tying at level 2b have the SAME `occurred_at`, two claims tying at
    level 3 have the SAME `id`, and tying at BOTH means violating the primary
    key. Levels 2b and 3 together ARE the primary key, so the total order rests
    on something the database enforces instead of on an assumption about what the
    translator mints.
    """
    cfg = config or load_resolver_config()
    ts = _occurred_epoch(claim)
    return (
        claim_class(claim, cfg),                 # 0. class — the boundary
        _registration_priority(claim.source_who),  # 1. declared ranking
        0 if ts is not None else 1,              # 2a. dated beats undated
        -ts if ts is not None else 0.0,          # 2b. newest first
        str(claim.id),                           # 3. total order, always decides
    )


_crud_module = None


def _crud():
    """`database.crud`, imported lazily — this module must be importable by a
    worker that has no ORM session, and the ranking levels it borrows are the
    only reason it is needed at all.

    ONE spelling, no `except ImportError` fallback. The obvious-looking fallback
    `import crud` is not a fallback at all: there is no top-level `crud` module,
    only `server/database/crud.py`, so the second arm could only ever raise a
    SECOND ImportError from inside the handler for the first — turning a clear
    failure into a confusing one. `test_prod_import_env.py` caught it, which is
    exactly what that test is for.
    """
    global _crud_module
    if _crud_module is None:
        from database import crud as _c
        _crud_module = _c
    return _crud_module


def _registration_priority(source_who):
    """The declared source ranking — `crud`'s map, not a second one."""
    return _crud().get_source_priority(source_who or "")


def _occurred_epoch(claim):
    """`occurred_at` as absolute POSIX seconds, via `crud`'s normalisation."""
    if claim.occurred_at is None:
        return None
    return _crud().resolution_ingested_at({"ingested_at": claim.occurred_at})


def claim_basis(claim):
    """The DERIVATION that produced this atom, or None — read off
    `source_translator_ver`'s `#<derivation>` suffix.

    🔴 No twelfth column, and no new field on the hop. The translator writes
    `<source>/<cfg version>/rules:<hash>#<derivation>` into the provenance column
    it already has, precisely so the rule behind one atom is queryable
    (`LIKE '%#slot_preserving'`) without the envelope growing. This reads the same
    suffix and puts it in the hop's `reason`, where a human is already looking.

    Why it belongs on the screen at all: some atoms rest on an operator's DECLARED
    CONVENTION rather than on something the source uttered — "a split keeps its
    slot numbers" is a judgement, and 127 of the first 878 real atoms exist only
    because of it. An investigator who cannot tell those from an uttered fact is
    being handed a conclusion dressed as an observation.

    It is reported VERBATIM and never classified here. Which derivations are
    conventions and which are utterances is the translator config's knowledge, and
    a list of them copied into this module would be a second spelling that goes
    stale the first time a source is added.
    """
    ver = claim.source_translator_ver or ""
    if "#" not in ver:
        return None
    basis = ver.rsplit("#", 1)[1].strip()
    return basis or None


@dataclass
class Resolution:
    """One hop's answer plus WHY it has the state it has."""
    state: str                       # "resolved" | "candidate" | "unresolvable"
    winner: Optional[Claim]
    answer: Any                      # the extracted answer of the winning claim
    rank: Optional[int]
    n: Optional[int]
    reason: str
    top_class: Optional[int] = None
    competing: Tuple = ()            # the distinct answers inside the top class


def resolve(claims, answer_of, config=None, subject_label="", predicate=""):
    """§6 applied to one question. THE resolver — every hop state comes from here.

    `answer_of(claim)` extracts the thing the caller is actually asking for (a
    parent lot, a wafer id, a slot). Competition is measured on the ANSWER, not
    on the claim count: three atoms that all name the same parent lot are three
    witnesses agreeing, not a contest, and calling that `candidate` would teach
    the screen to cry wolf.

    🔴 **`n` counts DISTINCT ANSWERS THAT WERE IN CONTENTION, across classes.**
    The class decides WHICH answer is followed; it does not decide whether a
    disagreement happened. So a lower-class claim naming a different answer still
    counts, and the hop reads `candidate` — the ranking is never in doubt, but
    the operator is told that something disagreed.

    The case that forced this shape (ontology owner, 2026-08-13): a `slot_map`
    atom produced under the `slot_preserving` convention resolves at class 3, and
    if a real observation later asserts a different mapping the observation wins
    automatically. If that hop still rendered `resolved`, the screen would show a
    measurement silently overruling an assumption and say nothing about it — and
    "where the chain disagrees, and why" is the entire product. A claim that
    agrees with the winner is NOT contention: agreement across classes stays
    `resolved`, because a screen that cries wolf is read as noise on the day it
    is right.
    """
    cfg = config or load_resolver_config()
    claims = list(claims)
    if not claims:
        return Resolution(
            state="unresolvable", winner=None, answer=None, rank=None, n=None,
            reason=f"[no_claim] {predicate} 원자 없음 · {subject_label}")

    usable = [c for c in claims if answer_of(c) is not None]
    if not usable:
        return Resolution(
            state="unresolvable", winner=None, answer=None, rank=None, n=None,
            reason=(f"[unusable_payload] {predicate} {len(claims)}건 · "
                    f"목적어에 답 없음 · {subject_label}"),
            top_class=None)

    ranked = sorted(usable, key=lambda c: claim_rank_key(c, cfg))
    winner = ranked[0]
    top_class = claim_class(winner, cfg)
    peers = [c for c in ranked if claim_class(c, cfg) == top_class]
    outranked = [c for c in ranked if claim_class(c, cfg) != top_class]

    def distinct_answers(group):
        out = []
        for c in group:
            a = answer_of(c)
            if a not in out:
                out.append(a)
        return out

    agreed = distinct_answers(peers)
    dissent = [a for a in distinct_answers(outranked) if a not in agreed]
    contenders = agreed + dissent

    n = len(contenders)
    cls_name = CLASS_NAMES.get(top_class, str(top_class))

    if n == 1:
        if len(peers) == 1 and not outranked:
            reason = (f"[single] {predicate} 1건 · class={top_class} {cls_name}"
                      f" · src={winner.source_who or '?'}")
        elif outranked:
            reason = (f"[class_wins] class={top_class} {cls_name} {len(peers)}건 · "
                      f"하위 계급 {len(outranked)}건도 같은 답")
        else:
            reason = (f"[agreed] {predicate} {len(peers)}건 전부 동일 답 · "
                      f"class={top_class} {cls_name}")
        return Resolution(state="resolved", winner=winner, answer=agreed[0],
                          rank=1, n=1, reason=_with_basis(reason, winner, cfg),
                          top_class=top_class, competing=tuple(contenders))

    if dissent:
        # A lower class disagreed. NAME what it rests on, because "an assumption
        # disagreed with a measurement" and "two measurements disagreed" are
        # different situations and the operator acts on them differently.
        losers = []
        for c in outranked:
            a = answer_of(c)
            if a in dissent and a not in [x for x, _ in losers]:
                losers.append((a, _basis_label(c, cfg)))
        shown = " / ".join(f"{a}({lbl})" if lbl else str(a) for a, lbl in losers[:3])
        reason = (f"[candidate] class={top_class} {cls_name} 답 {agreed[0]} · "
                  f"하위 계급 반대 {len(dissent)}종 ({shown}) · 1순위 {agreed[0]}")
    else:
        shown = " / ".join(str(a) for a in agreed[:4])
        if len(agreed) > 4:
            shown += f" / +{len(agreed) - 4}"
        reason = (f"[candidate] class={top_class} {cls_name} 내 답 {n}종 ({shown}) · "
                  f"1순위 {agreed[0]}")
    return Resolution(state="candidate", winner=winner, answer=agreed[0],
                      rank=1, n=n, reason=_with_basis(reason, winner, cfg),
                      top_class=top_class, competing=tuple(contenders))


def _basis_label(claim, config=None):
    """`convention:<name>` when the atom rests on a declared assumption, else
    `basis=<name>` — the WORD is the point.

    An operator reading `basis=slot_preserving` learns a rule's name. An operator
    reading `convention:slot_preserving` learns that this hop is not a
    measurement. That difference is the whole reason the ruling exists, so it is
    carried in the vocabulary of the sentence rather than left to be inferred
    from the name.
    """
    basis = claim_basis(claim)
    if basis is None:
        return None
    return (f"convention:{basis}" if is_convention_backed(claim, config)
            else f"basis={basis}")


def _with_basis(reason, winner, config=None):
    label = _basis_label(winner, config)
    return f"{reason} · {label}" if label else reason


def live_claims(claims):
    """Drop claims a later atom superseded. §3: 정정·철회 = 새 원자.

    Applied HERE and not in the lookup on purpose: supersession is part of "which
    claim is current", so putting it in the lookup would make every lookup
    implementation re-spell it — the second spelling problem again. It is safe to
    do over a fetched set because a correction is about the same subject (§3), so
    the superseding atom is in the same neighbourhood the walk already fetched.
    """
    claims = list(claims)
    retired = {str(c.supersedes) for c in claims if c.supersedes}
    if not retired:
        return claims
    return [c for c in claims if str(c.id) not in retired]


# --------------------------------------------------------------------------
# THE LOOKUP — replaceable. Knows nothing about ranking.
# --------------------------------------------------------------------------

@dataclass
class Neighbourhood:
    """Everything the walk needs, fetched. No ordering decision has been taken."""
    claims: List[Claim] = field(default_factory=list)
    lots: Tuple = ()
    truncated: bool = False
    truncation_reason: Optional[str] = None


class ClaimLookup:
    """Fetch claims. Two primitives, and a `neighbourhood` written in terms of them.

    A materialised lookup (week 2, slot-level) overrides `reachable_lots` with a
    single indexed SELECT against a closure table and inherits everything else.
    `SqlClaimLookup` overrides `neighbourhood` instead, to do both primitives in
    one round trip. Neither override touches the resolver, and that is the point.
    """

    def reachable_lots(self, lot, max_depth):
        raise NotImplementedError

    def claims_for_lots(self, lots, predicates=LINEAGE_PREDICATES):
        raise NotImplementedError

    def neighbourhood(self, lot, max_depth=DEFAULT_MAX_DEPTH,
                      predicates=LINEAGE_PREDICATES):
        lots, truncated, reason = self.reachable_lots(lot, max_depth)
        claims = self.claims_for_lots(lots, predicates)
        return Neighbourhood(claims=list(claims), lots=tuple(lots),
                             truncated=truncated, truncation_reason=reason)


class InMemoryClaimLookup(ClaimLookup):
    """A lookup over a list. Exercises the DEFAULT `neighbourhood` path, so a
    trace served from it and a trace served from `SqlClaimLookup` agreeing is
    evidence the two primitives and the one-shot CTE compute the same set."""

    def __init__(self, claims):
        self._claims = list(claims)

    def reachable_lots(self, lot, max_depth):
        by_lot = {}
        for c in self._claims:
            if c.predicate == "derived_from" and c.subject_lot:
                parent = _payload_lot(c)
                if parent:
                    by_lot.setdefault(c.subject_lot, []).append(parent)
        seen = [lot]
        seen_set = {lot}
        frontier = [lot]
        depth = 0
        while frontier and depth < max_depth:
            nxt = []
            for cur in frontier:
                for parent in by_lot.get(cur, ()):
                    if parent not in seen_set:
                        seen_set.add(parent)
                        seen.append(parent)
                        nxt.append(parent)
            frontier = nxt
            depth += 1
        truncated = bool(frontier)
        return seen, truncated, ("[depth_cap] %d홉에서 조회 중단" % max_depth
                                 if truncated else None)

    def claims_for_lots(self, lots, predicates=LINEAGE_PREDICATES):
        wanted = set(lots)
        preds = set(predicates)
        return [c for c in self._claims
                if c.subject_type == "Lot" and c.subject_lot in wanted
                and c.predicate in preds]


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: The whole neighbourhood in one round trip: the recursive CTE walks Lot -> Lot
#: on `derived_from` and the outer SELECT drags back every lineage atom of every
#: lot it reached. Used by `OneShotSqlClaimLookup`, which is the MEASURED-WORSE
#: alternative and is kept only so the finding stays reproducible.
#:
#: 🔴 It does NOT rank and it does NOT filter superseded atoms. Both of those are
#: the resolver's job (see `resolve` / `live_claims`); a CTE that ordered the
#: candidates would have to be re-written in the materialised lookup, which is
#: the shape the brief forbids.
#:
#: `CYCLE lot SET is_cycle USING path` (PostgreSQL 14+) is the cycle guard. A
#: `UNION` on (lot, depth) is NOT one — the same lot at two depths is two
#: distinct rows, so a genuine cycle would spin until the depth cap and report
#: `depth_cap` for what is really a loop. The screen exists to say WHY, so those
#: two must not be told apart by a guess.
_TRACE_CTE = """
WITH RECURSIVE reach(lot, depth) AS (
        SELECT CAST(%(start_lot)s AS text), 0
    UNION ALL
        SELECT COALESCE(e.object_payload->'keys'->>'lot', e.object_payload->>'lot'), r.depth + 1
        FROM reach r
        JOIN {relation} e
          ON e.subject_type = 'Lot'
         AND e.subject_keys->>'lot' = r.lot
         AND e.predicate = 'derived_from'
        WHERE r.depth < %(max_depth)s
          AND COALESCE(e.object_payload->'keys'->>'lot', e.object_payload->>'lot') IS NOT NULL
) CYCLE lot SET is_cycle USING path
, reached AS (
    -- One row per lot, not one per PATH. A diamond genealogy reaches the same
    -- lot twice; without this the join would return each of that lot's claims
    -- twice and the resolver would count one witness as two.
    SELECT lot, min(depth) AS depth
    FROM reach WHERE NOT is_cycle AND lot IS NOT NULL GROUP BY lot
)
SELECT e.id, e.subject_type, e.subject_keys, e.predicate, e.object_kind,
       e.object_payload, e.occurred_at, e.source_who, e.source_translator_ver,
       e.source_raw_ref, e.supersedes,
       r.depth
FROM reached r
JOIN {relation} e
  ON e.subject_type = 'Lot'
 AND e.subject_keys->>'lot' = r.lot
 AND e.predicate = ANY(%(predicates)s)
"""

_REACH_ONLY_CTE = """
WITH RECURSIVE reach(lot, depth) AS (
        SELECT CAST(%(start_lot)s AS text), 0
    UNION ALL
        SELECT COALESCE(e.object_payload->'keys'->>'lot', e.object_payload->>'lot'), r.depth + 1
        FROM reach r
        JOIN {relation} e
          ON e.subject_type = 'Lot'
         AND e.subject_keys->>'lot' = r.lot
         AND e.predicate = 'derived_from'
        WHERE r.depth < %(max_depth)s
          AND COALESCE(e.object_payload->'keys'->>'lot', e.object_payload->>'lot') IS NOT NULL
) CYCLE lot SET is_cycle USING path
SELECT lot, min(depth) AS depth
FROM reach WHERE NOT is_cycle AND lot IS NOT NULL GROUP BY lot
"""


class SqlClaimLookup(ClaimLookup):
    """The ledger itself: a recursive CTE for the reach, an indexed fetch for the
    claims. TWO round trips, and that is a measured choice rather than an
    oversight — see `OneShotSqlClaimLookup` for the one that was rejected.

    `relation` is the seam. It is the ONLY thing that has to change to point the
    walk at a materialised projection instead of at `ledger_events`, and it is
    validated as a bare identifier because it is interpolated into SQL (a bound
    parameter cannot name a relation).
    """

    def __init__(self, connection, relation="ledger_events"):
        if not _IDENTIFIER.match(relation or ""):
            raise ValueError(f"relation must be a bare SQL identifier: {relation!r}")
        self.connection = connection
        self.relation = relation

    def reachable_lots(self, lot, max_depth):
        sql = _REACH_ONLY_CTE.format(relation=self.relation)
        rows = self._execute(sql, {"start_lot": lot, "max_depth": int(max_depth)})
        lots = [r[0] for r in rows if r[0] is not None]
        truncated = any(int(r[1] or 0) >= int(max_depth) for r in rows)
        return lots, truncated, (f"[depth_cap] {max_depth}홉에서 조회 중단"
                                 if truncated else None)

    def claims_for_lots(self, lots, predicates=LINEAGE_PREDICATES):
        if not lots:
            return []
        sql = (f"SELECT id, subject_type, subject_keys, predicate, object_kind, "
               f"object_payload, occurred_at, source_who, source_translator_ver, "
               f"source_raw_ref, supersedes FROM {self.relation} "
               f"WHERE subject_type = 'Lot' "
               f"AND subject_keys->>'lot' = ANY(%(lots)s) "
               f"AND predicate = ANY(%(predicates)s)")
        rows = self._execute(sql, {"lots": [str(x) for x in lots],
                                   "predicates": list(predicates)})
        return [_claim_from_row(r) for r in rows]

    def _execute(self, sql, params):
        """Run `sql` on either a DBAPI connection or a SQLAlchemy Connection."""
        conn = self.connection
        if hasattr(conn, "cursor"):                      # psycopg2 connection
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        # SQLAlchemy Connection / Session — pyformat params go through exec_driver_sql
        exec_driver = getattr(conn, "exec_driver_sql", None)
        if exec_driver is None and hasattr(conn, "connection"):   # Session
            exec_driver = conn.connection().exec_driver_sql       # pragma: no cover
        return list(exec_driver(sql, params))


class OneShotSqlClaimLookup(SqlClaimLookup):
    """The whole neighbourhood in ONE round trip. **Measured slower — kept as the
    rejected alternative, not as the default.**

    Interleaved arms, rotated order, 40 rounds, this box, synthetic ledger,
    2026-08-13 (ms per 14-hop trace):

        ledger     one-shot   two-step (default)
        18,000       8.63        2.22
        360,000      2.07        2.15

    At 360k the two are the same query within noise (1.04x). At 18k the one-shot
    is 4x WORSE, and `EXPLAIN` says why: the outer join's driving side is the
    recursive CTE, and **PostgreSQL cannot estimate a recursive CTE's output — it
    uses a fixed guess** (it estimated 149-200 rows against an actual 5). On the
    small ledger that fiction made a hash join with a SEQ SCAN OF THE WHOLE
    PARTITION look cheaper than five index probes, so the cost of one trace
    became O(ledger).

    The two-step is immune because its second query is `= ANY(<array of 5>)` —
    the planner counts the array, so the estimate is grounded in a fact instead
    of a constant, and the plan is an index scan at both sizes (0.97x across a
    20x ledger, i.e. flat).

    🔴 The hazard is NOT "small ledgers are slow". It is that the join method for
    this query is chosen from a number that does not come from the data, so a
    ledger that grows past a crossover can flip to O(ledger) per trace with no
    code change. That is the kind of defect that ships green.
    """

    def neighbourhood(self, lot, max_depth=DEFAULT_MAX_DEPTH,
                      predicates=LINEAGE_PREDICATES):
        sql = _TRACE_CTE.format(relation=self.relation)
        rows = self._execute(sql, {"start_lot": lot, "max_depth": int(max_depth),
                                   "predicates": list(predicates)})
        claims = []
        lots = []
        max_seen = 0
        for row in rows:
            claims.append(_claim_from_row(row))
            subj = (row[2] or {}).get("lot")
            if subj is not None and subj not in lots:
                lots.append(subj)
            if row[11] is not None:
                max_seen = max(max_seen, int(row[11]))
        truncated = max_seen >= int(max_depth)
        return Neighbourhood(
            claims=claims, lots=tuple(lots), truncated=truncated,
            truncation_reason=(f"[depth_cap] {max_depth}홉에서 조회 중단"
                               if truncated else None))


def _claim_from_row(row):
    payload = row[5]
    if isinstance(payload, str):                          # pragma: no cover
        payload = json.loads(payload)
    keys = row[2]
    if isinstance(keys, str):                             # pragma: no cover
        keys = json.loads(keys)
    return Claim(
        id=str(row[0]), subject_type=row[1], subject_keys=keys or {},
        predicate=row[3], object_kind=row[4], object_payload=payload or {},
        occurred_at=row[6], source_who=row[7], source_translator_ver=row[8],
        source_raw_ref=row[9],
        supersedes=str(row[10]) if row[10] is not None else None)


# --------------------------------------------------------------------------
# Payload readers — the ONE place a predicate's object shape is spelled
# --------------------------------------------------------------------------

def _as_text(value):
    return None if value is None else str(value)


def _object_key(claim, name):
    """An IDENTITY field of an `entity_ref` object payload.

    The payload shape is the translator's `envelope.entity_ref`:
    `{"type": ..., "keys": {...}, "qualifiers": {...}}`. Identity lives under
    `keys` and everything said ABOUT the object lives under `qualifiers`, and the
    separation is load-bearing rather than tidy: `has_wafer`'s `slot` is a
    qualifier, so a flat payload would read `slot` as part of the wafer's
    identity. Reading the two through separate accessors is how that distinction
    survives on this side of the boundary too.

    The flat spelling is also accepted. Not as tolerance for sloppiness — it is
    what a materialised projection or a hand-built fixture naturally produces,
    and a reader that refuses it would make the lookup NOT swappable.
    """
    p = claim.object_payload or {}
    keys = p.get("keys")
    if isinstance(keys, dict) and keys.get(name) is not None:
        return _as_text(keys[name])
    return _as_text(p.get(name)) if p.get(name) is not None else None


def _object_qualifier(claim, name):
    """A QUALIFIER of an `entity_ref` object payload — what is said about it."""
    p = claim.object_payload or {}
    quals = p.get("qualifiers")
    if isinstance(quals, dict) and quals.get(name) is not None:
        return quals[name]
    keys = p.get("keys")
    if isinstance(keys, dict):          # flat fixtures put everything together
        return p.get(name)
    return p.get(name)


def _payload_lot(claim):
    """The object lot of a `derived_from` / `slot_map` atom."""
    return _object_key(claim, "lot")


def _payload_wafer(claim):
    """The wafer named by a `has_wafer` atom."""
    return _object_key(claim, "wafer")


def _payload_slot(claim):
    """The slot a `has_wafer` atom puts its wafer in — a QUALIFIER, not identity."""
    return _slot_text(_object_qualifier(claim, "slot"))


def _slot_text(value):
    """Slots arrive as `3`, `"3"` and `"03"` from three sources. Compared as text
    with leading zeros stripped, because `3 != "3"` is how a chain silently
    reads as broken."""
    if value is None or value == "":
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lstrip("0").isdigit():
        return str(int(s))
    return s


def _slot_map_pair(claim):
    """`(from, to)` of a `slot_map` atom, as the atom spells them.

    Design §4.2 says `slot_map` is `Lot -> Lot + {from, to}` and does NOT say
    which side `from` names. So this reads the pair verbatim and the WALK decides
    the direction from which lot is the SUBJECT — see `_map_slot`. Guessing here
    would put a wrong slot on the screen; the walk's way puts an honest
    `unresolvable` there when the pair does not fit.

    The translator's convention, read off its code and pinned by
    `test_ledger_trace_contract.py`: subject = PARENT, object = CHILD,
    `from` = the parent-side slot, `to` = the child-side slot.
    """
    a = _slot_text(_object_qualifier(claim, "from"))
    b = _slot_text(_object_qualifier(claim, "to"))
    return a, b


# --------------------------------------------------------------------------
# THE WALK — asks the lookup once, then the resolver once per question
# --------------------------------------------------------------------------

def _lot_node(lot, slot=None):
    node = {"type": "Lot", "keys": {"lot": lot}}
    if slot is not None:
        node["slot"] = slot
    return node


def _wafer_node(wafer):
    return {"type": "Wafer", "keys": {"wafer": wafer}}


def _iso(dt, zone):
    """ISO 8601, `T` separator, rendered in the DECLARED zone. See
    `DISPLAY_TIMEZONE_RULING`.

    Every instant in the response goes through here and through `zone`, so the
    output does not depend on the PostgreSQL session's TimeZone, on the server
    process's ambient zone, or on the viewer's machine. The same atom renders the
    same string everywhere, which is what makes "matches the source document"
    checkable at all.

    A naive value is INTERPRETED in the declared zone rather than in the
    machine's — only a hand-built fixture can produce one (the column is NOT NULL
    `timestamptz`), and reading it ambiently would reintroduce the defect this
    rule exists to close.
    """
    if dt is None:
        return None
    if isinstance(dt, str):                               # pragma: no cover
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return dt.astimezone(zone).isoformat()


def resolve_display_zone(config=None):
    """The declared render zone as a tzinfo. Refused loudly if unusable.

    No fallback to UTC and no fallback to the machine zone: a display zone that
    silently became something else is precisely the failure being designed out,
    and a screen that renders a fab record in the wrong zone looks completely
    normal.
    """
    cfg = config or load_resolver_config()
    name = cfg.get("display_timezone") or DEFAULT_RESOLVER_CONFIG["display_timezone"]
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception as exc:
        raise ResolverConfigError(
            f"display_timezone {name!r} is not a usable IANA zone: {exc}. "
            f"On a bare Windows install this usually means the `tzdata` package "
            f"is missing.")


def _hop(frm, to, resolution, predicate, zone):
    """One hop in the pinned response shape.

    `predicate` is the one field added to the pinned hop dict — additive, never
    a rename or a removal. Without it a client cannot tell a `has_wafer` hop from
    a `derived_from` hop except by parsing the prose in `reason`, and the whole
    point of this screen is that the prose is for a human.
    """
    winner = resolution.winner
    return {
        "from": frm,
        "to": to,
        "predicate": predicate,
        "state": resolution.state,
        "rank": resolution.rank,
        "n": resolution.n,
        "reason": resolution.reason,
        "occurred_at": (_iso(winner.occurred_at, zone)
                        if winner is not None else None),
        "event_id": str(winner.id) if winner is not None else None,
    }


def trace(lot, slot=None, lookup=None, config=None, max_depth=DEFAULT_MAX_DEPTH):
    """Walk the lineage of `(lot, slot)` and return the pinned response shape.

    🔴 **AN EMPTY `hops` LIST IS IMPOSSIBLE BY CONSTRUCTION AND THAT IS THE WHOLE
    FEATURE.** Brief §3-2: "끊긴 자리가 이유와 함께 나와야 한다. 빈 결과 금지 —
    어느 홉에서 왜 끊겼는지가 이 화면의 존재 이유다." Against an EMPTY ledger this
    returns one `unresolvable` hop naming the lot that has no atoms, plus a
    `terminal_reason`. `test_ledger_trace.py::test_empty_ledger_still_answers`
    holds that door shut.

    Every hop is one QUESTION and its answer, in the order the walk asks them:

        has_wafer(lot, slot)          -> which wafer sits at this position
        derived_from(lot)             -> which lot this one came from
        slot_map(lot -> parent, slot) -> where this position was in the parent

    so a broken chain names the question that could not be answered, not just
    "the chain is short".
    """
    cfg = config or load_resolver_config()
    if lookup is None:
        raise ValueError("trace() needs a ClaimLookup - resolution and lookup "
                         "are separate on purpose")

    lot = _as_text(lot)
    slot = _slot_text(slot)

    nb = lookup.neighbourhood(lot, max_depth=max_depth)
    claims = live_claims(nb.claims)

    index = {}
    lots_with_atoms = set()
    for c in claims:
        if c.subject_type != "Lot":
            continue
        index.setdefault((c.subject_lot, c.predicate), []).append(c)
        lots_with_atoms.add(c.subject_lot)

    def at(l, predicate):
        return index.get((l, predicate), [])

    # Resolved ONCE for the whole answer, so every instant in one response is on
    # one clock even if the config were reloaded mid-walk.
    zone = resolve_display_zone(cfg)

    hops = []
    terminal_reason = None
    cur_lot, cur_slot = lot, slot
    visited = [lot]
    depth = 0

    while True:
        if cur_lot not in lots_with_atoms:
            res = Resolution(
                state="unresolvable", winner=None, answer=None, rank=None, n=None,
                reason=f"[unknown_subject] lot={cur_lot} · 원장에 원자 0")
            hops.append(_hop(_lot_node(cur_lot, cur_slot), None, res,
                             "register", zone))
            terminal_reason = (f"[unknown_subject] lot={cur_lot} · 원장에 원자 0 "
                               f"— 번역 안 됨 또는 없는 랏")
            break

        # --- question 1: which wafer sits at (cur_lot, cur_slot)? --------
        if cur_slot is not None:
            wafer_claims = [c for c in at(cur_lot, "has_wafer")
                            if _payload_slot(c) == cur_slot]
            res = resolve(wafer_claims, _payload_wafer, cfg,
                          subject_label=f"lot={cur_lot} slot={cur_slot}",
                          predicate="has_wafer")
            hops.append(_hop(
                _lot_node(cur_lot, cur_slot),
                _wafer_node(res.answer) if res.answer is not None else None,
                res, "has_wafer", zone))

        # --- question 2: which lot did this one come from? ---------------
        parent_claims = at(cur_lot, "derived_from")
        if not parent_claims:
            registered = bool(at(cur_lot, "register"))
            res = Resolution(
                state="unresolvable", winner=None, answer=None, rank=None, n=None,
                reason=(f"[root] lot={cur_lot} · derived_from 없음"
                        + (" (register 있음)" if registered else " (register 없음)")))
            hops.append(_hop(_lot_node(cur_lot, cur_slot), None, res,
                             "derived_from", zone))
            terminal_reason = (
                f"[root] lot={cur_lot} · derived_from 주장 없음 — 사슬의 뿌리"
                if registered else
                f"[dead_end] lot={cur_lot} · derived_from 없고 register도 없음 — "
                f"원장이 이 랏의 혈통을 모름")
            break

        res = resolve(parent_claims, _payload_lot, cfg,
                      subject_label=f"lot={cur_lot}", predicate="derived_from")
        parent = res.answer
        hops.append(_hop(_lot_node(cur_lot, cur_slot),
                         _lot_node(parent, None) if parent is not None else None,
                         res, "derived_from", zone))
        if parent is None:
            terminal_reason = (f"[broken] hop {len(hops)} · derived_from "
                               f"{len(parent_claims)}건이 부모 랏을 못 준다")
            break

        # --- question 3: where was this position in the parent? ----------
        parent_slot = None
        if cur_slot is not None:
            sm_res = _map_slot(index, cur_lot, parent, cur_slot, cfg)
            parent_slot = sm_res.answer
            hops.append(_hop(_lot_node(cur_lot, cur_slot),
                             _lot_node(parent, parent_slot),
                             sm_res, "slot_map", zone))

        depth += 1
        if parent in visited:
            terminal_reason = (f"[cycle] lot={parent} 재방문 · 사슬이 순환한다 — "
                               f"원장에 모순 원자")
            break
        visited.append(parent)
        cur_lot, cur_slot = parent, parent_slot

        if depth >= max_depth:
            terminal_reason = (f"[depth_cap] {max_depth}홉 도달 · lot={cur_lot} "
                               f"에서 사슬이 계속된다 (끝 아님)")
            break

    if terminal_reason is None:                           # pragma: no cover
        terminal_reason = "[unknown] 워크가 이유 없이 멈췄다"
    if nb.truncated and nb.truncation_reason and "depth_cap" not in terminal_reason:
        terminal_reason += f" · 조회도 잘림: {nb.truncation_reason}"

    # The invariant, asserted rather than trusted. Brief §3-2: 빈 결과 금지.
    assert hops, "trace() produced an empty hop list - the one forbidden answer"

    return {
        "hops": hops,
        "terminal_reason": terminal_reason,
        # The DECLARED zone, same as every `occurred_at` in `hops`. A
        # `generated_at` from a different clock than the hop times is an
        # invitation to subtract nine hours by eye.
        "generated_at": _iso(datetime.now(timezone.utc), zone),
    }


def _map_slot(index, cur_lot, parent, cur_slot, cfg):
    """Carry `cur_slot` across one lineage hop through `slot_map`.

    Both directions are searched because §4.2 does not pin which side `from`
    names (see `_slot_map_pair`). The direction is decided by which lot is the
    SUBJECT of the atom, which is a fact of the atom rather than a guess:

        subject = child, object = parent  ->  from = child slot, to = parent slot
        subject = parent, object = child  ->  from = parent slot, to = child slot

    An atom that fits neither is not read at all, so a wrong slot never reaches
    the screen — the hop comes back `unresolvable` with the pair that did not fit.
    """
    forward = []
    for c in index.get((cur_lot, "slot_map"), []):
        if _payload_lot(c) != parent:
            continue
        a, b = _slot_map_pair(c)
        if a == cur_slot and b is not None:
            forward.append((c, b))
    backward = []
    for c in index.get((parent, "slot_map"), []):
        if _payload_lot(c) != cur_lot:
            continue
        a, b = _slot_map_pair(c)
        if b == cur_slot and a is not None:
            backward.append((c, a))

    pairs = forward + backward
    if not pairs:
        present = len(index.get((cur_lot, "slot_map"), [])) + \
            len(index.get((parent, "slot_map"), []))
        return Resolution(
            state="unresolvable", winner=None, answer=None, rank=None, n=None,
            reason=(f"[no_slot_map] {cur_lot}→{parent} slot={cur_slot} 짝 없음 · "
                    f"두 랏의 slot_map 원자 {present}건 중 해당 없음"))

    answers = {id(c): s for c, s in pairs}
    return resolve([c for c, _ in pairs], lambda c: answers.get(id(c)), cfg,
                   subject_label=f"{cur_lot}→{parent} slot={cur_slot}",
                   predicate="slot_map")
