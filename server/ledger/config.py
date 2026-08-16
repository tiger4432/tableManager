"""`ledger_config.json` - the translator declarations, loaded and VALIDATED.

Every source the ledger reads gets one declaration here (design §1: "번역기 config -
소스마다 한 장"). What is declared, and why each item is a declaration rather than code:

  * `occurred_at_column` + `occurred_at_timezone` - risk control #2 of §10 and risk #2 of
    the brief. **A source with no declared time column is refused, not defaulted.** The
    failure this prevents is silent: substituting arrival time makes every atom look
    plausible and re-ordering a reload changes history.
  * `subject_types` - the EXTENSION of this source's translator: the entity types its
    atoms are allowed to be about. 🔴 It is a plural allow-list and it BITES - `gate`
    refuses an atom whose `subject_type` is outside it by name
    (`undeclared_subject_type`). Ruling R-2026-08-13-D is why both halves of that
    sentence are here: the field used to be singular `subject_type`, it was assigned once
    in the translator and read NOWHERE (every call site passes a literal), so
    `validate()` was checking a value that reached no atom - a declaration teaching the
    reader a contract nothing enforced. The literals stay in code, because the code owns
    the FACT of each atom; this declaration owns the allowed RANGE of those facts, and a
    translator that quietly starts minting a new type is now a counted refusal instead of
    a discovery. **The standing rule it promoted: a declaration field has an enforcement
    point, or it does not exist.**
  * `vocabulary` - which source `event_type`s are understood, and what each one produces.
    An `event_type` absent from this map is refused and counted; it is NOT skipped.
  * `slot_pairing` - 🔴 THE JUDGEMENT CALL OF THIS SLICE, and it is config precisely so
    that it is a judgement somebody made rather than one the translator made:

      - `shared_wafer` - emit `slot_map` only where the SAME wafer id is uttered on both
        rows of the molecule. Zero inference. On `lot_event` this yields atoms for
        merges (the source lot's row is a pre-move snapshot, so the moved wafers appear
        on both sides) and NOTHING for splits (the child's wafers have already left the
        parent's row, so the parent never says where they sat).
      - `slot_preserving` - the operator declares "this source's splits keep slot
        numbers", so each (slot, wafer) on the child row yields `from == to`. That
        convention is the product owner's own statement, not a pattern this translator
        found in the data; declaring it here is what keeps atomicity check ③ honest,
        because the declaration is hashed into `source_translator_ver` and every atom
        therefore carries which convention produced it. If the convention is ever found
        false, `source_raw_ref` re-utters the source rows and the atoms are re-derived.
      - `none` - this event type produces no slot map.

  * `molecules_per_transaction` - how many WHOLE source events share a transaction. Never
    a fraction of one (see `backfill.py`).

🔴 `kind` - WHICH GRAMMAR A SOURCE SPEAKS (ruling R-2026-08-14-D)
------------------------------------------------------------------
`lot_event` is a LINEAGE source: two rows make one event, and its columns are lots, slots
and parent/child. `void_obs` is an OBSERVATION source: one row IS one utterance, its
columns are a finding's position and extent, and its world time is not even on the row -
it belongs to the inspection run that produced it. Validating the second against the
first's required column list would have refused it for not having a `parent_lot`.

So `kind` names the grammar and the validation dispatches on it. It DEFAULTS to `lineage`,
which is what keeps every declaration written before this ruling valid unchanged - and the
default is a fact about history, not a preference: a source that does not say is the one
shape this file already knew.

An observation source additionally declares its RUN - the inspection execution that
produced the finding:

    "run": {"relation": "inspection_run", "key_column": "run_uid",
            "method_column": "method"}

and its `occurred_at_column` is read from THAT relation, not from the observation row.
That is not a convenience: a finding has no time of its own, it has the time of the look
that found it, and inventing one from `created_at` would be arrival time wearing a
world-time hat - risk 1 of design §10, one table over.

🔴 `watermark` - WHERE AN OBSERVATION SOURCE'S CURSOR LIVES
------------------------------------------------------------
A lineage source's cursor is its world time. An observation source's cannot be: every row
of a bulk load shares one `updated_at` (measured on this box: 91,756 `void_obs` rows across
92 distinct values), so a time cursor would put a whole load in one indivisible group. The
declared watermark is therefore a KEYSET - `(updated_at, row_id)` - which is unique,
monotone under both insert and edit, and index-backed (`idx_void_obs_updated`). Declaring
the columns rather than assuming them is what lets a source whose editor stamps a
different column say so.

🔴 `transfer` - THE THIRD GRAMMAR, AND WHY IT IS A GRAMMAR AND NOT A FLAG (`dt_log`)
-------------------------------------------------------------------------------------
`dt_log`'s row is ONE DIE moved into one tape cell, and the declared atom unit is the
JOB-RUN. So its rows must be GROUPED - which neither grammar above does: `lineage` groups
by an event key that pairs exactly two rows, `observation` does not group at all. A
transfer source therefore declares

    "group": {"column": "dt_job", "row_order_column": "row_id"}

and one whole value of that column is one molecule. The cursor is that value; a batch is
always a whole number of groups.

It also declares where the DESTINATION's identity is CONFIRMED:

    "container": {"relation": "dt_inventory", "key_column": "dt_job",
                  "lot_column": "dt_lot", "slot_column": "dt_slot"}

🔴 This is the declaration that keeps the round honest. `dt_log` carries `dt_lot`/`dt_slot`
of its own and `table_config.json` says in its own words what they are: "the INFERENCE
TARGETS -- 40% absent, and 10% PRESENT BUT WRONG, which is worse than absent because a
wrong value makes a join succeed quietly", and "a guess must never sit inside an identity".
A translator that read them would produce a movement chain that joins plausibly and wrongly
for a tenth of the fab. So the identity comes from the confirming relation, the row's own
reading is preserved beside it as `container_recorded` (never as identity), and the atom
says which of the two it got through its DERIVATION - `job_run_to_confirmed_container` or
`job_run_to_job`.

MEASURED ON `assy_manager`, 2026-08-14, and this is why the distinction is not theoretical:
`dt_inventory` holds 401 rows and exactly ONE of them has a non-blank `dt_lot` - the string
`'DT_LOT'`, a spreadsheet HEADER that was ingested as data. So the confirmed path currently
resolves for ZERO jobs, every atom lands under `job_run_to_job`, and the ledger says
"unconfirmed" instead of inventing a container.

RELOAD POLICY
-------------
Read once per RUN, not per row. `crud`'s own hard-won rule (QA D1/F4): re-reading config
per access makes the snapshot shift mid-job and can turn a 0-row write into a SUCCESS,
while caching it forever kills hot reload. A backfill run is the job boundary here, so
the snapshot is taken at the top of the run and passed down as an argument.
"""
from __future__ import annotations

