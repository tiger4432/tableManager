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

#: 🔴 THE WALK'S VOCABULARY IS DECLARED, NOT LISTED HERE (ruling R-2026-08-14-E).
#:
#: This used to be the literal `("derived_from", "slot_map", "has_wafer", "register")` —
#: a SECOND list of the vocabulary, in a module that does not know the vocabulary exists.
#: Two things were wrong with it and only one was visible:
#:
#:   * a predicate could not JOIN the walk without an edit here, so "the walk reads the
#:     lineage words" was upkeep rather than a property;
#:   * and a predicate could not be KEPT OUT of it either — there was nowhere to say so.
#:     `observed` (ruling R-2026-08-14-D) is the word that made that fatal: a wafer carries
#:     tens of thousands of findings, `claims_for_lots` drags back EVERY claim of every lot
#:     it reaches, and a defect translator succeeding would have killed this screen. The
#:     declaration says `traversable: None` and that is now a fact the walk reads.
#:
#: `lineage_predicates()` is the fetch set (traversable words AND annotations);
#: `traversal_predicate()` is the single word the recursion follows. Both come from
#: `ledger.vocabulary`, IMPORTED LAZILY: `LEDGER_GUIDE` §0 promises nothing on the web
#: server's boot path imports `server/ledger`, and this module is imported by the router,
#: so the import lives inside the call exactly as `ledger_structure._vocabulary()` does.
#:
#: `ledger_trace.LINEAGE_PREDICATES` still resolves, through the module `__getattr__`
#: below, because it is what an existing reader reaches for. It is the DERIVED tuple now.
_WALK_CACHE = {}


def _vocabulary():
    """The closed vocabulary. Lazy, and never cached across a reload of it."""
    from ledger import vocabulary
    return vocabulary


def lineage_predicates():
    """Every predicate the walk may FETCH for a lot it reached. Derived, order stable."""
    if "fetch" not in _WALK_CACHE:
        _WALK_CACHE["fetch"] = tuple(_vocabulary().walk_predicates())
    return _WALK_CACHE["fetch"]


def rollup_subject_types(root_type: str) -> tuple:
    """The subject types a read about `root_type` must include (ruling R-2026-08-15-O).

    🔴 ONE SPELLING FOR EVERY READER, and it lives here because this is already the module
    that adapts the vocabulary's declarations for the query layer (`lineage_predicates`
    right above does the same job for the walk's fetch set). `ledger_journey`,
    `ledger_walk_contrast` and `ledger_selection` all import from this module already, so a
    per-file copy would have been three lists of one fact - and three lists is how
    a derived subject type can become visible to one query and invisible to the next.

    Cached with the walk sets, so `reset_walk_cache()` (wired into `/admin/reload-configs`)
    drops it too - the vocabulary can gain a derived type without a restart.
    """
    key = ("rollup", root_type)
    if key not in _WALK_CACHE:
        _WALK_CACHE[key] = tuple(_vocabulary().rollup_subject_types(root_type))
    return _WALK_CACHE[key]


def traversal_predicate():
    """The ONE predicate the recursion follows, checked against what it can execute.

    🔴 A declaration this walk cannot honour is REFUSED BY NAME rather than approximated.
    Two arms of that: a second traversable word would need a different recursive CTE (the
    current one joins on one predicate), and a `direction` other than `subject_to_object`
    would need the join written the other way round. Falling back to the hard-coded
    behaviour in either case is how a declaration becomes decoration — the walk would keep
    following `derived_from` while the declaration said something else, and every test
    would stay green.
    """
    if "traverse" not in _WALK_CACHE:
        vocabulary = _vocabulary()
        traversable = list(vocabulary.traversable_predicates())
        if len(traversable) != 1:
            raise ResolverConfigError(
                f"the vocabulary declares {len(traversable)} traversable predicate(s) "
                f"({', '.join(traversable) or 'none'}) and this walk implements exactly "
                f"one. A second lineage edge needs the recursive CTE to join on a set "
                f"rather than a value, which is a measured change to the one query whose "
                f"plan this system has already argued about - it is not a default this "
                f"function may pick.")
        predicate = traversable[0]
        direction = vocabulary.walk_direction(predicate)
        if direction != "subject_to_object":
            raise ResolverConfigError(
                f"predicate '{predicate}' declares walk direction {direction!r}; this "
                f"walk implements 'subject_to_object' only (subject_keys->>'lot' joined "
                f"to the object's lot). Walking it the other way is a different query, "
                f"not a flag.")
        _WALK_CACHE["traverse"] = predicate
    return _WALK_CACHE["traverse"]


def reset_walk_cache():
    """Tests only - so a swapped vocabulary is actually re-read."""
    _WALK_CACHE.clear()


def __getattr__(name):
    """`LINEAGE_PREDICATES`, resolved on access rather than at import.

    Module-level `__getattr__` (PEP 562) is what lets the name keep working for readers
    and tests while the VALUE comes from the declaration - and it is what keeps the lazy
    import lazy, because a module-level constant would have to import `server/ledger` at
    the web server's boot.
    """
    if name == "LINEAGE_PREDICATES":
        return lineage_predicates()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
    # 🔴 class 1 — DERIVATIONS WHOSE DESTINATION WAS CONFIRMED AGAINST A DECLARED
    # RELATION. Ontology owner's ruling, 2026-08-15, and the FIRST USE of class 1 for
    # anything other than `frame_confirmed`.
    #
    # WHY A DERIVATION LIST AND NOT ONE OF THE THREE TESTS ABOVE. `confirmed_sources`
    # would promote every atom `dt_log` makes, and the whole point is that ONE of its two
    # derivations confirmed its destination and the other could not. `confirmed_payload_flag`
    # would need the translator to stamp a new key, which reaches only atoms written AFTER
    # the change — the 29 already in the ledger would keep the wrong rank. The derivation
    # suffix is already stamped on every atom ever written, so reading class off it is
    # retroactive by construction, and the class stays a READ-TIME declaration rather than
    # a permanent mark (which is what makes it revisable at all).
    #
    # WHAT MAKES THIS ATOM CLASS 1 RATHER THAN A GOOD CLASS 2. Its `to` identity comes from
    # the declared confirmation relation, and MEASURED on a real atom that identity
    # DISAGREES with `container_recorded` — the row's own written-down value, preserved
    # beside it as evidence to argue with. A claim that may override what the source row
    # said is not an observation of equal standing with one; 「확정된 체인 주장」 is exactly
    # the rung design §6 has for it.
    #
    # AND IT ANSWERS A REAL GAP. Its sibling `job_run_to_job` is class 2, so under equal
    # class the tiebreak would be `occurred_at` desc then id — a wafer carrying both would
    # resolve by ordering, arbitrarily, and wrong about half the time. Class 1 makes the
    # confirmed container win BY RANK, deterministically.
    "confirmed_derivations": ["job_run_to_confirmed_container"],
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
        merged["inference_derivations"] = sorted(
            set(merged.get("inference_derivations") or ())
            | set(_declared_inference_derivations()))
        _config_cache = merged
        return merged