import hashlib
import json
import os

CONFIG_FILENAME = "ledger_config.json"

#: The pairing strategies this translator implements. A config naming anything else is a
#: startup error rather than a runtime surprise - a misspelled strategy that silently
#: fell back to "none" would produce a ledger with no slot chain and no complaint.
SLOT_PAIRING_STRATEGIES = frozenset({"shared_wafer", "slot_preserving", "none"})
LINEAGE_STRATEGIES = frozenset({"parent_child", "none"})

#: The grammars a source may declare. `lineage` is the default and the one every
#: declaration written before ruling R-2026-08-14-D speaks.
SOURCE_KIND_LINEAGE = "lineage"
SOURCE_KIND_OBSERVATION = "observation"
#: 🔴 THE THIRD GRAMMAR (`dt_log`, 2026-08-14). Neither of the two above fits, and the
#: reason is the UNIT rather than the columns:
#:
#:   * `lineage` assembles a molecule from a PAIR of rows found by an event key. `dt_log`
#:     has no pair - and no event id at all; what it has is a job column that many rows
#:     share.
#:   * `observation` treats ONE ROW as one utterance. `dt_log`'s row is one DIE, and the
#:     declared atom unit is the JOB-RUN, so its rows must be GROUPED - which is exactly
#:     the thing the observation driver is built not to do.
#:
#: So a transfer source declares the column its rows GROUP BY, and one whole group is one
#: molecule. The cursor is that column's value, and a batch is always a whole number of
#: groups (the same cut the lineage driver makes on `event_time`, one column over).
SOURCE_KIND_TRANSFER = "transfer"

#: 🔴 THE FOURTH GRAMMAR, AND THE ONLY ONE WITH NO PYTHON CLASS OF ITS OWN
#: (`ADMIN_SETUP_BRIEF` §6-2, 2026-08-15).
#:
#: The observation that produced it: A TRANSLATOR BELONGS TO A SHAPE, NOT TO A SOURCE.
#: `void_obs` and `delam_obs` are two sources sharing one translator because they are one
#: shape. So the thing that is actually missing when a new table arrives is not a source
#: entry - it is a SHAPE - and writing a Python class per shape is what put「코드 0줄」out
#: of reach. This kind takes the row -> atom mapping ITSELF as a declaration (`emit`), so a
#: table whose shape is「one row says N things」needs no code at all.
#:
#: 🔴 DELIBERATELY NARROW, AND THE BOUNDARY IS MEASURED. One row -> 1..N atoms, value
#: mapping, and branching on a column's value. STRUCTURAL TRANSFORMS ARE OUT: one
#: `lot_event` row pairs `slot_numbers` against `wafer_ids` POSITIONALLY and yields
#: `derived_from` 1 + `has_wafer` 19. Expressing that declaratively means inventing a small
#: programming language, and a config file that is a programming language is a programming
#: language nobody can debug. Those shapes keep their Python classes.
#:
#: ⚠️ THIS IS NOT R-2026-08-15-M ⑤'s `derivation`, AND THE TWO MUST NOT BE CONFLATED.
#: That ruling's fourth kind evaluates conditions AGAINST THE LEDGER (via the walk) to
#: produce class-3 INFERENCE carrying evidence atom ids. This one translates A SOURCE ROW
#: it is looking straight at, which is the same epistemic act the other three perform. They
#: occupy the same "fourth" slot in two documents written a day apart; the later one
#: (`ADMIN_SETUP_BRIEF` §6-2) is canonical and is what this implements. The walk-reading
#: inference kind remains unbuilt, and calling this one `derivation` would have quietly
#: given class-3 rules' name to class-2 claims.
SOURCE_KIND_DECLARED = "declared"

SOURCE_KINDS = frozenset({SOURCE_KIND_LINEAGE, SOURCE_KIND_OBSERVATION,
                          SOURCE_KIND_TRANSFER, SOURCE_KIND_DECLARED})

#: Columns a DECLARED source must map. Only one: the route back to the row it came from.
#: Everything else this grammar reads is named inside `emit`, by the physical column name,
#: because a logical-name indirection would be a second vocabulary to keep in step with the
#: first for no gain - the declaration already says which column it means.
DECLARED_REQUIRED_COLUMNS = ("row_identity",)

#: 🔴 THE HONESTY FIELD, REQUIRED (ruling R-2026-08-15-N ②). A registry row's `occurred_at`
#: should be WHEN THE CLAIM WAS MADE - assigned, approved. Most registry tables do not have
#: such a column and only carry `created_at`, which is when the ROW appeared. Both are legal;
#: silently passing the second off as the first is not, because every downstream question of
#: the form「when did this become true」would then be answered with「when did this get
#: loaded」. So the declaration must SAY WHICH, and there is no default: `claim_time` asserts
#: that the column really is the moment of the claim, `row_created` admits it is not.
OCCURRED_AT_BASES = frozenset({"claim_time", "row_created"})

#: The `when` clause's operators. Closed, for the reason every other vocabulary here is
#: closed: an operator invented at a call site is a branch nobody can chart, and a
#: MISSPELLED one that silently fell through to "always true" would emit atoms nobody
#: declared while every test stayed green.
WHEN_OPERATORS = frozenset({"equals", "not_equals", "in", "not_in", "present", "absent"})

#: The prefix that makes a declared value a COLUMN REFERENCE rather than a literal.
#: `"$leg"` is the row's `leg`; `"leg"` is the four-character string. A literal `$` is
#: written `$$`.
COLUMN_REF_PREFIX = "$"

#: 🔴 THE RESOLUTION CLASS OF AN `emit` RULE, DECLARED BY THE OPERATOR. No default.
#:
#: Design §6's ladder is `0 핀(사람) > 1 확정된 체인 주장 > 2 관측 > 3 추론`, and the two
#: ranks a source translation can land in are the bottom two. Which one is not a property
#: of the table, the predicate or the translator - it is a property of WHERE THE ATOM'S
#: CONTENT CAME FROM, and only the person writing the rule knows that.
#:
#: WHY THE OPERATOR AND NOT A DEVELOPER
#: -------------------------------------
#: The classification rule used to be enforced by a test carrying a hand-maintained list,
#: which worked while every derivation was born in Python. This grammar's derivations are
#: born in a config file written through a screen, and the standing check would then fail
#: in CI for a developer to clear - a developer who was not there when the rule was written
#: and would be guessing at somebody else's intent. Worse, until they cleared it, USING the
#: admin screen would break the build. So the choice moves to the only person who holds the
#: answer, at the only moment they hold it, in exactly the shape `traversable` already uses:
#: explicit, no default, refused at save.
#:
#: WHY IT MATTERS THAT THIS IS NOT COSMETIC
#: -----------------------------------------
#: The ledger has no UPDATE, so this stamp is permanent, and the resolution order TRUSTS
#: it: a class-2 claim beats a class-3 one automatically, with nobody retracting anything.
#: An inference-grade claim wearing observation grade therefore wins against a real
#: measurement - silently, and forever.
EMIT_CLASS_OBSERVATION = "observation"
EMIT_CLASS_INFERENCE = "inference"
EMIT_CLASSES = {
    #: 「관측」 - the source row SAID this. The translator reshaped what was in front of it
    #: and added nothing that was not there.
    EMIT_CLASS_OBSERVATION: 2,
    #: 「추론」 - the atom's content rests on a DECLARED ASSUMPTION not present in the row
    #: (a convention, a rule, a default). `slot_preserving` is the existing example: the
    #: source never uttered the slot pairing; an operator declared that splits preserve
    #: slots, and every atom made under it is a conclusion rather than a report.
    EMIT_CLASS_INFERENCE: 3,
}

#: Columns a LINEAGE source must map. Named here rather than inline so the observation
#: list beside it is visibly a different list rather than an exception to this one.
LINEAGE_REQUIRED_COLUMNS = ("lot", "event_type", "slots", "wafers", "parent_lot",
                            "child_lot", "row_identity")

#: Columns an OBSERVATION source must map. Everything else about a finding - where on the
#: chip, how big, which class - is OPTIONAL, because a source that does not utter a thing
#: must be able to say so by leaving it out rather than by declaring a column that does
#: not exist. These three are the ones without which there is no atom at all: the route
#: back to the row, the subject it is about, and the run that makes it countable.
OBSERVATION_REQUIRED_COLUMNS = ("row_identity", "wafer", "run_key")

#: The optional ones, listed so a typo in a declaration is caught rather than silently
#: producing an atom with a field missing. Add-only; a name absent from here is refused.
OBSERVATION_OPTIONAL_COLUMNS = ("die_x", "die_y", "die_gate", "inchip_x", "inchip_y",
                                "extent_x", "extent_y", "unit", "class")

#: Columns a TRANSFER source must map. `group_key` is the column whose value makes a
#: molecule; `wafer` is the substrate the moved dies belong to and therefore the SUBJECT.
#: Everything else a transfer row carries is optional for the same reason it is optional
#: on an observation source: a source that does not utter a thing must be able to stay
#: silent rather than declare a column that is not there.
TRANSFER_REQUIRED_COLUMNS = ("row_identity", "group_key", "wafer")

#: The optional ones. `recorded_lot`/`recorded_slot` are what the SOURCE ROW wrote down
#: about the destination container. 🔴 They are NEVER identity - on `dt_log` they are the
#: table's own declared inference targets ("40% absent, and 10% PRESENT BUT WRONG"), and
#: `table_config.json`'s own rule is that "a guess must never sit inside an identity".
#: They are carried as a preserved utterance so the confirmation flow has evidence to
#: argue with, and the container's identity comes from the confirmation relation below.
TRANSFER_OPTIONAL_COLUMNS = ("recorded_lot", "recorded_slot")

#: The derivation an observation atom carries: ONE source row, uttered as it stands.
DERIVATION_OBSERVATION_ROW = "observation_row"

#: The two derivations a transfer atom may carry, and the difference between them is the
#: WHOLE honesty of this grammar - it is queryable, exactly as `#slot_preserving` is:
#:
#:     WHERE source_translator_ver LIKE '%#job_run_to_confirmed_container'
#:
#: separates the atoms whose destination has a confirmed physical identity from the ones
#: whose destination could only be named as the acquisition job. No new column and no new
#: payload flag: the derivation field already means "which rule made this claim", and
#: `gate.screen_molecule` already refuses a derivation the config did not declare.
DERIVATION_TRANSFER_CONFIRMED = "job_run_to_confirmed_container"
DERIVATION_TRANSFER_JOB = "job_run_to_job"

#: 🔴 The predicate a transfer source's translator emits. One spelling, for the reason
#: `OBSERVATION_PREDICATE` has one.
TRANSFER_PREDICATE = "transferred"

#: The `type` words of a `transferred` payload's `from` / `to` containers. They are
#: spelled here because the FIXTURE GENERATORS already emit them
#: (`server/scripts/seed_syn_process_ledger.py`'s `PLACE_*`), and position continuity -
#: §2-bis's "event N's `to` is event N+1's `from`" - is a comparison of the WHOLE
#: container object. Two spellings of one place would silently produce a chain that never
#: joins, which is the failure this grammar exists to make visible rather than commit.
PLACE_WAFER_GRID = "wafer_grid"
PLACE_DT_SLOT = "dt_slot"
#: 🔴 A place the fixture does NOT have, and it is new on purpose. A DT tape addressed by
#: the JOB that filled it is the ACQUISITION unit, not the physical wafer - `table_config`
#: says so in its own words ("MAP KEY IS (dt_lot, dt_slot) -- the PHYSICAL UNIT, not the
#: acquisition unit"). Giving it its own type is what makes an unjoinable hop READ as
#: unjoinable instead of silently matching nothing under a name that promised to match.
PLACE_DT_JOB = "dt_job"

#: 🔴 The predicate an observation source's translator emits. ONE SPELLING, because two
#: modules need it: the translator that writes it and `ledger_kinds`, which answers「이
#: 종류가 원장에 있는가」by asking which declaration carries which kind under which word.
#: A literal in each would be a linkage that agrees on the day it is written and silently
#: stops agreeing the day the word changes.
OBSERVATION_PREDICATE = "observed"