def _declared_inference_derivations():
    """Class-3 derivations an OPERATOR declared on `declared`-grammar `emit` rules.

    🔴 WHY THE RESOLVER READS THE TRANSLATOR'S CONFIG. Since the `declared` grammar landed,
    a derivation can be born in a config file written through the admin screen, and its
    class is declared beside it (`"class": "inference"`). If that declaration reached the
    classification TEST but not this function, the test would go green while the resolver
    ranked those atoms as observations - a check certifying the opposite of what runs.

    🔴 AND IT RAISES RATHER THAN DEGRADING. An unreadable declaration means these
    derivations fall back to `claim_class`'s final `return CLASS_OBSERVATION`, which is
    precisely the inversion the whole rule exists to prevent - an assumption outranking a
    measurement, permanently, because a file had a stray comma. Loud beats subtly wrong;
    this is the same posture `load_resolver_config` already takes for its own malformed
    file, one file over.
    """
    try:
        from ledger import config as ledger_config
    except Exception:
        # The translator package is not importable in this process at all (the web server
        # is not required to ship it). Nothing declared it, so nothing is missing.
        return frozenset()
    try:
        return ledger_config.declared_inference_derivations(ledger_config.load())
    except Exception as exc:
        raise ResolverConfigError(
            f"the ledger source declarations could not be read, so operator-declared "
            f"class-3 derivations cannot be honoured ({exc.__class__.__name__}: {exc}). "
            f"Refusing rather than continuing: without them every such atom would rank as "
            f"an OBSERVATION, which is the inversion design §6 exists to prevent - a "
            f"declared assumption would silently outrank a real measurement.")


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


def is_confirmed_derivation(claim, config=None):
    """True when this atom's content was CONFIRMED against a declared relation.

    Symmetric with `is_convention_backed` and read off the same `#<derivation>` suffix —
    one register of derivations, three classes read from it, no twelfth column.
    """
    cfg = config or load_resolver_config()
    basis = claim_basis(claim)
    return basis is not None and basis in tuple(cfg.get("confirmed_derivations") or ())


def claim_class(claim, config=None):
    """§6's four ranks: 0 pin > 1 confirmed chain claim > 2 observation > 3 inference."""
    cfg = config or load_resolver_config()
    if claim.predicate in tuple(cfg["pin_predicates"]):
        return CLASS_PIN
    payload = claim.object_payload or {}
    if (claim.predicate in tuple(cfg["confirmed_predicates"])
            or (claim.source_who or "") in tuple(cfg["confirmed_sources"])
            or payload.get(cfg["confirmed_payload_flag"]) is True
            or is_confirmed_derivation(claim, cfg)):
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


#: 🔴 **THE HOP STATE VOCABULARY.** Four words as of R-2026-08-13-B week 2; three
#: before it, because `contested` was allowed to shelter under `candidate` for
#: slice 1 ON THE CONDITION that `reason` carried the real distinction. That
#: condition ends here — the distinction is now in the `state` field and the
#: prose is free to be prose again.
#:
#: The two middle words are NOT degrees of the same thing, which is why one word
#: could not keep covering both:
#:
#:     contested   the CLASS declared a winner and a LOWER class still disagrees.
#:                 The ranking is not in doubt; a live contradiction survives it.
#:     candidate   the top class is NOT UNANIMOUS — k distinct answers at the same
#:                 authority, and only the tiebreak levels (registration priority,
#:                 recency, event id) separate them. Nothing declared a winner.
#:
#: 🔴 **A hop with both is `candidate`, not `contested`.** `contested` asserts
#: "a winner was DECLARED", and a top class that disagrees with itself declared
#: nothing — the tiebreak did. Reporting `contested` there would overstate the
#: authority behind the answer, so the weaker word wins when both apply, and the
#: dissent is still named in `reason`.
#:
#: ⚠️ Both words mean the same thing to the ENRICH GRAFT's safety rule: neither
#: may ever pre-mark a row confirmed. The split exists so a client can act on
#: them differently in every OTHER respect, not so one of them can become safe.
STATE_RESOLVED = "resolved"
STATE_CONTESTED = "contested"
STATE_CANDIDATE = "candidate"
STATE_UNRESOLVABLE = "unresolvable"

#: Every state a hop may carry. `test_ledger_trace.py` pins this against the hop
#: dicts the walk actually emits, and `test_ledger_trace_contract.py` pins it
#: against `ledger/vocabulary.py::PROJECTION_ONLY_WORDS` — the design's own
#: projection vocabulary, which already listed `contested` before this route
#: emitted it. That module is NOT imported here on purpose (the web server does
#: not import the translator package), so the two spellings are held equal by a
#: test rather than by an import, exactly as `UUID7_MS_SQL` is.
HOP_STATES = (STATE_RESOLVED, STATE_CONTESTED, STATE_CANDIDATE,
              STATE_UNRESOLVABLE)

#: 🔴 **THE KINDS OF `basis`, AND THE ONLY DISTINCTION THE SAFETY RULE READS.**
#:
#:     convention   the atom's content rests on a DECLARED ASSUMPTION that is not
#:                  in the source row ("a split keeps its slot numbers"). Class 3.
#:     measured     the source uttered it; the translator only reshaped it. Class 2.
#:
#: The enrich graft's hard rule — a hop resting on a convention may NEVER
#: pre-mark a row confirmed — branches on `kind == "convention"` and on nothing
#: else. It used to be recoverable only by regexing Korean prose, and that read
#: INVERTED once: a `candidate` reason lists the LOSERS' basis labels inline, so
#: a naive `includes('convention:')` labelled "assumption" the very hop where an
#: assumption had been OVERRULED by a measurement. A safety rule cannot live in a
#: sentence. R-2026-08-13-C.
BASIS_CONVENTION = "convention"
BASIS_MEASURED = "measured"
BASIS_KINDS = (BASIS_CONVENTION, BASIS_MEASURED)