#: The shape a source's timestamps are read in when the source declares no
#: `occurred_at_format`. Product owner ruling 2026-08-13: fab timestamps are ISO 8601
#: with the `T` separator (`2026-08-13T13:45:00`), so the default names what production
#: actually emits. `store._candidate_formats` reads the RFC 3339 space spelling of this
#: same shape as well, which is why a development box holding `2026-08-13 13:45:00` is
#: not a second format.
#:
#: One constant rather than one literal per caller: the translator and the lag report
#: both fall back to it, and two copies of a default are two things that drift apart
#: silently - the reader would then disagree with the lag report about what the cursor
#: position means.
DEFAULT_OCCURRED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"


class LedgerConfigError(ValueError):
    """The declaration is missing or self-contradictory. Raised at load, never later."""


def _config_dir():
    try:
        import paths
        return paths.CONFIG_DIR
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config")


def config_path(filename: str = CONFIG_FILENAME) -> str:
    return os.path.join(_config_dir(), filename)


def sample_path(path: str = None) -> str:
    active = path or config_path()
    return os.path.join(
        os.path.dirname(os.path.abspath(active)),
        "sample",
        os.path.basename(active) + ("" if active.endswith(".sample") else ".sample"),
    )


def load(path: str = None) -> dict:
    """Load and validate. Falls back to ``sample/<name>.sample`` when live is absent.

    The `.sample` fallback is this project's convention for gitignored operator config
    (`server/config/*.json` is the operator's, `sample/*.json.sample` ships). Without it
    a fresh checkout could not run the backfill at all, and "it works on the box that has
    the untracked file" is not a deployable state.
    """
    path = path or config_path()
    if not os.path.exists(path):
        sample = sample_path(path)
        if os.path.exists(sample):
            path = sample
        else:
            raise LedgerConfigError(
                f"no ledger configuration at {path} (and no sample at {sample}). The "
                f"translator refuses to run rather than guess a time column.")
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    validate(raw, origin=path)
    raw["__origin__"] = path
    return raw


def validate(cfg: dict, origin: str = "<memory>"):
    """Raise `LedgerConfigError` on anything the translator would otherwise have to
    guess about. Returns `cfg` so it can be used inline."""
    if not isinstance(cfg, dict):
        raise LedgerConfigError(f"{origin}: the configuration must be an object")
    sources = cfg.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise LedgerConfigError(f"{origin}: 'sources' must declare at least one source")

    for name, source in sources.items():
        where = f"{origin}: sources.{name}"
        if not isinstance(source, dict):
            raise LedgerConfigError(f"{where} must be an object")

        if not str(source.get("occurred_at_column") or "").strip():
            raise LedgerConfigError(
                f"{where}.occurred_at_column is not declared. Design §10 risk 1 and the "
                f"brief's risk 2: the world time must come from a named source column, "
                f"and arrival time may never stand in for it. Declare the column or "
                f"remove the source.")
        if not str(source.get("occurred_at_timezone") or "").strip():
            raise LedgerConfigError(
                f"{where}.occurred_at_timezone is not declared. The source's timestamps "
                f"are naive text; without a declared zone the stored instant would be "
                f"whatever the translating machine happened to be set to.")

        from . import vocabulary
        if "subject_type" in source:
            # The retired singular. Errors rather than being ignored, and the message
            # carries the fix: a config that silently means nothing is the defect ruling
            # R-2026-08-13-D exists to end, so the one thing this must NOT do is accept
            # the old key and quietly do something else with it.
            raise LedgerConfigError(
                f"{where}.subject_type (singular) was retired by ruling R-2026-08-13-D. "
                f"It reached no atom - the translator names each atom's type as a literal "
                f"- so it declared a contract nothing enforced. Rename it to "
                f"'subject_types' and give it the LIST of every entity type this source "
                f"may speak about, e.g. \"subject_types\": [\"Lot\", \"Wafer\"]. That list "
                f"is enforced: an atom outside it is refused by name "
                f"('undeclared_subject_type').")

        subject_types = source.get("subject_types")
        if not isinstance(subject_types, list) or not subject_types:
            raise LedgerConfigError(
                f"{where}.subject_types must be a non-empty LIST of the entity types this "
                f"source's atoms may be about ({', '.join(sorted(vocabulary.ENTITY_TYPES))}"
                f"). It is the translator's declared extension and the gate refuses "
                f"anything outside it, so an absent list would refuse every atom.")
        for member in subject_types:
            if member not in vocabulary.ENTITY_TYPES:
                raise LedgerConfigError(
                    f"{where}.subject_types names {member!r}, which is not a declared "
                    f"entity type ({', '.join(sorted(vocabulary.ENTITY_TYPES))}). Adding "
                    f"an entity type is a vocabulary decision, not a config one.")

        kind = source.get("kind", SOURCE_KIND_LINEAGE)
        if kind not in SOURCE_KINDS:
            raise LedgerConfigError(
                f"{where}.kind {kind!r} is not one of {sorted(SOURCE_KINDS)}. The kind "
                f"selects which grammar this source's translator speaks, so a misspelling "
                f"would validate the declaration against the wrong required columns.")
        if kind == SOURCE_KIND_OBSERVATION:
            _validate_observation_source(source, where)
            continue
        if kind == SOURCE_KIND_TRANSFER:
            _validate_transfer_source(source, where)
            continue
        if kind == SOURCE_KIND_DECLARED:
            _validate_declared_source(source, where)
            continue

        vocab = source.get("vocabulary")
        if not isinstance(vocab, dict) or not vocab:
            raise LedgerConfigError(
                f"{where}.vocabulary must map at least one source event type to a rule. "
                f"An empty map means every event is refused, which is legal but is never "
                f"what somebody meant to write.")
        for event_type, rule in vocab.items():
            rule_where = f"{where}.vocabulary.{event_type}"
            if not isinstance(rule, dict):
                raise LedgerConfigError(f"{rule_where} must be an object")
            lineage = rule.get("lineage", "none")
            if lineage not in LINEAGE_STRATEGIES:
                raise LedgerConfigError(
                    f"{rule_where}.lineage {lineage!r} is not one of "
                    f"{sorted(LINEAGE_STRATEGIES)}")
            pairing = rule.get("slot_pairing", "none")
            if pairing not in SLOT_PAIRING_STRATEGIES:
                raise LedgerConfigError(
                    f"{rule_where}.slot_pairing {pairing!r} is not one of "
                    f"{sorted(SLOT_PAIRING_STRATEGIES)}. A misspelling here would "
                    f"silently produce a ledger with no slot chain.")
            if pairing != "none" and lineage == "none":
                raise LedgerConfigError(
                    f"{rule_where}: slot_pairing {pairing!r} needs a parent/child pair, "
                    f"but lineage is 'none' - there would be no two lots to map between")

        columns = source.get("columns")
        if not isinstance(columns, dict):
            raise LedgerConfigError(f"{where}.columns must map logical names to source "
                                    f"columns")
        for required in LINEAGE_REQUIRED_COLUMNS:
            if not str(columns.get(required) or "").strip():
                raise LedgerConfigError(f"{where}.columns.{required} is not declared")

    batch = cfg.get("batch") or {}
    size = int(batch.get("molecules_per_transaction", 200))
    if size < 1:
        raise LedgerConfigError(f"{origin}: batch.molecules_per_transaction must be >= 1")
    return cfg


def _validate_observation_source(source: dict, where: str):
    """Ruling R-2026-08-14-D's declaration, checked. Every rule here has a consumer.

    🔴 The one that matters most is `run`. An observation with no inspection run is an
    observation with no denominator, and the `observed` signature makes `run_uid` a
    REQUIRED payload field precisely so that such an atom cannot be written. If the
    declaration did not have to name the run relation, the translator would have nothing
    to read it from and every atom would be refused at the gate for a reason that pointed
    at the wrong file.
    """
    finding_kind = str(source.get("finding_kind") or "").strip()
    if not finding_kind:
        raise LedgerConfigError(
            f"{where}.finding_kind is not declared. An observation source translates ONE "
            f"kind of finding (`server/finding_kinds.py` is the registry of what a kind "
            f"is), and the value lands in every atom's payload - guessing it from the "
            f"table name would put an unreviewed word in the ledger.")

    run = source.get("run")
    if not isinstance(run, dict):
        raise LedgerConfigError(
            f"{where}.run must declare the inspection run this source's findings belong "
            f"to: {{\"relation\": ..., \"key_column\": ..., \"method_column\": ...}}. "
            f"It is where `occurred_at` is read from (a finding has the time of the LOOK "
            f"that found it) and it is the denominator - `observed` requires `run_uid` in "
            f"its payload, so a source with no run declaration can produce no atoms.")
    for field in ("relation", "key_column"):
        if not str(run.get(field) or "").strip():
            raise LedgerConfigError(f"{where}.run.{field} is not declared")

    watermark = source.get("watermark")
    if not isinstance(watermark, dict) or not watermark.get("columns"):
        raise LedgerConfigError(
            f"{where}.watermark must declare the cursor columns, e.g. "
            f"{{\"columns\": [\"updated_at\", \"row_id\"]}}. An observation source cannot "
            f"use a world-time cursor: a bulk load stamps one `updated_at` on every row, "
            f"so the whole load would be one indivisible group. The declared keyset must "
            f"be UNIQUE and index-backed.")
    columns_declared = [str(c).strip() for c in watermark["columns"]]
    if not all(columns_declared):
        raise LedgerConfigError(f"{where}.watermark.columns holds a blank column name")

    columns = source.get("columns")
    if not isinstance(columns, dict):
        raise LedgerConfigError(f"{where}.columns must map logical names to source "
                                f"columns")
    for required in OBSERVATION_REQUIRED_COLUMNS:
        if not str(columns.get(required) or "").strip():
            raise LedgerConfigError(
                f"{where}.columns.{required} is not declared. An observation atom needs "
                f"the route back to its row, the wafer it is about, and the run that "
                f"makes it countable; the rest of a finding is optional because a source "
                f"that does not utter a thing must be able to stay silent about it.")
    known = set(OBSERVATION_REQUIRED_COLUMNS) | set(OBSERVATION_OPTIONAL_COLUMNS)
    # `__`-prefixed keys are this config file's comment convention (every block carries
    # them and `ledger_structure` already filters on the same prefix). They are not
    # mappings and must not be judged as ones.
    undeclared = sorted(name for name, value in columns.items()
                        if not name.startswith("__") and name not in known
                        and value is not None)
    if undeclared:
        raise LedgerConfigError(
            f"{where}.columns names {', '.join(undeclared)}, which this translator does "
            f"not read (known: {', '.join(sorted(known))}). A mapping nothing consumes is "
            f"a declaration that teaches the reader a contract nobody enforces - ruling "
            f"R-2026-08-13-D - and here it would usually be a typo for one that IS read.")
    if "vocabulary" in source:
        raise LedgerConfigError(
            f"{where}.vocabulary is a LINEAGE declaration (it maps source event types to "
            f"lineage rules) and an observation source has no event types - one row is one "
            f"utterance. Remove it, or set kind to '{SOURCE_KIND_LINEAGE}'.")