def hop_basis(claim, config=None):
    """What the WINNING claim of a hop rests on, as a structured field, or None.

    🔴 `name` is reported VERBATIM off `claim_basis` and `kind` is decided by
    `is_convention_backed` — i.e. by the SAME `inference_derivations` list that
    decides the claim's CLASS. That identity is the point, and it is what keeps
    this field from becoming the soft landing the standing rule forbids:

        kind == "convention"  <->  is_convention_backed  <->  class 3

    A derivation nobody has classified therefore comes out `measured` here just as
    it did before this field existed, and
    `test_every_declared_derivation_is_explicitly_classified` still fails at the
    moment it is added. `basis.name` is a REPORT of the suffix, never a second
    register of derivations that the classification test does not see.

    ⚠️ `measured` DOES NOT MEAN CLASS 2 — it means「not convention-backed」, which
    since 2026-08-15 covers class 1 AND class 2. `job_run_to_confirmed_container`
    (class 1, confirmed against a declared relation) and `job_run_to_job` (class 2,
    an honest weaker utterance) both report `measured`, so THIS FIELD CANNOT TELL
    THEM APART. That is a deliberate non-change rather than an oversight: widening
    `BASIS_KINDS` is a response-shape change for every consumer that switches on
    `kind`, and it is a decision for the product owner rather than a side effect of
    a classification ruling. A client that needs the distinction reads the hop's
    CLASS, which is where the ranking actually lives.

    None has two causes that are deliberately not told apart: the hop has no
    winner (`unresolvable`), or the winner carries no `#<derivation>` suffix.
    Both mean "no declared basis", and neither is a convention — so a client that
    treats null as "not convention-backed" is correct in both.
    """
    if claim is None:
        return None
    name = claim_basis(claim)
    if name is None:
        return None
    return {"kind": (BASIS_CONVENTION if is_convention_backed(claim, config)
                     else BASIS_MEASURED),
            "name": name}


@dataclass
class Resolution:
    """One hop's answer plus WHY it has the state it has."""
    state: str                       # one of `HOP_STATES`
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
    counts, and the hop reads `contested` — the ranking is never in doubt, but
    the operator is told that something disagreed. When the TOP class is itself
    split the word drops to `candidate`, because then nothing declared a winner
    at all; see `HOP_STATES` for why the weaker word wins when both apply.

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
            state=STATE_UNRESOLVABLE, winner=None, answer=None, rank=None, n=None,
            reason=f"[no_claim] {predicate} 원자 없음 · {subject_label}")

    usable = [c for c in claims if answer_of(c) is not None]
    if not usable:
        return Resolution(
            state=STATE_UNRESOLVABLE, winner=None, answer=None, rank=None, n=None,
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
        return Resolution(state=STATE_RESOLVED, winner=winner, answer=agreed[0],
                          rank=1, n=1, reason=_with_basis(reason, winner, cfg),
                          top_class=top_class, competing=tuple(contenders))

    # The dissent sentence is built for BOTH states, not only for `contested`.
    # Gaining the word must not lose the fact: a hop whose top class is split AND
    # whose lower class disagrees reads `candidate`, and the lower-class dissent
    # is still the thing an operator needs to see.
    #
    # NAME what each loser rests on, because "an assumption disagreed with a
    # measurement" and "two measurements disagreed" are different situations and
    # the operator acts on them differently.
    dissent_phrase = ""
    if dissent:
        losers = []
        for c in outranked:
            a = answer_of(c)
            if a in dissent and a not in [x for x, _ in losers]:
                losers.append((a, _basis_label(c, cfg)))
        shown = " / ".join(f"{a}({lbl})" if lbl else str(a) for a, lbl in losers[:3])
        dissent_phrase = f" · 하위 계급 반대 {len(dissent)}종 ({shown})"

    if len(agreed) > 1:
        # The top class is not unanimous: k answers at one authority, separated
        # only by the tiebreak levels. NOTHING declared this winner, so the word
        # is `candidate` even when a lower class ALSO dissents.
        state = STATE_CANDIDATE
        shown = " / ".join(str(a) for a in agreed[:4])
        if len(agreed) > 4:
            shown += f" / +{len(agreed) - 4}"
        reason = (f"[{STATE_CANDIDATE}] class={top_class} {cls_name} 내 답 "
                  f"{len(agreed)}종 ({shown}){dissent_phrase} · 1순위 {agreed[0]}")
    else:
        # The class DECLARED this winner and a lower class still disagrees. The
        # ranking is not in doubt; the contradiction is alive and is reported.
        state = STATE_CONTESTED
        reason = (f"[{STATE_CONTESTED}] class={top_class} {cls_name} 답 "
                  f"{agreed[0]}{dissent_phrase} · 1순위 {agreed[0]}")
    return Resolution(state=state, winner=winner, answer=agreed[0],
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

    def claims_for_lots(self, lots, predicates=None):
        raise NotImplementedError

    def neighbourhood(self, lot, max_depth=DEFAULT_MAX_DEPTH,
                      predicates=None):
        # `None` means "whatever the vocabulary declares", resolved HERE rather than in a
        # default argument: a default is evaluated at import time and would drag
        # `server/ledger` onto the web server's boot path (`LEDGER_GUIDE` §0). A caller
        # that passes a list still gets exactly that list - the scoped-query path depends
        # on it.
        predicates = lineage_predicates() if predicates is None else predicates
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
        traverse = traversal_predicate()
        by_lot = {}
        for c in self._claims:
            if c.predicate == traverse and c.subject_lot:
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

    def claims_for_lots(self, lots, predicates=None):
        wanted = set(lots)
        preds = set(lineage_predicates() if predicates is None else predicates)
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
         AND e.predicate = %(traverse)s
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
         AND e.predicate = %(traverse)s
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
        rows = self._execute(sql, {"start_lot": lot, "max_depth": int(max_depth),
                                   "traverse": traversal_predicate()})
        lots = [r[0] for r in rows if r[0] is not None]
        truncated = any(int(r[1] or 0) >= int(max_depth) for r in rows)
        return lots, truncated, (f"[depth_cap] {max_depth}홉에서 조회 중단"
                                 if truncated else None)

    def claims_for_lots(self, lots, predicates=None):
        if not lots:
            return []
        sql = (f"SELECT id, subject_type, subject_keys, predicate, object_kind, "
               f"object_payload, occurred_at, source_who, source_translator_ver, "
               f"source_raw_ref, supersedes FROM {self.relation} "
               f"WHERE subject_type = 'Lot' "
               f"AND subject_keys->>'lot' = ANY(%(lots)s) "
               f"AND predicate = ANY(%(predicates)s)")
        predicates = lineage_predicates() if predicates is None else predicates
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
                      predicates=None):
        predicates = lineage_predicates() if predicates is None else predicates
        sql = _TRACE_CTE.format(relation=self.relation)
        rows = self._execute(sql, {"start_lot": lot, "max_depth": int(max_depth),
                                   "predicates": list(predicates),
                                   "traverse": traversal_predicate()})
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


def _hop(frm, to, resolution, predicate, zone, config=None):
    """One hop in the pinned response shape.

    🔴 **THE SHAPE IS PINNED BY KEY SET, NOT BY "at least these keys".**
    `test_ledger_trace.py::test_response_shape_is_the_pinned_one` asserts the key
    set EXACTLY, so a field cannot arrive here unnoticed. Two have arrived
    deliberately, both additive, both for the same reason:

      `predicate`  (L2) — without it a client cannot tell a `has_wafer` hop from
                   a `derived_from` hop except by parsing prose.
      `basis`      (R-2026-08-13-C) — `{kind, name}` or None. Without it a client
                   cannot tell an assumption from an utterance except by parsing
                   prose, and that parse had already INVERTED once.

    The standing principle behind both, and the reason a third field would be
    argued the same way: **`reason` is prose for a human; any fact the screen
    must BRANCH on goes out as a structured field.**
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
        "basis": hop_basis(winner, config),
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
                state=STATE_UNRESOLVABLE, winner=None, answer=None, rank=None, n=None,
                reason=f"[unknown_subject] lot={cur_lot} · 원장에 원자 0")
            hops.append(_hop(_lot_node(cur_lot, cur_slot), None, res,
                             "register", zone, cfg))
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
                res, "has_wafer", zone, cfg))

        # --- question 2: which lot did this one come from? ---------------
        parent_claims = at(cur_lot, "derived_from")
        if not parent_claims:
            registered = bool(at(cur_lot, "register"))
            res = Resolution(
                state=STATE_UNRESOLVABLE, winner=None, answer=None, rank=None, n=None,
                reason=(f"[root] lot={cur_lot} · derived_from 없음"
                        + (" (register 있음)" if registered else " (register 없음)")))
            hops.append(_hop(_lot_node(cur_lot, cur_slot), None, res,
                             "derived_from", zone, cfg))
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
                         res, "derived_from", zone, cfg))
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
                             sm_res, "slot_map", zone, cfg))

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
            state=STATE_UNRESOLVABLE, winner=None, answer=None, rank=None, n=None,
            reason=(f"[no_slot_map] {cur_lot}→{parent} slot={cur_slot} 짝 없음 · "
                    f"두 랏의 slot_map 원자 {present}건 중 해당 없음"))

    answers = {id(c): s for c, s in pairs}
    return resolve([c for c, _ in pairs], lambda c: answers.get(id(c)), cfg,
                   subject_label=f"{cur_lot}→{parent} slot={cur_slot}",
                   predicate="slot_map")


# --------------------------------------------------------------------------
# COVERAGE — "is there a ledger on this box, and what does it cover?"
# --------------------------------------------------------------------------
#
# 🔴 THE PROBLEM THIS SOLVES IS THAT FOUR DIFFERENT SITUATIONS RENDER AS
# "nothing", AND AN OPERATOR CANNOT TELL A DEPLOYMENT PROBLEM FROM A DATA
# BOUNDARY. Measured 2026-08-13: the product owner opened the trace screen and
# got nothing, because `assy_manager` had no `ledger_events` table at all. The
# screen was honest and the box was empty, and nothing on screen said which.
#
#     ledger_events absent      -> deployment: the migration has not been run
#     present, zero atoms       -> the backfill has not been run
#     unknown lot               -> a data boundary
#     known lot, no lineage     -> registered, but nothing claimed about parentage
#
# The first two are properties of the BOX and are answered here, once, in a
# machine-readable `state`. The last two are properties of one LOT and are
# already answered by `trace` (`[unknown_subject]` vs `[root] … (register 있음)`).
# Splitting them that way is deliberate: a screen asks `coverage` once on load
# and `trace` once per lot, and neither has to guess what the other's silence
# meant.
#
# WHY `state` IS A FIELD AND NOT PROSE. Ruling R-2026-08-13-C: `reason` is prose
# for humans, and any fact the screen must BRANCH on goes out as a structured
# field. A client that branched on Korean text would break the first time the
# wording improved — and L3 has already shown what a prose parse costs.

#: The absent-relation refusal, as a machine-readable token rather than as
#: Korean prose. Named here so the route, the tests and any future consumer
#: share one spelling. A client branches on this; the message beside it is for
#: the operator's eyes only.
REASON_RELATION_ABSENT = "ledger_relation_absent"

#: The three answers `coverage` can give. `absent` and `empty` are operational
#: facts about the deployment; `ready` means the walk has something to walk.
COVERAGE_STATES = ("absent", "empty", "ready")

#: How many traceable lots the coverage answer carries. A handful — this is a
#: "try one of these" affordance for the screen, not a catalogue endpoint. The
#: catalogue is `register`, and it is counted rather than listed.
DEFAULT_SAMPLE_SIZE = 3


def _fetch(connection, sql, params=None):
    """Run `sql` on either a DBAPI connection or a SQLAlchemy Connection/Session.

    Same two-shaped handling `SqlClaimLookup._execute` does, and for the same
    reason: the route hands over a `Session`'s connection while the tests and
    any operator script hand over psycopg2.
    """
    conn = connection
    # `params` stays None rather than becoming `{}` when there is nothing to
    # bind: psycopg2 only runs its `%` interpolation pass when a parameter
    # argument is given, and an empty dict would still turn a literal `%` in a
    # future query into an IndexError that has nothing to do with the query.
    if hasattr(conn, "cursor"):                          # psycopg2 connection
        with conn.cursor() as cur:
            cur.execute(sql, params) if params else cur.execute(sql)
            return cur.fetchall()
    exec_driver = getattr(conn, "exec_driver_sql", None)
    if exec_driver is None and hasattr(conn, "connection"):    # Session
        exec_driver = conn.connection().exec_driver_sql        # pragma: no cover
    return list(exec_driver(sql, params) if params else exec_driver(sql))


def relation_exists(connection, relation):
    """Catalogue gate. `to_regclass` returns NULL for an absent relation rather
    than raising, so this can be asked BEFORE any query that would poison the
    transaction — this project's standing rule for DDL-adjacent work, applied to
    reads because the failure mode is identical: one `UndefinedTable` and every
    later statement on the connection fails for an unrelated-looking reason.

    Resolution is through `search_path`, which is what makes the scratch-schema
    test fixture ask about the scratch table rather than about `public`'s.
    """
    if not _IDENTIFIER.match(relation or ""):
        raise ValueError(f"relation must be a bare SQL identifier: {relation!r}")
    rows = _fetch(connection, "SELECT to_regclass(%(rel)s) IS NOT NULL",
                  {"rel": relation})
    return bool(rows and rows[0][0])


def coverage(connection, relation="ledger_events",
             cursor_relation="ledger_translator_cursor", config=None,
             sample_size=DEFAULT_SAMPLE_SIZE):
    """What this box's ledger covers, in the pinned coverage shape.

    Never raises for an absent or empty ledger — those ARE the answers. The only
    refusal is `ResolverConfigError` from an unusable display zone, which is the
    same door `trace` refuses at and for the same reason: a screen that renders a
    fab record in the wrong zone looks completely normal.

    [SCALE — every query here is bounded by something other than atom count]
    * existence      `to_regclass`, a catalogue lookup.
    * any atom?      `EXISTS (SELECT 1 …)` stops at the first row; with no
                     partitions it stops without touching a heap at all.
    * `lots`         `count(*) WHERE predicate='register' AND subject_type='Lot'`
                     is served by the PARTIAL index `idx_ledger_register`, which
                     is O(entities) while the table is O(atoms) — that index's
                     own admission note says so.
    * `occurred_at`  `min`/`max` ride `uq_ledger_atom`, whose LEADING column is
                     `occurred_at` (`schema.DEDUPE_COLUMNS`), so each partition
                     answers from one end of an index and PostgreSQL merges them.
                     🔴 This is why no new index was added for this endpoint: the
                     one that idempotency already pays for happens to be sorted
                     on exactly the column the header needs.
    * `sample`       an ordered index scan on `idx_ledger_subject_lot` with a
                     LIMIT, so it stops after a handful rather than sorting the
                     ledger, plus one indexed seek per sampled lot.
    * `atoms`        `pg_class.reltuples` summed over the partitions. THE CATALOGUE,
                     never `count(*)`: `store.atom_count()` counts every row of
                     every partition and is exactly the cost this endpoint may not
                     pay. It is an ESTIMATE and the response says so in a field
                     (`exact: false`), because a screen that prints a maintained
                     statistic as if it were a count is how "the ledger lost rows"
                     gets reported after an autovacuum has simply not run yet.
    * `partitions`   `pg_inherits` + `pg_class`, the same catalogue query
                     `schema.partitions` runs. Free, and exact.
    * `cursors`      the whole cursor table. O(sources) — one row per translator,
                     not per atom — so it is a handful of rows forever.
    * `last_atom`    `ORDER BY occurred_at DESC LIMIT 1`, which rides
                     `uq_ledger_atom`'s leading column exactly as min/max above do:
                     one index descent per partition and a MergeAppend, O(partitions)
                     rather than O(atoms). `recorded_at` costs NOTHING extra — it is
                     decoded from the `id` that row already carries.
    There is deliberately NO `SELECT DISTINCT source_who` — see `sources` below.
    There is deliberately no verification-run log: none exists, and ruling
    R-2026-08-13-F declined to build one for a status strip. The screen says so.

    🔴 ONE REQUEST, NOT TWO (ruling R-2026-08-13-F). The status strip reuses THIS
    body rather than fetching its own, so everything added above had to be O(1) in
    atoms or it would have made the page-load call heavier. `lots` remains the only
    field that grows, under the ruling that already governs it.

    MEASURED 2026-08-13, throwaway probe DB, 280,000 atoms / 100,000 lots across
    12 monthly partitions, VACUUM ANALYZEd (a probe without statistics reports a
    plan nobody will ever run):

        EXISTS               0.12 ms   3 buffers, 11 of 12 partitions unvisited
        min/max occurred_at  0.13 ms   8 buffers, Index Only Scan + Limit 1
        sample               1.07 ms  38 buffers, MergeAppend of index scans
        count(register)     24.06 ms 636 buffers, Index Only Scan, 0 heap fetches
        coverage() total    31 ms

    🔴 `lots` IS THE ONLY ONE THAT GROWS, and it grows with ENTITIES, not atoms —
    it walks the whole partial index. At this source's density (909 atoms / 25
    lots) a ten-million-atom ledger is ~275,000 lots, so ~66 ms.

    **It is deliberately NOT cached, and that is the interesting decision.** This
    project caches counts for 5 s elsewhere (`main.TABLE_COUNT_CACHE`) and the
    same trick would work here. But this endpoint exists to tell an operator
    whether the migration and backfill they JUST RAN took effect — a cache would
    make it answer "absent" or "empty" for five seconds at the exact moment its
    answer matters most, which is a worse defect than 66 ms. If a future consumer
    polls it, cache it THERE.
    """
    cfg = config or load_resolver_config()
    zone = resolve_display_zone(cfg)

    answer = {"state": "absent", "lots": 0, "sources": [],
              "occurred_at": {"from": None, "to": None}, "sample": [],
              "atoms": dict(ATOMS_UNKNOWN), "partitions": {"count": 0, "list": []},
              "cursors": [], "last_atom": {"occurred_at": None, "recorded_at": None}}

    # `sources` comes from the CURSOR table, not from `DISTINCT source_who`.
    #
    # Two reasons, and the second one is the better one. (1) There is no index on
    # `source_who` and there is no consumer that would justify adding one, so a
    # DISTINCT over it is a sequential scan of the whole ledger — at ten million
    # atoms that is a multi-second page load for a header field. (2) The cursor
    # table is the ledger's own registry of WHO HAS WRITTEN HERE, and it still
    # answers when the ledger is empty: a translator that ran and refused every
    # molecule leaves a cursor row and no atoms, and "a translator has been here
    # and produced nothing" is precisely the distinction `state: "empty"` exists
    # to draw. `DISTINCT source_who` would say `[]` for both "never ran" and
    # "ran, refused everything".
    #
    # The two spellings agree by construction for every translator that exists:
    # `backfill.run(source=…)` keys the cursor row, and the same string is the
    # translator's `who`, which becomes `source_who` on every atom
    # (`lot_event_translator.SOURCE`). A future translator whose `who` differs
    # from its cursor key would make this field name a source rather than an
    # author — worth a test at that point, not a scan today.
    if relation_exists(connection, cursor_relation):
        answer["cursors"] = _cursor_rows(connection, cursor_relation, zone)
        answer["sources"] = [c["source"] for c in answer["cursors"] if c["source"]]

    if not relation_exists(connection, relation):
        return answer                                   # state stays "absent"

    # Catalogue facts, and they are answered for an EMPTY ledger too: "the table is
    # deployed and partitioned and holds nothing" is a different report from "the table
    # is deployed and I cannot tell you anything about it", and the second one is what an
    # early return here would produce.
    answer["partitions"] = _partition_report(connection, relation)
    answer["atoms"] = _atom_estimate(connection, relation)

    populated = _fetch(connection, f"SELECT EXISTS (SELECT 1 FROM {relation})")
    if not (populated and populated[0][0]):
        answer["state"] = "empty"
        return answer

    answer["state"] = "ready"
    answer["last_atom"] = _last_atom(connection, relation, zone)
    rows = _fetch(connection, f"SELECT count(*) FROM {relation} "
                              f"WHERE predicate = 'register' AND subject_type = 'Lot'")
    answer["lots"] = int(rows[0][0]) if rows else 0

    rows = _fetch(connection,
                  f"SELECT min(occurred_at), max(occurred_at) FROM {relation}")
    if rows:
        answer["occurred_at"] = {"from": _iso(rows[0][0], zone),
                                 "to": _iso(rows[0][1], zone)}

    answer["sample"] = _coverage_sample(connection, relation, sample_size)
    return answer


#: The atom count before the catalogue has been asked, and the shape every answer
#: keeps. 🔴 `exact` is FALSE in every spelling of this field — there is no branch
#: of this endpoint that counts rows — so a client that reads it can render "약"
#: without deciding when to.
ATOMS_UNKNOWN = {"estimate": 0, "exact": False, "method": "pg_class.reltuples",
                 "unanalyzed_partitions": 0}


def _atom_estimate(connection, relation):
    """How many atoms, APPROXIMATELY, from the catalogue alone.

    `reltuples` is maintained by VACUUM and ANALYZE rather than by the statistics
    collector, which is why it is trustworthy in exactly the situation
    `pg_stat_user_tables` is not: this project spent a round on five phantom
    "bloated" tables because `n_live_tup` had been reset while the tables were
    fine (server-pm lessons, 2026-08-06). It is still an estimate, and the two
    ways it lies are both reported rather than smoothed over:

      * a partition that has never been analysed carries `-1` (PostgreSQL 14+)
        or `0`. Counting either as "no atoms" would let a freshly restored
        database report an empty ledger that is full, so those partitions are
        COUNTED and named in `unanalyzed_partitions`, and the estimate says how
        many of its inputs it could not see.
      * between a bulk write and the next autovacuum the number is simply old.
        `exact: false` is the whole of the defence, and it is the client's job to
        render it as an approximation.

    Summed over the PARTITIONS, never read off the parent: a partitioned parent
    holds no rows of its own, so its own `reltuples` is 0 and a reader that took
    it would report an empty ledger with total confidence.
    """
    rows = _fetch(connection, """
        SELECT coalesce(sum(GREATEST(c.reltuples, 0)), 0)::bigint,
               count(*) FILTER (WHERE c.reltuples < 0 OR c.relpages = 0)
        FROM pg_class parent
        JOIN pg_inherits inh ON inh.inhparent = parent.oid
        JOIN pg_class c ON c.oid = inh.inhrelid
        WHERE parent.oid = to_regclass(%(rel)s)
    """, {"rel": relation})
    if not rows:
        return dict(ATOMS_UNKNOWN)                           # pragma: no cover
    return dict(ATOMS_UNKNOWN, estimate=int(rows[0][0] or 0),
                unanalyzed_partitions=int(rows[0][1] or 0))


def _partition_report(connection, relation):
    """The partitions and their bounds — the same catalogue query `schema.partitions`
    runs, spelled here rather than imported for the reason the relation names at the
    top of `ledger_trace_router` are: the web server must not import the translator
    package to answer a read (`server/ledger/__init__.py` states that coupling is
    empty, and it is worth keeping empty).

    The BOUND is carried verbatim, as PostgreSQL renders it. Parsing
    `FOR VALUES FROM (…) TO (…)` into a pair of instants here would be a second
    spelling of the partition grammar, and the screen needs to show the operator what
    the database says, not this module's re-reading of it.
    """
    rows = _fetch(connection, """
        SELECT c.relname, pg_get_expr(c.relpartbound, c.oid)
        FROM pg_class parent
        JOIN pg_inherits inh ON inh.inhparent = parent.oid
        JOIN pg_class c ON c.oid = inh.inhrelid
        WHERE parent.oid = to_regclass(%(rel)s)
        ORDER BY c.relname
    """, {"rel": relation})
    return {"count": len(rows),
            "list": [{"name": name, "bound": bound} for name, bound in rows]}


#: Every column the cursor report would like, in the order the response carries them.
#: Which of them EXIST is asked of the catalogue per request, because a web server may
#: legitimately be running against a database whose migration has not been applied yet —
#: the ordering hazard `add_frame_confirmation.py` documents, and the failure it produces
#: is a 500 on a status endpoint, i.e. the screen reporting itself broken.
CURSOR_FIELDS = ("source", "translator_ver", "cursor_value", "molecules_done",
                 "atoms_written", "atoms_deduped", "molecules_refused",
                 "incomplete_molecules", "refusal_reasons", "source_head",
                 "head_probed_at", "started_at", "updated_at")

#: Cursor columns that are instants and are rendered in the declared display zone,
#: the same rule every other time in this response follows.
CURSOR_TIME_FIELDS = frozenset({"head_probed_at", "started_at", "updated_at"})


def _cursor_rows(connection, cursor_relation, zone):
    """The translator cursor table, whole. O(sources), and that is the point.

    🔴 `refusal_reasons` IS THE ONLY READ OF NAMED REFUSALS THAT EXISTS. The gate's
    counters are process-local to the backfill, the web server never imports that
    package, and the heartbeat note it writes is not served — so before ruling
    R-2026-08-13-F no read of this database could produce a reason breakdown at all.
    This is that read.

    `refusals_unaccounted` is computed here rather than left to the client, and it is
    the anti-false-alarm field. A row written before the column existed carries NULL
    with a non-zero `molecules_refused` — both development databases had exactly that,
    `molecules_refused = 1` and no breakdown — and a screen that rendered "1 refused"
    beside an empty list would be reporting a bookkeeping fault that is not there. So
    the response states how much of the aggregate the breakdown accounts for, and the
    remainder is a fact about deployment history rather than a discrepancy.
    """
    present = _existing_columns(connection, cursor_relation, CURSOR_FIELDS)
    if "source" not in present:
        return []                                            # pragma: no cover
    selected = [f for f in CURSOR_FIELDS if f in present]
    rows = _fetch(connection,
                  f"SELECT {', '.join(selected)} FROM {cursor_relation} ORDER BY source")
    out = []
    for row in rows:
        entry = dict(zip(selected, row))
        for field in CURSOR_TIME_FIELDS & set(entry):
            entry[field] = _iso(entry[field], zone)
        reasons = entry.get("refusal_reasons")
        if "refusal_reasons" in entry:
            # Only when the DATABASE has the column. Setting the key regardless would
            # make "this server is running ahead of its migration" and "this row
            # predates the breakdown" render identically, and only the first of those
            # is fixed by running something.
            entry["refusal_reasons"] = _rendered_reasons(reasons, zone)
        entry["refusals_unaccounted"] = _unaccounted(entry, reasons)
        out.append(entry)
    return out


def _rendered_reasons(reasons, zone):
    """`{reason: {count, last_at}}` with `last_at` moved into the display zone.

    The column stores UTC (`store.LedgerStore._NOW_ISO`) so that two writers can never
    disagree about what a stored string means; the rendering happens here, once, exactly
    as `occurred_at` is rendered. NULL survives as NULL — see `_cursor_rows`.
    """
    if not isinstance(reasons, dict):
        return reasons
    out = {}
    for name, entry in reasons.items():
        if not isinstance(entry, dict):                      # pragma: no cover
            out[name] = entry
            continue
        last_at = entry.get("last_at")
        if isinstance(last_at, str):
            try:
                last_at = _iso(datetime.fromisoformat(last_at), zone)
            except ValueError:                               # pragma: no cover
                pass
        out[name] = {"count": entry.get("count"), "last_at": last_at}
    return out


def _unaccounted(entry, reasons):
    """`molecules_refused` minus what the breakdown explains. 0 on a healthy row.

    🔴 THE SIGN CARRIES MEANING, so a client branches on it rather than on the number:

        0        the breakdown accounts for the aggregate. The ordinary answer.
        > 0      refusals counted before this column existed (or before a
                 `--reverse`), whose names are gone with the process that held them.
                 Deployment history, NOT a fault.
        < 0      the breakdown exceeds the aggregate, which is a real bookkeeping
                 fault: a refusal path that counts in the gate without refusing the
                 molecule. **No such path is currently known.**

                 One existed and was MEASURED on 2026-08-13 — `lot_event_translator`
                 swallowed `_slot_map`'s refusal with `or []`, so the gate counted a
                 refusal, the molecule landed anyway, and the operator's log said
                 "produced nothing" about a row that produced three atoms. Closed by
                 R-2026-08-13-H: the refusal now travels as `gate.MoleculeRefused`,
                 which no merge expression can swallow, and both arms are guarded in
                 `test_ledger_l1_pg.py`.

                 🔴 Keep this branch anyway. It is the detector, and the reason it
                 reads NEGATIVE is that the swallow direction is the dangerous one —
                 a refusal counted while its atoms land is worse than a refusal
                 uncounted. If this number ever goes negative again, a new path of
                 the same shape has opened.
    """
    if "molecules_refused" not in entry:
        return None                                          # pragma: no cover
    total = int(entry.get("molecules_refused") or 0)
    if not isinstance(reasons, dict):
        return total                                # NULL: nothing is accounted for
    explained = sum(int((e or {}).get("count") or 0) for e in reasons.values()
                    if isinstance(e, dict))
    return total - explained


def _existing_columns(connection, relation, wanted):
    """Which of `wanted` the relation actually has, per the catalogue.

    Resolved through `to_regclass` rather than by matching `information_schema` on a
    bare table name: this box carries a second copy of these tables in a scratch schema
    and a name match would answer about whichever one it met first.
    """
    rows = _fetch(connection, """
        SELECT attname FROM pg_attribute
        WHERE attrelid = to_regclass(%(rel)s) AND attnum > 0 AND NOT attisdropped
    """, {"rel": relation})
    return {r[0] for r in rows} & set(wanted)


#: The 48-bit millisecond stamp RFC 9562 puts in the first 12 hex digits of a UUIDv7,
#: decoded in SQL. 🔴 THERE IS NO `recorded_at` COLUMN AND THERE MUST NOT BE ONE
#: (ruling R-2026-08-13-F: a second home for one fact) — the write time lives inside
#: `id`, which is what `ledger/uuid7.py` exists to guarantee.
#:
#: Decoded here rather than by importing `ledger.uuid7.timestamp_ms` because the web
#: server does not import the translator package (`server/ledger/__init__.py`'s stated
#: safety property). That leaves two spellings of one decode, so the two are pinned
#: against each other by a test rather than trusted to stay equal.
#:
#: The version nibble is checked first: a non-v7 id carries no timestamp, and decoding
#: one anyway would mint a confident, wrong instant out of random bits. NULL is the
#: honest answer, and the fixtures in `test_ledger_trace_pg.py` are uuid5, so this
#: branch is exercised by the existing suite rather than only by a written-for-it test.
UUID7_MS_SQL = """
    CASE WHEN substr(replace({column}::text, '-', ''), 13, 1) = '7'
         THEN to_timestamp(
                (('x' || substr(replace({column}::text, '-', ''), 1, 12))
                 ::bit(48)::bigint) / 1000.0)
    END