def _validate_transfer_source(source: dict, where: str):
    """The transfer declaration, checked. Every rule below has a consumer.

    🔴 THE ONE THAT MATTERS MOST IS `container`. A transfer atom's `to` is a PLACE, and
    position continuity joins places by value - so the question "what is this destination's
    identity" has to be answered from a declared relation rather than from whichever column
    on the row looks like it. On `dt_log` the row's own `dt_lot`/`dt_slot` is the table's
    declared INFERENCE TARGET, and using it would produce a chain that joins plausibly and
    wrongly for the ~10% of rows the fixture deliberately mis-fills. If the declaration did
    not have to name the confirming relation, the only available answer would be the wrong
    one, and nothing would say so.

    A source with no confirmation relation at all is legal and says so by declaring
    `"container": {"relation": null}` - it then emits every atom under
    `job_run_to_job` and the ledger reads back "this destination was never confirmed"
    rather than "this destination is a lot named X".
    """
    group = source.get("group")
    if not isinstance(group, dict) or not str(group.get("column") or "").strip():
        raise LedgerConfigError(
            f"{where}.group must declare the column whose value makes one molecule, e.g. "
            f"{{\"column\": \"dt_job\"}}. A transfer source's rows are DIES and its atom "
            f"unit is the job-run, so the driver has to know which column groups them; "
            f"guessing it would make the batch boundary fall inside a source event, which "
            f"is the half-landing the whole gate exists to prevent.")
    if not str(group.get("row_order_column") or "").strip():
        raise LedgerConfigError(
            f"{where}.group.row_order_column is not declared. The page is ordered by "
            f"(group column, this column) so that a group is CONTIGUOUS and a re-read "
            f"returns the same rows in the same order; without a tiebreak the order "
            f"inside a group is whatever the plan happened to produce.")

    container = source.get("container")
    if not isinstance(container, dict):
        raise LedgerConfigError(
            f"{where}.container must declare where the DESTINATION's identity is "
            f"confirmed: {{\"relation\": ..., \"key_column\": ..., \"lot_column\": ..., "
            f"\"slot_column\": ...}}, or {{\"relation\": null}} to state that this source "
            f"has no confirming relation at all. It is not optional, because the "
            f"alternative to a declared confirmation is a translator reading whichever "
            f"column on the row looks like the answer - and on this source that column is "
            f"the declared inference target.")
    if str(container.get("relation") or "").strip():
        for field in ("key_column", "lot_column", "slot_column"):
            if not str(container.get(field) or "").strip():
                raise LedgerConfigError(
                    f"{where}.container.{field} is not declared. A relation that cannot "
                    f"be keyed and read produces no confirmation, which is silently the "
                    f"same as having declared none.")

    columns = source.get("columns")
    if not isinstance(columns, dict):
        raise LedgerConfigError(f"{where}.columns must map logical names to source "
                                f"columns")
    for required in TRANSFER_REQUIRED_COLUMNS:
        if not str(columns.get(required) or "").strip():
            raise LedgerConfigError(
                f"{where}.columns.{required} is not declared. A transfer atom needs the "
                f"route back to its rows, the column that groups them into one job-run, "
                f"and the substrate the moved dies belong to - which is the SUBJECT, "
                f"because a die is COMPOSED and has no identity to carry through a move.")
    known = set(TRANSFER_REQUIRED_COLUMNS) | set(TRANSFER_OPTIONAL_COLUMNS)
    undeclared = sorted(name for name, value in columns.items()
                        if not name.startswith("__") and name not in known
                        and value is not None)
    if undeclared:
        raise LedgerConfigError(
            f"{where}.columns names {', '.join(undeclared)}, which this translator does "
            f"not read (known: {', '.join(sorted(known))}). A mapping nothing consumes is "
            f"a declaration that teaches the reader a contract nobody enforces - ruling "
            f"R-2026-08-13-D.")
    if str(columns["group_key"]).strip() != str(group["column"]).strip():
        raise LedgerConfigError(
            f"{where}: columns.group_key is {columns['group_key']!r} but group.column is "
            f"{group['column']!r}. They name the same physical column from two sides (the "
            f"driver orders and cuts by one, the translator reads the other), and two "
            f"spellings would make the molecule's key disagree with the batch boundary.")
    if "vocabulary" in source:
        raise LedgerConfigError(
            f"{where}.vocabulary is a LINEAGE declaration (it maps source event types to "
            f"lineage rules) and a transfer source has no event types - a job-run is one "
            f"movement. Remove it, or set kind to '{SOURCE_KIND_LINEAGE}'.")


def _validate_declared_source(source: dict, where: str):
    """The declarative grammar, checked. `ADMIN_SETUP_BRIEF` §6-2.

    🔴 EVERY RULE HERE EXISTS BECAUSE THE ALTERNATIVE IS A SILENT WRONG ATOM. This kind has
    no Python class reviewing its output, so the declaration IS the program and this
    function is the only compiler it gets. The gate is the second net - a malformed atom is
    refused rather than written - but a refusal at backfill time is a worse place to learn
    about a typo than a refusal at save time, which is what this produces.
    """
    basis = str(source.get("occurred_at_basis") or "").strip()
    if basis not in OCCURRED_AT_BASES:
        raise LedgerConfigError(
            f"{where}.occurred_at_basis must be declared as one of "
            f"{sorted(OCCURRED_AT_BASES)} (ruling R-2026-08-15-N ②). A registry row's world "
            f"time should be WHEN THE CLAIM WAS MADE; most registry tables only carry a "
            f"row-creation timestamp. Both are legal and they mean different things, so the "
            f"declaration has to say which - 'claim_time' asserts that "
            f"{source.get('occurred_at_column')!r} really is the moment of the claim, "
            f"'row_created' admits it is when the row appeared. There is no default, "
            f"because a defaulted answer here would silently turn 'when did this become "
            f"true' into 'when did this get loaded'.")

    watermark = source.get("watermark")
    if not isinstance(watermark, dict) or not watermark.get("columns"):
        raise LedgerConfigError(
            f"{where}.watermark must declare the cursor columns, e.g. "
            f"{{\"columns\": [\"updated_at\", \"row_id\"]}}. A registry is UPDATED in place "
            f"(R-2026-08-15-N ③ - an update is a new atom, not an edit), so the cursor has "
            f"to be monotone under edit as well as insert; that is what an "
            f"(updated_at, row_id) keyset is and what a world-time cursor is not.")
    if not all(str(c).strip() for c in watermark["columns"]):
        raise LedgerConfigError(f"{where}.watermark.columns holds a blank column name")

    columns = source.get("columns")
    if not isinstance(columns, dict):
        raise LedgerConfigError(f"{where}.columns must map logical names to source columns")
    for required in DECLARED_REQUIRED_COLUMNS:
        if not str(columns.get(required) or "").strip():
            raise LedgerConfigError(
                f"{where}.columns.{required} is not declared. Every atom needs a route back "
                f"to the row that uttered it - without one the claim cannot be argued with, "
                f"and re-translation after a rule change has nothing to re-read.")
    known = set(DECLARED_REQUIRED_COLUMNS)
    undeclared = sorted(name for name, value in columns.items()
                        if not name.startswith("__") and name not in known
                        and value is not None)
    if undeclared:
        raise LedgerConfigError(
            f"{where}.columns names {', '.join(undeclared)}, which this grammar does not "
            f"read (known: {', '.join(sorted(known))}). A declared source names its columns "
            f"INSIDE `emit`, by physical name (\"$leg\"), so a logical-name map here would "
            f"be a second vocabulary that nothing consumes - ruling R-2026-08-13-D.")

    emit = source.get("emit")
    if not isinstance(emit, list) or not emit:
        raise LedgerConfigError(
            f"{where}.emit must be a non-empty LIST of the atoms one row produces. This is "
            f"the whole grammar: a source declared with no `emit` reads every row and says "
            f"nothing, which is never what somebody meant to write.")
    if "vocabulary" in source:
        raise LedgerConfigError(
            f"{where}.vocabulary is a LINEAGE declaration (source event type -> lineage "
            f"rule). A declared source branches inside each `emit` rule's `when` instead.")

    seen_rules = set()
    declared_subjects = set(source.get("subject_types") or ())
    for index, rule in enumerate(emit):
        _validate_emit_rule(rule, f"{where}.emit[{index}]", seen_rules)
        # 🔴 CROSS-CHECKED HERE RATHER THAN LEFT TO THE GATE. The gate WOULD refuse these
        # atoms (`undeclared_subject_type`), but it would do it once per row at backfill
        # time - and「the declaration contradicts itself」is knowable the moment it is
        # written. Deferring a save-time-knowable error to run time is exactly the delay
        # this round exists to remove.
        subject_type = (rule.get("subject") or {}).get("type")
        if subject_type and subject_type not in declared_subjects:
            raise LedgerConfigError(
                f"{where}.emit[{index}].subject.type is '{subject_type}', which is not in "
                f"this source's subject_types ({', '.join(sorted(declared_subjects)) or 'none'}). "
                f"`subject_types` is the translator's declared EXTENSION - the types its "
                f"atoms are allowed to be about - so every atom this rule makes would be "
                f"refused by name. Add '{subject_type}' to subject_types, or point the rule "
                f"at a type this source is allowed to speak about.")