"""


def _last_atom(connection, relation, zone):
    """The newest atom's event time and the time it was RECORDED.

    Two different questions that look like one: `occurred_at` is when the world did
    something, and the id's stamp is when this box heard about it. A ledger whose
    newest event time is yesterday is either quiet or stuck, and the gap between these
    two numbers is what tells them apart — the distinction `observability.lag_report`
    exists for, made visible without asking the source table anything.
    """
    rows = _fetch(connection, f"""
        SELECT occurred_at, {UUID7_MS_SQL.format(column="id")}
        FROM {relation} ORDER BY occurred_at DESC LIMIT 1
    """)
    if not rows:
        return {"occurred_at": None, "recorded_at": None}    # pragma: no cover
    return {"occurred_at": _iso(rows[0][0], zone),
            "recorded_at": _iso(rows[0][1], zone)}


#: How many `derived_from` atoms the sample ranks over. See `_coverage_sample`
#: for why this is a WINDOW and not "all of them".
SAMPLE_CANDIDATE_WINDOW = 300


def _coverage_sample(connection, relation, sample_size):
    """A handful of lots the trace screen will actually have something to say about.

    THE RULE, in two parts:

    1. **Eligible** = the lot is the SUBJECT of a `derived_from` atom, i.e. the
       ledger claims where it came from, so the walk produces a real lineage hop
       rather than an immediate `[root]`. A lot with only a `register` is
       registered, not traceable, and offering it would demonstrate the very
       emptiness this endpoint exists to explain.
    2. **Ordered** by how many `derived_from` atoms name it, most first, ties
       broken by lot name so the answer is stable across calls (an operator's
       "try this" link must not shuffle on refresh).

    Rule 1 is also what keeps hand-typed junk out without the translator judging
    its source. `assy_manager`'s ledger legitimately registers a lot called
    `adsfas` — somebody typed it into `lot_event` — and the ledger MUST keep
    counting it, because the count is a fact about the source. But nothing is
    derived from `adsfas`, so it is not eligible here. The junk is excluded by
    a property of the data, not by a blocklist that would need maintaining.

    Rule 2 surfaces contended lineage first, which is the most informative thing
    the screen can open on: on `assy_manager` it puts `CL-2601-005-A5` (three
    `derived_from` atoms, two of which disagree) ahead of lots with one.

    [WHY A WINDOW AND NOT `GROUP BY` OVER THE WHOLE LEDGER]
    Measured 2026-08-13 on a throwaway probe, 280,828 atoms / 80,828
    `derived_from`, VACUUM ANALYZEd:

        index-ordered LIMIT, no ranking      2.3 ms     36 buffers
        GROUP BY over ALL derived_from      98.4 ms  7,796 buffers
        this: ranked over a 300-row window   ~2 ms     ~40 buffers

    The middle one is O(lineage events) — ~1.2 s at ten million atoms, on an
    endpoint a screen calls when it loads. So the ranking runs over a BOUNDED
    window of the index-ordered scan and the aggregation happens in Python. The
    ranking is therefore EXACT for any ledger whose lineage fits in the window
    (every ledger this box has: `assy_manager` holds 20 `derived_from` atoms)
    and is an honest "best of the first {SAMPLE_CANDIDATE_WINDOW}" beyond it.
    A sample is a "try one of these" affordance; paying a second of page load to
    rank it perfectly would be the wrong trade.

    The slot is carried because the screen's interesting questions are
    slot-shaped (`has_wafer` and `slot_map` hops only exist when a slot is
    given), so a sample without one would demo a third of the feature. It is
    normalised through `_slot_text`, the same reader the walk uses, so what the
    client sends back matches what the walk compares against — `3` and `03` are
    the same slot and `3 != "03"` is exactly how a chain silently reads broken.
    """
    if sample_size <= 0:
        return []
    # ORDER BY on the index's leading expression makes this a MergeAppend of
    # per-partition index scans that stops at the window, rather than a sort of
    # the ledger. The ORDER BY is also what makes the window DETERMINISTIC —
    # without it the rows come back in whatever order the partitions are read.
    counts = {}
    for row in _fetch(connection, f"""
            SELECT subject_keys->>'lot' FROM {relation}
            WHERE predicate = 'derived_from'
            ORDER BY subject_keys->>'lot' LIMIT %(w)s""",
            {"w": int(SAMPLE_CANDIDATE_WINDOW)}):
        if row[0]:
            counts[row[0]] = counts.get(row[0], 0) + 1
    lots = [lot for lot, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ][:int(sample_size)]

    sample = []
    for lot in lots:
        rows = _fetch(connection, f"""
            SELECT object_payload->'qualifiers'->>'slot'
            FROM {relation}
            WHERE subject_keys->>'lot' = %(lot)s AND predicate = 'has_wafer'
              AND object_payload->'qualifiers'->>'slot' IS NOT NULL
            ORDER BY 1 LIMIT 1""", {"lot": lot})
        slot = _slot_text(rows[0][0]) if rows else None
        if slot is not None:
            # Only a (lot, slot) the walk can answer BOTH questions for is
            # offered. Fewer honest samples beat a padded list.
            sample.append({"lot": lot, "slot": slot})
    return sample