def _validate_emit_rule(rule: dict, where: str, seen_rules: set):
    """One row -> one atom, declared. The unit of this grammar."""
    from . import vocabulary

    if not isinstance(rule, dict):
        raise LedgerConfigError(f"{where} must be an object")

    name = str(rule.get("rule") or "").strip()
    if not name:
        raise LedgerConfigError(
            f"{where}.rule is not declared. It names the DERIVATION every atom this rule "
            f"makes will carry, so「which declared rule made this claim」is queryable "
            f"(`source_translator_ver LIKE '%#<rule>'`) exactly as `#slot_preserving` is. "
            f"The gate refuses an atom whose derivation the config did not declare, so an "
            f"unnamed rule could emit nothing at all.")
    if name in seen_rules:
        raise LedgerConfigError(
            f"{where}.rule {name!r} is declared twice. Two rules under one derivation name "
            f"are two claims that cannot be told apart afterwards.")
    seen_rules.add(name)

    predicate = str(rule.get("predicate") or "").strip()
    if not predicate:
        raise LedgerConfigError(f"{where}.predicate is not declared")

    # 🔴 THE CLASS, CHOSEN EXPLICITLY. Same discipline as `traversable`: no default,
    # because a defaulted class is a claim about evidence that nobody made - and this one
    # decides which atom WINS when two disagree.
    rule_class = rule.get("class")
    if rule_class not in EMIT_CLASSES:
        raise LedgerConfigError(
            f"{where}.class must be declared as '{EMIT_CLASS_OBSERVATION}' or "
            f"'{EMIT_CLASS_INFERENCE}' (design §6: 2 관측 / 3 추론); got "
            f"{rule_class!r}. Ask one question about the atom this rule makes: does its "
            f"content come from the ROW IN FRONT OF YOU, or from a convention or default "
            f"that the row never uttered? The row -> '{EMIT_CLASS_OBSERVATION}'. A "
            f"convention -> '{EMIT_CLASS_INFERENCE}'. There is no default, because the "
            f"ledger never updates and the resolution order trusts this: a class-2 claim "
            f"beats a class-3 one automatically, so an assumption labelled as an "
            f"observation would silently and permanently outrank a real measurement.")
    # NOT checked against the vocabulary here, and that is deliberate: the vocabulary is
    # merged from code AND the operator's declaration file, so a predicate registered in
    # the same admin session as this source would be refused by a check that ran at config
    # load time in a process whose vocabulary cache predates it. The GATE checks it, per
    # atom, against the live merged set - which is the check that cannot go stale.

    subject = rule.get("subject")
    if not isinstance(subject, dict):
        raise LedgerConfigError(
            f"{where}.subject must declare the atom's subject: "
            f"{{\"type\": \"Wafer\", \"keys\": {{\"wafer\": \"$base_wafer_id\"}}}}")
    subject_type = subject.get("type")
    if subject_type not in vocabulary.ENTITY_TYPES:
        raise LedgerConfigError(
            f"{where}.subject.type {subject_type!r} is not a declared entity type "
            f"({', '.join(sorted(vocabulary.ENTITY_TYPES))}). Adding an entity type is a "
            f"vocabulary decision, not a config one.")
    keys = subject.get("keys")
    expected = vocabulary.ENTITY_TYPES[subject_type]["keys"]
    if not isinstance(keys, dict) or sorted(keys) != sorted(expected):
        raise LedgerConfigError(
            f"{where}.subject.keys must name EXACTLY the key parts of "
            f"'{subject_type}' ({', '.join(expected)}); got "
            f"{sorted(keys) if isinstance(keys, dict) else keys!r}. A partial identity is "
            f"the concatenation incident one column over - design §3 - and an extra part is "
            f"an identity this type does not have.")

    declared_object = rule.get("object")
    if declared_object is not None:
        if not isinstance(declared_object, dict):
            raise LedgerConfigError(f"{where}.object must be an object or null")
        kind = declared_object.get("kind")
        if kind not in vocabulary.OBJECT_KINDS:
            raise LedgerConfigError(
                f"{where}.object.kind {kind!r} is not one of "
                f"{sorted(vocabulary.OBJECT_KINDS)}")
        if kind == "value":
            if not isinstance(declared_object.get("payload"), dict) \
                    or not declared_object["payload"]:
                raise LedgerConfigError(
                    f"{where}.object.payload must be a non-empty object for a value "
                    f"object - it is what the atom actually SAYS.")
        elif kind == "entity_ref":
            target = declared_object.get("type")
            if target not in vocabulary.ENTITY_TYPES:
                raise LedgerConfigError(
                    f"{where}.object.type {target!r} is not a declared entity type")
            target_keys = declared_object.get("keys")
            target_expected = vocabulary.ENTITY_TYPES[target]["keys"]
            if not isinstance(target_keys, dict) \
                    or sorted(target_keys) != sorted(target_expected):
                raise LedgerConfigError(
                    f"{where}.object.keys must name EXACTLY the key parts of '{target}' "
                    f"({', '.join(target_expected)})")

    when = rule.get("when")
    if when is not None:
        if not isinstance(when, dict):
            raise LedgerConfigError(f"{where}.when must be an object or absent")
        if not str(when.get("column") or "").strip():
            raise LedgerConfigError(f"{where}.when.column is not declared")
        operators = [op for op in when if op in WHEN_OPERATORS]
        if len(operators) != 1:
            raise LedgerConfigError(
                f"{where}.when must carry EXACTLY ONE operator from "
                f"{sorted(WHEN_OPERATORS)}; found {operators or 'none'}. Two operators in "
                f"one clause would have to be combined by a rule nobody wrote down, and "
                f"zero is a clause that is always true - which is an `emit` rule with no "
                f"`when` at all, spelled misleadingly.")
        operator = operators[0]
        if operator in ("in", "not_in") and not isinstance(when[operator], list):
            raise LedgerConfigError(f"{where}.when.{operator} must be a list")
        unknown = [key for key in when
                   if key != "column" and key not in WHEN_OPERATORS
                   and not str(key).startswith("__")]
        if unknown:
            raise LedgerConfigError(
                f"{where}.when names {', '.join(unknown)}, which is not an operator this "
                f"grammar implements. A misspelled operator that was ignored would make the "
                f"clause always true and emit atoms nobody asked for.")


def source_kind(cfg: dict, source: str) -> str:
    """Which grammar a source speaks. Absent means `lineage` - see the module docstring."""
    return (source_config(cfg, source) or {}).get("kind", SOURCE_KIND_LINEAGE)


def source_config(cfg: dict, source: str) -> dict:
    """The declaration for one source, or `None`. `None` is a refusal, not a default."""
    return (cfg.get("sources") or {}).get(source)


def translator_version(cfg: dict, source: str) -> str:
    """`<source>/<config version>/rules:<8 hex>` - the value stamped into every atom.

    The hash covers the source's ENTIRE declaration, so two boxes running different
    `slot_pairing` rules produce atoms that are visibly different in provenance rather
    than invisibly different in meaning. That is what makes the `slot_preserving`
    judgement above auditable instead of merely documented: an atom carries which
    convention made it, and `source_raw_ref` carries how to redo it.
    """
    source_cfg = source_config(cfg, source) or {}
    material = json.dumps(source_cfg, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]
    return f"{source}/{cfg.get('version', 0)}/rules:{digest}"


def declared_subject_types(cfg: dict, source: str) -> frozenset:
    """The entity types atoms from this source are allowed to be about.

    Same shape and same direction as `declared_derivations` below: an undeclared source
    yields the EMPTY set, which refuses everything rather than allowing everything. A
    permissive default here would put the decoy back - the gate would hold a list that
    never says no, which is indistinguishable from having no list at all.
    """
    source_cfg = source_config(cfg, source) or {}
    return frozenset(source_cfg.get("subject_types") or ())


def declared_inference_derivations(cfg: dict) -> frozenset:
    """Every derivation ACROSS EVERY SOURCE that its own rule declared class 3.

    🔴 ONE HOME FOR THE ANSWER, read by two very different consumers: the RESOLVER
    (`ledger_trace.load_resolver_config` folds these into `inference_derivations`, so a
    declared assumption loses to a measurement at query time) and the CLASSIFICATION TEST
    (which now reads the declaration instead of demanding a hand-maintained code-side
    list). If those two read different sources of truth, the test goes green while the
    resolver ranks the atom the other way - which is worse than having no test, because it
    is a test that certifies the wrong answer.

    Only the `declared` grammar can contribute. The other three grammars' derivations are
    minted by Python, so their class stays a code-side judgement where a code reviewer can
    see it; there is no config field on those sources that could say otherwise.
    """
    out = set()
    for source, declaration in (cfg.get("sources") or {}).items():
        if str(source).startswith("__") or not isinstance(declaration, dict):
            continue
        if declaration.get("kind") != SOURCE_KIND_DECLARED:
            continue
        for rule in declaration.get("emit") or []:
            if not isinstance(rule, dict):
                continue
            if rule.get("class") == EMIT_CLASS_INFERENCE:
                name = str(rule.get("rule") or "").strip()
                if name:
                    out.add(name)
    return frozenset(out)


def declared_derivations(cfg: dict, source: str) -> frozenset:
    """The derivation names atoms from this source are allowed to carry.

    Assembled FROM the declaration rather than listed beside it: adding a rule to the
    config is what makes its derivation legal, so a translator cannot emit an atom under
    a rule the operator did not turn on.
    """
    source_cfg = source_config(cfg, source) or {}
    if source_cfg.get("kind") == SOURCE_KIND_DECLARED:
        # 🔴 THE DECLARATION IS THE LIST. Every `emit` rule's `rule` name becomes a legal
        # derivation and nothing else does, so this grammar's provenance is exactly as
        # queryable as the hand-written translators' - `#<rule>` on `source_translator_ver`
        # tells you which declared rule made a claim. It also means a rule REMOVED from the
        # config stops being emittable immediately, which is what makes the gate's refusal
        # the safety net the brief promises: a declaration that drifts produces named
        # refusals rather than atoms under a rule nobody can find.
        names = {str(rule.get("rule")).strip()
                 for rule in (source_cfg.get("emit") or [])
                 if isinstance(rule, dict) and str(rule.get("rule") or "").strip()}
        if source_cfg.get("register_entity_types"):
            names.add("first_sight")
        return frozenset(names)
    if source_cfg.get("kind") == SOURCE_KIND_TRANSFER:
        # BOTH transfer derivations are legal for every transfer source, and that is not
        # laxity: which one an atom carries is decided by whether the DATA confirmed the
        # destination, so an operator cannot turn one off without turning the honesty off
        # with it. What the declaration governs is whether there is a confirming relation
        # AT ALL - and a source that declares none can only ever emit the unconfirmed one.
        names = {DERIVATION_TRANSFER_JOB}
        if str(((source_cfg.get("container") or {}).get("relation") or "")).strip():
            names.add(DERIVATION_TRANSFER_CONFIRMED)
        if source_cfg.get("register_entity_types"):
            names.add("first_sight")
        return frozenset(names)
    if source_cfg.get("kind") == SOURCE_KIND_OBSERVATION:
        # One row, uttered as it stands. There is no second rule here and that is the
        # point of the grammar: an observation source has nothing to infer, so a
        # translator that ever needed a second derivation would be doing something the
        # declaration never allowed.
        names = {DERIVATION_OBSERVATION_ROW}
        if source_cfg.get("register_entity_types"):
            names.add("first_sight")
        return frozenset(names)
    names = {"positional_row"}          # (slot[i], wafer[i]) on one row - always uttered
    for rule in (source_cfg.get("vocabulary") or {}).values():
        if rule.get("lineage") == "parent_child":
            names.add("pair_field")     # parent_lot / child_lot named on the row itself
        pairing = rule.get("slot_pairing", "none")
        if pairing != "none":
            names.add(pairing)
        if rule.get("emit_register", True):
            names.add("first_sight")    # register, on first appearance of an entity
    return frozenset(names)
