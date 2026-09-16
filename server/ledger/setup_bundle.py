"""Pure Ledger authoring bundle schema and single-file loader.

This module deliberately has no database, translator, mapper, compiler, cursor, or store
imports.  Stage 2 owns only the authoring boundary: strict files in one root become one
deterministically serializable logical bundle.  Runtime registries are a later stage.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import difflib

import validation
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SETUP_VERSION = 5

#: The one authoring file. The path does not move: the operator writes here.
CONFIG_FILENAME = "ledger_config.json"

#: The whole authoring surface, in the order the file declares it.  All four are
#: REQUIRED even when empty: a missing key and an empty one mean different things to a
#: reader, and "the section does not apply to me" is a decision worth writing down.
#:
#: 🔴 `profiles` IS NOT HERE EITHER (owner, 2026-08-20: 「그럼 프로필도 소스랑 묶여야 하는거
#: 아니야?」).  The 1:1 was already ENFORCED, not merely observed: a profile had to declare
#: `source`, and `_cross_validate` refused any value but the id of the source that selected
#: it -- so a profile could never be shared and a separate section bought nothing.  The body
#: now lives inline at `sources.*.bind`, and its `source` field is gone with the section:
#: the source that HOLDS it is the answer that field used to repeat.
#: 🔴 `source_preparers` AND `mappers` ARE NOT HERE EITHER (owner, 2026-08-20: 「소스플랜
#: 준비기 맵퍼」).  A preparer's `input_columns` must be columns of a PHYSICAL relation, and
#: `relation` is declared only by a source -- so a preparer sitting in its own section was
#: always one hop away from the only declaration that could check it.  Both bodies now live
#: inline at `sources.*.prepare` and `sources.*.map`, where the
#: relation is one key away.  Measured before the move: both were 1:1 with their source, so
#: no sharing was lost.  What is reused is CODE, not declaration, and that reuse is still
#: spelled `implementation_id` + `implementation_version`, which both bodies still carry.
#: 🔴 `tables` IS NOT HERE, AND ITS ABSENCE IS THE POINT (owner, 2026-08-18: "why is
#: `tables` in the ledger json as well?").  It used to be an eighth section restating
#: the physical schema.  Measured on the live root before removal: its one relation was a
#: COMPLETE duplicate of the catalog entry -- 8 columns, 8/8 types agreeing, the same
#: single-column business key -- and no RUNNING code compared them.  (One test did, for
#: that one relation; a hand-kept pin over one row says nothing about the next one, and
#: said nothing about the sample root, whose copy had drifted into columns that exist
#: nowhere.)  Two copies that no code puts side by side do not stay equal; they drift in
#: silence and disagree only at execution.
#: The physical schema now has exactly one author, `server/config/table_config.json`,
#: which `_physical_catalog` reads.  See `PHYSICAL_CATALOG_FILENAME`.
#: 🔴 `packs` LEFT ON 2026-08-21, AND IT IS THE THIRD RESTATEMENT THIS FILE HAS RETIRED
#: (owner: 「굳이 claims 도 불필요하지 않나 … 실질적 클레임은 vocab 만 남잖아」).  A Claim
#: declared Roles and an `emit` clause; `predicate_claim` now derives both from the
#: predicate the mapping names.  See that function for what was measured first.
LOGICAL_SECTIONS = (
    "vocabulary", "entities", "sources",
)

#: 🔴 OPTIONAL, AND THE DISTINCTION IS DELIBERATE.  The operator root stops carrying a
#: `virtual_joins` section -- it was empty there, and an enabled rule is refused unless a
#: caller supplies a physically verified descriptor, so nothing was lost by dropping it.
#: But the LOADER keeps the ability to read one, because a different root does use it:
#: `server/config/sample/ontology/transfer_explorer/` supplies real descriptors and
#: `docs/qa/FEATURE_CHECKLIST.md` lists that round trip as a capability.  Removing the
#: section from a FILE and removing support from the LOADER are not the same act, and
#: only the first was asked for.
OPTIONAL_SECTIONS = ("virtual_joins",)

ALL_SECTIONS = (*LOGICAL_SECTIONS, *OPTIONAL_SECTIONS)

#: The physical-schema authority for the WHOLE system -- ingestion, the chain workers, the
#: grid, and now the ledger read the same file.  The ledger does not get a private copy and
#: does not get a private checker.
#:
#: 🔴 WHY THIS ALSO CLOSES A HOLE RATHER THAN JUST REMOVING A DUPLICATE.
#: `server/schema_drift.py` (`_register_dynamic_models`) sweeps every SQLAlchemy-mapped
#: table, and that set INCLUDES the dynamic tables built from this file.  So a column named
#: here that the database does not have is already reported.  A column named in a ledger-
#: private `tables` section was checked against nothing, which is how an invented column
#: name came to pass green (measured 2026-08-18).  Reading this file is therefore not a
#: tidier spelling of the same check -- it is the difference between a declaration that is
#: verified against the database and one that is verified against itself.  Adding a second
#: "declaration vs database" verifier would put the system back where it started: two
#: verifiers that can disagree.
PHYSICAL_CATALOG_FILENAME = "table_config.json"

_VERSIONED_ID = re.compile(r"^[^@/\s]+@[1-9][0-9]*$")
_FORBIDDEN_DECLARATION_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec", "lookup", "lookups", "declared_lookup",
    "position", "positions", "frame", "frames",
})
_FORBIDDEN_EXECUTABLE_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec",
})
#: The three binding fields that retired on 2026-08-21, kept ONLY as names to swallow.
#:
#: 🔴 EACH ONE HAD EXACTLY ONE REACHABLE VALUE, MEASURED ON THE LIVE FILE.
#: `binding_origin` was declared on 0 of 40 bindings and the one branch that read it
#: (`system_suggested`) had no writer anywhere in the tree.  `approval_status` was
#: `approved` on all 40 and no file in the repository held a value that could fail the
#: gate -- a permission that is never withheld is not a permission.  `suggestion_reason`
#: was declared on 0 of 40 and was REFUSED outright unless the origin was the branch that
#: nothing could produce.  A declaration with one legal value is a copy, not a contract.
#:
#: 🔴 THEY ARE SWALLOWED, NOT REFUSED, AND THAT IS THE WHOLE POINT OF THE CONSTANT.
#: Every config written before today carries `approval_status` on every binding.  A plain
#: removal turns `unknown_field` on at those exact paths the moment this lands, and the
#: person holding that file is mid-sentence in it.  Nothing has to be migrated for the
#: file to keep meaning what it meant, so nothing is asked of them.  See `_Problems.exact`.
_RETIRED_BINDING_FIELDS = ("approval_status", "binding_origin", "suggestion_reason")
_JOIN_FOLD_RULES = frozenset({"separator", "case", "zero_pad"})
_IMPLEMENTED_JOIN_FOLD_RULES = frozenset({"separator", "case"})
_ROLE_KINDS = frozenset({
    "entity", "time", "quantity", "identity", "order", "attribute", "symbolic",
})
_SCALAR_ROLE_KINDS = frozenset({
    "quantity", "identity", "order", "attribute", "symbolic",
})
#: 🔴 THE OBJECT KINDS A DECLARATION MAY WRITE -- one spelling, and it lives with
#: the validator because grammar's authority is by definition the thing that refuses.
#: `ledger.vocabulary` held a second copy WITHOUT "none"; measured 2026-08-27 the live
#: declaration uses `none` (register@1, 396 atoms), so the set without it was the wrong
#: one, and the admin catalogue built from it could not offer a value the declaration
#: actually uses. No underscore: three modules outside this one read it.
OBJECT_KINDS = frozenset({"none", "entity_ref", "value", "event_ref"})

#: What a `value` object HOLDS. Until now the compiler read every value object as a
#: quantity, so 「this predicate's value is a piece of text」 could not be said at all --
#: an operator with a string-valued fact had to invent a number or a second entity.
#:
#: OPTIONAL, AND ABSENCE MEANS `number`, which is what every declaration on disk means
#: today. Spelled here rather than left implicit because a default nobody can read is a
#: hardcoding with a nicer name. Closed on purpose: an open string would let "numeric"
#: become a silent claim the compiler cannot honour.
VALUE_TYPES = frozenset({"number", "string", "boolean", "timestamp"})
DEFAULT_VALUE_TYPE = "number"

#: What the EMITTER can honour today, which is not the same set (판정 178).
#:
#: 🔴 A WORD THE GRAMMAR ACCEPTS AND THE EMITTER REFUSES IS A TRAP, and the first
#: version of `VALUE_TYPES` was exactly that: the validator took `string`, the form
#: OFFERED it, and every atom built from it was then refused because the compiler pins
#: a value object to `quantity`. 「가드는 도달 가능해지는 날 틀린다」 -- except here the
#: day was the day it shipped.
#:
#: ⚠️ THE WIDER SET STAYS, because the refusal that reads 「declared, but the emitter
#: does not read it yet (S-84)」 is a different sentence from 「that is not a word」 --
#: one names a debt with a number, the other tells an operator they made a typo.
#:
#: 🔴 S-84 LANDED THREE OF THE FOUR (판정 249). `number`, `string` and `boolean` are read
#: by the emitter now - see `_OBJECT_VALUE_ROLE_KINDS`.
#:
#: ⚰️ `timestamp` JOINED THEM IN S-84-b (판정 09-10 13:44), and what unblocked it was a
#: DECLARATION rather than a clever import. A `time` Role must be timezone-AWARE and a
#: source column usually holds a string; the cast needs to know what a NAIVE reading means,
#: which is a fact about the source. Borrowing the timezone declared on `occurred_at` would
#: have been the compiler guessing, so the VALUE BINDING says it - one grammar field - and
#: the parse itself moved to `roleframe.aware_time`, which both readers already reach.
EMITTABLE_VALUE_TYPES = frozenset({"number", "string", "boolean", "timestamp"})

#: How many objects one subject may hold on this predicate. Without it an aggregate can
#: count a subject twice and NOTHING refuses -- the quiet arithmetic error this project
#: keeps naming. ABSENCE MEANS `many`, because that is what every predicate on disk is
#: today and narrowing one silently would refuse facts that are already stored.
CARDINALITIES = frozenset({"one", "many"})
DEFAULT_CARDINALITY = "many"

#: 「this type / this source is no longer used」. The predicate has said it since the
#: grammar existed; an entity and a source could only be DELETED, which also deletes the
#: history that points at them. Same two words, same shape, so an operator learns it
#: once. ABSENCE MEANS `active`.
LIFECYCLE_STATES = frozenset({"active", "retired"})
DEFAULT_LIFECYCLE = "active"


def is_retired(item: Any) -> bool:
    """Whether this declaration has said 「stop reading me」 (S-177 ①).

    🔴 ONE SPELLING, because the answer gates FOUR different passes -- source content,
    cross-relation columns, the compile registries and the plan -- and a second spelling
    is how one of them keeps validating what the other three have stopped reading.
    """
    return (isinstance(item, Mapping)
            and item.get("status", DEFAULT_LIFECYCLE) == "retired")
_SOURCE_UNITS = frozenset({"row", "group"})
_MAPPER_UNITS = frozenset({"event", "row", "group_by"})
# A source whose table carries no world time declares that instead of naming a column.
# Closed on purpose: an open string here would let a typo become a silent claim about time.
_OCCURRED_AT_BASES = frozenset({"ingested"})


class LedgerSetupValidationError(validation.DeclarationValidationError):
    """One stable validation issue with its exact authoring path.

    ⚠️ THE BODY MOVED, THE NAME DID NOT (판정 300). It is a SUBCLASS of the neutral error so
    its sixteen callers keep catching what they caught, and so a caller that catches
    `validation.DeclarationValidationError` also sees it."""


#: The catalogue's relation kinds. A CLOSED list — see the refusal at `_validate_catalog`,
#: which exists because `"veiw"` would otherwise read as `table` and plant `row_id` back on
#: a view, looking exactly like the line had never been written.
CATALOG_KINDS = ("table", "view")

#: What a relation that says nothing IS. Absent means an ordinary table — that is the
#: catalogue's own default, not an invention at the reading site.
DEFAULT_CATALOG_KIND = "table"


def catalog_kind(entry):
    """A catalogue entry's kind, defaulted in ONE place (S-187).

    🔴 FOUR SITES SPELLED THIS OUT SEPARATELY — the validator here, the dynamic model
    builder, the grid's write door and a script — each as `str(x.get("kind") or "table")`.
    Four spellings of one default is four chances for one of them to drift, and the drift
    would be invisible: a relation read as a table where it should be a view is exactly the
    failure `_validate_catalog` refuses a typo to prevent.

    ⚠️ IT DOES NOT VALIDATE. An unknown word is refused at load time, by path, where the
    operator can be told which line is wrong; answering that question again here would be
    a second gate that can disagree with the first.
    """
    return str((entry or {}).get("kind") or DEFAULT_CATALOG_KIND)


def load_physical_catalog(path: str | Path) -> Mapping[str, Any]:
    """`table_config.json` as the relation shape the cross-validators read.

    🔴 THE PATH IS REQUIRED, AND THIS MODULE DOES NOT KNOW WHERE DATA LIVES.
    Resolving it would mean importing `paths`, and this module's contract is that it
    imports no runtime at all -- a contract with a test behind it
    (`test_common_module_has_no_domain_source_branches_or_runtime_imports`).  "Which data
    root am I" is a deployment question and an isolated stack must answer it differently
    from production, so it is answered one level up, in `ledger.setup`.

    The translation, and why each rule is the rule:

    * ``columns``       <- ``column_types``.  Same fact, other spelling.
    * ``composite_key`` <- ``composite_key_source``.  That list IS the row identity: it is
      the tuple `crud.assemble_composite_business_key` joins to build `business_key_val`,
      so covering it is exactly what makes an ordering unique.
    * ``business_key``  <- ``business_key``, GATED ON IT BEING A DECLARED COLUMN.
      That membership test, and NOT the `composite_key_source` gate
      `chain_bindings.identity_column` applies, is the right gate for THIS question --
      worth stating because the two rules look interchangeable.  That one asks "which
      column carries the job" and must refuse an assembled CELL key; this one asks "which
      tuples are unique", and an assembled key MATERIALIZED into its own column is
      unique, so ordering by it is provably an ordering by identity.  A table declaring
      both -- and three relations in the live catalog do declare both -- therefore keeps
      both.  A `business_key` naming something that is not a column of the relation
      certifies nothing and is dropped.

    ⚠️ `map_key_columns` is NOT translated into a key.  It is a lookup prefix -- one map
    holds many rows -- and admitting it here would certify a NON-unique ordering as a
    cursor, which is the one direction that loses events.

    A missing or unreadable catalog is a NAMED refusal, never an empty catalog.  An empty
    catalog would refuse every source with `unknown_relation`, which points the operator at
    the wrong file to fix.
    """
    catalog_path = Path(path)
    if not catalog_path.is_file():
        raise LedgerSetupValidationError(
            "physical_catalog_absent", PHYSICAL_CATALOG_FILENAME,
            f"the ledger reads the physical schema from {catalog_path}, which does not "
            f"exist")
    try:
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LedgerSetupValidationError(
            "physical_catalog_unreadable", PHYSICAL_CATALOG_FILENAME,
            f"{catalog_path} could not be read as JSON: {exc}") from exc
    if not isinstance(document, Mapping):
        raise LedgerSetupValidationError(
            "physical_catalog_unreadable", PHYSICAL_CATALOG_FILENAME,
            f"{catalog_path} must hold a JSON object of table declarations")
    return _adapt_physical_catalog(document)


#: The keys that tell an ADAPTED entry from the raw file it was adapted FROM.
#:
#: ⚠️ `business_key` IS NOT ONE OF THEM, though the adapter emits it: the raw document
#: carries that key under the SAME NAME, so it is evidence of nothing. Measured - the first
#: version of this guard listed it and the raw catalogue sailed through, because the first
#: entry it looked at had a `business_key`. A discriminator has to be a key only ONE of the
#: two shapes can have.
ADAPTED_CATALOG_KEYS = frozenset({"columns", "composite_key"})


def refuse_unadapted_catalog(catalog: Any, where: str = "catalog") -> None:
    """Refuse a catalogue that never went through the adapter, BY NAME (S-86).

    🔴 A WRONG INPUT THAT PRODUCES A PLAUSIBLE ANSWER IS WORSE THAN ONE THAT RAISES. This
    parameter took a raw `table_config.json` document without a word and the validators
    then read `column_types` as if it were `columns` - finding none, and reporting
    「column 'x' is not in EventFrame schema」 about a perfectly good declaration. That
    sentence is TRUE of what it was given and false about the world, which is the hardest
    kind of wrong to chase: it sent one lane to invent a defect (S-85) out of a caller's
    mistake, and it sent me to the same place today.

    ⚠️ THE REFUSAL NAMES THE FUNCTION THAT FIXES IT. 「that is not the right shape」 leaves
    the caller looking for a shape; `load_physical_catalog()` is the whole answer, so it is
    in the sentence.

    ⛔ SHAPE, NOT CONTENT. An adapted catalogue that happens to be EMPTY is a legitimate
    answer (a deployment declaring no tables), so emptiness is not the test - the test is
    whether the entries look like the adapter's output or like the file it reads.
    """
    if catalog is None:
        return
    if not isinstance(catalog, Mapping):
        raise LedgerSetupValidationError(
            "unadapted_physical_catalog", where,
            f"catalog must be the mapping `load_physical_catalog()` returns, not "
            f"{type(catalog).__name__}")
    for table_id, entry in catalog.items():
        if not isinstance(entry, Mapping):
            raise LedgerSetupValidationError(
                "unadapted_physical_catalog", f"{where}.{table_id}",
                "entry must be an object; pass the mapping `load_physical_catalog()` "
                "returns rather than a raw catalogue file")
        if ADAPTED_CATALOG_KEYS & set(entry):
            return
        # The tell of the RAW file: the adapter's input spellings, none of its output's.
        if {"column_types", "composite_key_source", "display_columns"} & set(entry):
            raw_keys = sorted(set(entry) & {"column_types", "composite_key_source",
                                            "display_columns"})
            raise LedgerSetupValidationError(
                "unadapted_physical_catalog", f"{where}.{table_id}",
                f"this is a raw table_config document, not an adapted catalogue: "
                f"{table_id!r} carries {raw_keys} and none of "
                f"{sorted(ADAPTED_CATALOG_KEYS)}. Pass `load_physical_catalog(<path>)` - "
                f"without it the cross-validators read no columns at all and refuse good "
                f"declarations with 「column ... is not in EventFrame schema」")
        raise LedgerSetupValidationError(
            "unadapted_physical_catalog", f"{where}.{table_id}",
            f"entry carries none of {sorted(ADAPTED_CATALOG_KEYS)}; pass the mapping "
            f"`load_physical_catalog()` returns")


def _adapt_physical_catalog(document: Mapping[str, Any]) -> Mapping[str, Any]:
    catalog: dict[str, dict[str, Any]] = {}
    for table_id, declared in document.items():
        if str(table_id).startswith("__") or not isinstance(declared, Mapping):
            continue
        columns = declared.get("column_types")
        if not isinstance(columns, Mapping) or not columns:
            continue
        relation: dict[str, Any] = {
            "columns": {str(name): str(value) for name, value in columns.items()},
        }
        composite = declared.get("composite_key_source")
        if isinstance(composite, list) and composite:
            relation["composite_key"] = [str(column) for column in composite]
        # The consumers (`_table_has_unique_key`, `_columns_cover_declared_unique_key`)
        # read unique indexes to decide whether an ordering can resume deterministically.
        # `table_config.json` may declare extra ones per table, and they pass through here.
        indexes = declared.get("indexes")
        if isinstance(indexes, list) and indexes:
            relation["indexes"] = [dict(item) for item in indexes
                                   if isinstance(item, Mapping)]
        # 🔴 `row_id` IS THE PRIMARY KEY OF EVERY INGESTED TABLE, AND THE CATALOG DID NOT
        # SAY SO.  Measured 2026-08-21: 26 of 26 tables carry `PRIMARY KEY (row_id)` in
        # PostgreSQL, and 0 of 26 declared it here -- so the two consumers above were
        # permanently-empty branches and no source could name ANY resumable cursor whose
        # ordering the catalog would accept.
        # Declaring it per table would be 26 copies of one sentence, which is the shape
        # this config has spent the day deleting; the invariant belongs to the loader.
        # It is added rather than replaced so a table that also declares its own unique
        # index keeps it.
        #
        # ⚠️ THE COLUMN IS ADDED TOO, AND THAT IS NOT A CONVENIENCE.  `column_types` names
        # the BUSINESS columns; `row_id` is the ingestion framework's own identity and 0 of
        # 26 tables list it.  A first version of this guarded on `"row_id" in columns` and
        # was therefore dead on every table -- a permanently-false branch, which is the
        # exact defect this block exists to remove.  Declaring the column is what makes the
        # index nameable: a cursor may only cite columns the catalog admits.
        # 🔴 A VIEW IS NOT AN INGESTED TABLE, so the invariant above is not its (판정 138).
        # It has whatever columns its SELECT lists, and planting `row_id` there turned four
        # sources' reads into `UndefinedColumn` on the cursor path, on rescope and on the
        # index backfill at once. For a view `column_types` is the WHOLE truth: five of the
        # ten here pass their base table's `row_id` through and say so, five do not.
        # ⛔ A CLOSED LIST, REFUSED BY PATH. `"veiw"` would otherwise read as `table` and
        # plant `row_id` back on the view -- the typo would look exactly like not having
        # written the line at all, which is the one failure mode this field has.
        kind = catalog_kind(declared)
        if kind not in ("table", "view"):
            raise LedgerSetupValidationError(
                "invalid_catalog", f"{table_id}.kind",
                f"kind must be 'table' or 'view', not {declared.get('kind')!r}")
        if kind != "view":
            relation["columns"].setdefault("row_id", "string")
        # ⚠️ THE INDEX FOLLOWS THE COLUMN, NOT THE KIND. Wherever `row_id` is present it is
        # unique -- that is what the column IS -- and a view passing it through passes its
        # uniqueness with it. Measured when the two were not split: `dt_transfer` orders by
        # `row_id` on a view and was refused with "ordering must include every column of a
        # catalog-declared ... UNIQUE index". Splitting them is what keeps the operator's
        # job to two lines.
        if "row_id" in relation["columns"]:
            relation.setdefault("indexes", []).append(
                {"columns": ["row_id"], "unique": True})
        # 🔴 THE UNIT A JUDGEMENT IS MADE ON, and it is a property of the TABLE (ruling
        # 151, placed here 2026-09-09). It is not always the row and not always the
        # business key: a value may be recorded per slot while the decision it feeds is
        # made per (lot, slot), and nothing in the grammar could say so -- which is how a
        # subset view came to fill a row whose key was already complete.
        #
        # ⛔ NO DEFAULT. A wrong judgement unit is a wrong answer that LOOKS right, so a
        # reader that needs one and does not find it must refuse by name rather than
        # assume the row. Nothing reads it yet: this builds the place, not the reader.
        #
        # ⚠️ REFUSED BY PATH, LIKE `kind` IS. A column that is not declared, a repeat, or
        # a blank would each read as "the operator meant something" while selecting
        # nothing -- the permanently-false filter this file already carries a note about.
        if "decision_key" in declared:
            columns = declared.get("decision_key")
            if not isinstance(columns, list) or not columns:
                raise LedgerSetupValidationError(
                    "invalid_catalog", f"{table_id}.decision_key",
                    "decision_key must be a non-empty list of declared column names")
            seen = []
            for column in columns:
                if not isinstance(column, str) or not column.strip():
                    raise LedgerSetupValidationError(
                        "invalid_catalog", f"{table_id}.decision_key",
                        "every decision_key entry must be a non-blank column name")
                if column in seen:
                    raise LedgerSetupValidationError(
                        "invalid_catalog", f"{table_id}.decision_key",
                        f"column {column!r} is named twice")
                if column not in relation["columns"]:
                    raise LedgerSetupValidationError(
                        "invalid_catalog", f"{table_id}.decision_key",
                        f"column {column!r} is not declared on {table_id!r}")
                seen.append(column)
            relation["decision_key"] = list(columns)
        business_key = declared.get("business_key")
        if (isinstance(business_key, str) and business_key.strip()
                and business_key in relation["columns"]):
            relation["business_key"] = business_key
        catalog[str(table_id)] = relation
    return catalog


@dataclass(frozen=True)
class LedgerSetupBundle:
    """Immutable normalized logical bundle; mappings are recursively read-only."""

    _data: Mapping[str, Any]

    @property
    def setup_version(self) -> int:
        return int(self._data["setup_version"])

    def section(self, name: str) -> Mapping[str, Any]:
        if name not in ALL_SECTIONS:
            raise KeyError(name)
        return self._data[name]

    def to_mapping(self) -> dict[str, Any]:
        return _thaw(self._data)

    def serialize(self) -> str:
        return json.dumps(
            self.to_mapping(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False)


class _DuplicateKey(ValueError):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


class _InvalidJsonConstant(ValueError):
    pass


# A refusal that names the fault without naming the ACTION reads as "unknown error" to the
# operator who hits it, and the operator who hits this one is on the production box holding
# a config that was correct yesterday.  So a retired field says three things: what happened,
# where the truth lives now, and that nothing has to be copied across.
_RETIRED_FIELD_HELP = {
    "ledger_config.tables": (
        "field is not allowed - the 'tables' section retired on 2026-08-18. "
        "Physical schema is declared once, in server/config/table_config.json, and the "
        "ledger reads it from there. Delete this section; do NOT copy its contents "
        "anywhere. If a relation it named is missing from table_config.json, declare the "
        "relation there - this setup will then name that relation on its own."
    ),
}


#: How many declared names a refusal will list before it stops.  A message nobody reads to
#: the end helps nobody; the close-match branch below is the one that usually answers.
#: 🔴 RE-EXPORTS, NOT COPIES (판정 300). The bodies live in `validation.py` so S-188's chain
#: loader refuses with the SAME language; these names stay because this module's callers and
#: its own thousand lines already spell them. The idiom is the one `main.py` uses for
#: `reload_local_process_cache` — an assignment, so it is the same object.
CANDIDATE_LIMIT = validation.CANDIDATE_LIMIT
_CANDIDATE_LIMIT = validation.CANDIDATE_LIMIT
_path = validation.path_of
_allowed_note = validation.allowed_note
_did_you_mean = validation.did_you_mean


def _Problems() -> validation.Problems:
    """This module's `Problems`, carrying the THREE things the shared class does not know:
    the ledger's exception, the ledger's retired authoring paths, and — the one that matters
    — the ledger's prohibition on cells that name code. A chain rule names a mapper on
    purpose, so that set cannot be the shared default."""
    return validation.Problems(
        error_cls=LedgerSetupValidationError,
        retired_help=_RETIRED_FIELD_HELP,
        forbidden_keys=_FORBIDDEN_DECLARATION_KEYS)

def public_bundle_schema() -> dict[str, Any]:
    """Small public contract; no runtime registry or implementation details."""
    return {
        "setup_version": SETUP_VERSION,
        "config_file": CONFIG_FILENAME,
        "logical_fields": ["setup_version", *LOGICAL_SECTIONS],
        "optional_fields": list(OPTIONAL_SECTIONS),
        # Where the physical half of the setup is authored.  Published so a screen can
        # SAY which file to open instead of leaving the operator to discover that
        # `tables` is no longer here.
        "physical_schema_file": PHYSICAL_CATALOG_FILENAME,
        "binding_kinds": ["column", "constant", "entity"],
        # 🔴 THE SAME LIST MINUS THE ONE THE VALIDATOR REFUSES THERE. `_validate_binding`
        # already answers `invalid_binding` for an `entity` binding used as an entity's
        # IDENTITY KEY ("entity identity keys allow only column or constant bindings"), so
        # a form that offers all three at that square recommends a value that can only be
        # refused. This is not a second rule -- it is the first one, said where the screen
        # can read it; `test_identity_keys_are_not_offered_an_entity.py` measures the two
        # against each other by feeding every kind to the validator rather than trusting
        # this literal.
        "identity_binding_kinds": ["column", "constant"],
        # 🔴 THE WORDS THE CELL ACCEPTS, from the tuple the validator judges with
        # (S-144). Written here so the authoring form OFFERS them rather than
        # inviting free text into a closed set -- the same reason
        # `identity_binding_kinds` sits above, and read from the constant so the
        # form and the refusal cannot name different words.
        "attribute_cardinalities": list(ATTRIBUTE_CARDINALITIES),
        # `tables` joins the list: naming it here is what turns "I pasted my old section
        # back in" from a silent no-op into `unknown_field` at `ledger_config.tables`.
        # `source_preparers` and `mappers` join it for the same reason on 2026-08-20 --
        # they retired into the source, and every config written before that day
        # still has them.  `profiles` joins them the same evening.  (Where inside the
        # source they landed changed once more on 2026-08-21: `driver` split into
        # `read`/`prepare`/`map` and the profile body became `bind`.)  `packs` joins the
        # list later the same day for the same reason: every config written before it went
        # still carries one, and a pasted-back section must say so by name.
        "forbidden_sections": ["frames", "lookups", "positions",
                               "manifest", "chains", "enrichments", "tables",
                               "source_preparers", "mappers", "profiles", "packs"],
    }


def role_binding_kinds(role: Mapping[str, Any]) -> tuple[str, ...]:
    """Resolve one validated Role's effective binding kinds from the Role contract."""
    if not isinstance(role, Mapping):
        raise TypeError("role must be a mapping")
    declared = role.get("allowed_binding_kinds")
    if _is_list(declared):
        return tuple(declared)
    return _default_binding_kinds(role.get("kind"))


#: The two Roles every predicate has, whatever it says about its object, and the one Role
#: an object contributes.  They are CONSTANTS because the vocabulary does not name them:
#: `subjects` says which entity TYPES may fill the subject, never what the slot is called,
#: so a per-predicate spelling would be a free choice with nothing to check it against.
SUBJECT_ROLE = "subject"
OCCURRED_AT_ROLE = "occurred_at"
TARGET_ROLE = "target"
VALUE_ROLE = "value"

#: `object.kind` -> the Role kind that carries the object, for the ONE kind that carries
#: one in a Role rather than in an entity reference and does not depend on a declared type.
_OBJECT_VALUE_ROLE_KINDS = {"event_ref": "identity"}

#: A `value` object's declared type -> the Role kind that carries it (S-84, 판정 249).
#:
#: 🔴 THIS USED TO BE THE CONSTANT `quantity`, and that is the defect: the grammar and the
#: authoring form accepted `string`/`boolean`/`timestamp` while the compiler pinned every
#: value object to a number, so a source declaring one of them had EVERY atom refused as
#: an invalid quantity. The type the declaration states is now the type the Role carries.
#:
#: ⛔ `string` IS `attribute` AND NOT `symbolic`, and that is not a naming preference.
#: `roleframe`'s scalar branch carries an extra condition for `symbolic` alone - the value
#: must be in `role.allowed_values` - and NOTHING writes `allowed_values`. Its own comment
#: says so and says what follows: the day the first half becomes reachable with the second
#: still empty, every symbolic value is refused. Mapping `string` here is exactly that day,
#: so it maps to the neighbouring kind that shares the branch and adds no condition.
#: `boolean` joins it because `_scalar` already admits bools.
#:
#: ⚠️ AN UNKNOWN TYPE IS STILL NOT DEFAULTED HERE. A silent fallback to a wrong kind is
#: how a value lands as something the Role validator then refuses, which is the defect this
#: whole item is about.
_VALUE_TYPE_ROLE_KINDS = {
    "number": "quantity",
    "string": "attribute",
    "boolean": "attribute",
    # ⚠️ `time` CARRIES A REQUIREMENT THE OTHERS DO NOT: the Role validator wants a
    # timezone-aware datetime, so a `timestamp` value's binding must declare a `timezone`
    # and the validator refuses one that does not. That refusal is the whole reason this
    # type could join the emittable set at all.
    "timestamp": "time",
}


def predicate_claim(predicate_id: str, predicate: Any,
                    entities: Any = None) -> dict[str, Any]:
    """The Roles and the emission ONE predicate forces -- the Claim, with nobody to say it.

    🔴 THIS FUNCTION IS WHAT `packs` USED TO BE (owner, 2026-08-21: 「packs 도 아예 삭제
    가능하네. claims 도 필요없고. 그냥 맵퍼가 say 한 문장 id 에 vocab 만 달아주면 되는 거
    아님?」).  Measured before removing the section: of the five predicates in the live
    config, ZERO were used with two different Role sets, every qualifier name in a Claim's
    `roles` matched its predicate's `object.qualifiers` character for character, and five
    of six `emit` clauses were `$subject`/`$occurred_at` verbatim.  The sixth spelled its
    endpoints `$child`/`$parent`, which is why the same round renamed them: a Claim that
    only restates its predicate is a copy, and a copy that MAY differ is a defect waiting
    for the day someone edits one side.

    Returns the shape `packs.<pack>.claims.<claim>` had, so the compiler, the validator and
    the authoring plan all read one derivation instead of three agreeing ones.

    Tolerant of a half-written predicate on purpose: `config_authoring` runs this over
    bundles that do not validate yet, and a screen that raises tells an author nothing.
    """
    obj = predicate.get("object") if isinstance(predicate, Mapping) else None
    obj = obj if isinstance(obj, Mapping) else {}
    object_kind = obj.get("kind")
    qualifiers = obj.get("qualifiers") if isinstance(obj.get("qualifiers"), Mapping) else {}
    required_qualifiers = _column_values(qualifiers.get("required"))
    optional_qualifiers = list(_column_values(qualifiers.get("optional")))

    # 🔴 A SENTENCE WITH NO OBJECT IS A STATEMENT ABOUT ITS SUBJECT, so it carries the
    # values that subject declares (S-52, ruling 130 ②). Written structurally - "object
    # kind is `none`" - and NEVER as a predicate name: a domain word here would decide the
    # rule for one vocabulary and be wrong for the next declaration, which is the thing
    # this repository forbids in as many words.
    #
    # This is why an operator adds NOTHING for an attribute: naming it on the entity and
    # binding it once on the source is the whole of it. Without this the name would have
    # to be written a third time, into the predicate's own qualifier list.
    #
    # ⚠️ `entities` widens this function's input from the predicate to the predicate AND
    # the entity section, and that is CORRECT rather than tolerated: a declaration that
    # gives an entity a new attribute IS a different declaration, and a snapshot hash that
    # did not move for it would be saying the two are the same.
    if object_kind == "none" and isinstance(entities, Mapping):
        declared = []
        for subject_type in _column_values(predicate.get("subjects")
                                           if isinstance(predicate, Mapping) else None):
            descriptor = entities.get(subject_type)
            if isinstance(descriptor, Mapping):
                declared.extend(_column_values(descriptor.get("attributes")))
        for name in declared:
            if name not in optional_qualifiers and name not in required_qualifiers:
                optional_qualifiers.append(name)

    roles: dict[str, Any] = {
        SUBJECT_ROLE: {"kind": "entity", "required": True},
        OCCURRED_AT_ROLE: {"kind": "time", "required": True},
    }
    emit_object: dict[str, Any] = {"kind": object_kind}
    if object_kind == "entity_ref":
        roles[TARGET_ROLE] = {"kind": "entity", "required": True}
        emit_object["entity"] = f"${TARGET_ROLE}"
    elif object_kind == "value":
        # Tolerant of a half-written predicate, like the rest of this function: an
        # undeclared type means `number`, which is what every declaration on disk means,
        # and a type this cannot honour falls back to it as well rather than raising -
        # the VALIDATOR is what tells an author that word is not emittable yet, and it
        # says so with a number (S-84).
        declared = obj.get("value_type") or DEFAULT_VALUE_TYPE
        roles[VALUE_ROLE] = {
            "kind": _VALUE_TYPE_ROLE_KINDS.get(declared,
                                               _VALUE_TYPE_ROLE_KINDS[DEFAULT_VALUE_TYPE]),
            "required": True}
        emit_object["value"] = f"${VALUE_ROLE}"
    elif object_kind in _OBJECT_VALUE_ROLE_KINDS:
        roles[VALUE_ROLE] = {
            "kind": _OBJECT_VALUE_ROLE_KINDS[object_kind], "required": True}
        emit_object["value"] = f"${VALUE_ROLE}"
    # An object-less sentence carries qualifiers too, WHEN THERE ARE ANY. Empty stays
    # absent so a vocabulary that declares none emits exactly the bytes it did before.
    if object_kind != "none" or required_qualifiers or optional_qualifiers:
        emit_object["qualifiers"] = {
            **{name: f"${name}" for name in required_qualifiers},
            **{name: f"${name}?" for name in optional_qualifiers},
        }
    for name in required_qualifiers:
        roles[name] = {"kind": "attribute", "required": True}
    for name in optional_qualifiers:
        roles.setdefault(name, {"kind": "attribute", "required": False})
    return {
        "roles": roles,
        "emit": {
            "predicate": predicate_id,
            "subject": f"${SUBJECT_ROLE}",
            "object": emit_object,
            "occurred_at": f"${OCCURRED_AT_ROLE}",
        },
    }


def _derived_cursor(value: Mapping[str, Any]) -> dict[str, Any]:
    """Write each source's `read.cursor` from its `read.order_by`, in the bundle.

    🔴 THE QUESTION LEFT THE FORM; THE VALUE DID NOT LEAVE THE DOCUMENT.  Everything
    downstream reads `driver.cursor_columns` -- `setup_registry` compiles it,
    `backfill` sorts the page by it and stores the watermark from it, `runtime_v2`
    checks a cursor tuple against it, `source_preparation` requires those columns to
    survive preparation.  None of them changes: the bundle they are handed still carries
    `read.cursor.columns`, it is just no longer something a person types.

    🔴 IT OVERWRITES RATHER THAN FILLING A GAP, AND THAT IS THE POINT.  A watermark says
    how far a read got; it can only be expressed in the order the read ran, so a cursor
    that differs from `order_by` is not a second opinion, it is a page boundary the reader
    cannot honour.  Filling only the absent ones would leave exactly those declarations
    alive AND unchecked, because the validator no longer looks at the key at all.

    ⚠️ MEASURED BEFORE WRITING THIS: of the three source declarations on disk, the two in
    the live config already declare a cursor character-for-character equal to their
    `order_by`; one tracked sample declares a two-column cursor against a one-column
    `order_by`, and that sample is the only place this changes a value.
    """
    sources = value.get("sources")
    if not isinstance(sources, Mapping):
        return dict(value)
    rebuilt: dict[str, Any] = {}
    for source_id, source in sources.items():
        read = source.get("read") if isinstance(source, Mapping) else None
        if not isinstance(read, Mapping) or not _is_list(read.get("order_by")):
            rebuilt[source_id] = source
            continue
        rebuilt[source_id] = {
            **source,
            "read": {**read, "cursor": {"columns": list(read["order_by"])}},
        }
    return {**value, "sources": rebuilt}


def validate_bundle(value: Mapping[str, Any], *,
                    catalog: Mapping[str, Any] | None = None) -> LedgerSetupBundle:
    issues = validate_bundle_errors(value, catalog=catalog)
    if issues:
        raise issues[0]
    filled = {name: {} for name in OPTIONAL_SECTIONS if name not in value} | dict(value)
    normalized = _normalize(_derived_cursor(filled))
    return LedgerSetupBundle(_freeze(normalized))


def validate_bundle_errors(value: Mapping[str, Any], *,
                           catalog: Mapping[str, Any] | None = None
                           ) -> tuple[LedgerSetupValidationError, ...]:
    """Every structural and cross-section issue in one pass.

    `catalog` is the physical relation shape from `table_config.json`, and it is
    REQUIRED -- omitting it refuses by name rather than defaulting.  Two reasons, and the
    second is the one that cost something:

    * A default would make this function read a file off disk, and this module's whole
      job is to be the pure authoring boundary.
    * A silently-defaulted catalog is how a bundle comes to be validated against one
      world and compiled against another.  When the answer to "does this column exist"
      can come from a source the caller did not name, nobody can tell which answer they
      got.  The refusal names the fix.

    It is a parameter for the same reason `trusted_implementations()` and
    `verified_joins` are parameters on `compile_setup_snapshot`: the caller states which
    world it is judging against.  Production resolves it once, in `ledger.setup`.
    """
    problems = _Problems()
    if catalog is None:
        return (LedgerSetupValidationError(
            "physical_catalog_required", PHYSICAL_CATALOG_FILENAME,
            f"validation needs the physical relation shape; pass "
            f"catalog=ledger.setup.live_physical_catalog() or an explicit "
            f"load_physical_catalog(<path to {PHYSICAL_CATALOG_FILENAME}>)"),)
    # 🔴 AND THE SHAPE, NOT ONLY THE PRESENCE (S-86). `catalog is None` has refused by name
    # since it cost something; a catalogue that is PRESENT but never went through the
    # adapter was accepted in silence, and the cross-validators below then found no columns
    # and refused good declarations with 「column ... is not in EventFrame schema」. That
    # sentence is true of what they were given and false about the world - the shape a loud
    # axis takes when it is standing in front of a quiet one.
    refuse_unadapted_catalog(catalog)
    if not problems.exact(
            value, "bundle", required=("setup_version", *LOGICAL_SECTIONS),
            optional=OPTIONAL_SECTIONS):
        return problems.finish()
    if value.get("setup_version") != SETUP_VERSION:
        problems.add(
            "unsupported_setup_version", "bundle.setup_version",
            f"supported setup_version is {SETUP_VERSION}")
    for section in ALL_SECTIONS:
        if section in value and not isinstance(value[section], Mapping):
            problems.add("invalid_type", f"bundle.{section}", "must be an object")
    # An omitted optional section is the same bundle as an empty one, resolved ONCE here
    # so every reader below -- and the compiler after it -- sees one shape. Leaving the
    # key absent for later code to `.get()` around is how two readers come to disagree
    # about whether "no joins" and "no joins section" are the same thing.
    value = {name: {} for name in OPTIONAL_SECTIONS if name not in value} | dict(value)

    if isinstance(value.get("virtual_joins"), Mapping):
        _validate_virtual_joins(value["virtual_joins"], problems)
    if isinstance(value.get("vocabulary"), Mapping):
        _validate_vocabulary(value["vocabulary"], problems)
    if isinstance(value.get("entities"), Mapping):
        _validate_entities(value["entities"], problems)
    if isinstance(value.get("sources"), Mapping):
        _validate_sources(value["sources"], problems)

    # Cross-validation only consumes structurally sound descriptors.  This makes every
    # malformed JSON shape a stable validation result instead of an AttributeError or
    # TypeError from a later semantic lookup.
    if problems.items:
        return problems.finish()
    if all(isinstance(value.get(name), Mapping) for name in ALL_SECTIONS):
        _cross_validate(value, catalog, problems)
    return problems.finish()


def bundle_readiness_errors(bundle: LedgerSetupBundle
                            ) -> tuple[LedgerSetupValidationError, ...]:
    """Structurally valid is not the same as ready to run -- and today nothing separates them.

    🔴 THIS PASS HAS NO RULES LEFT.  Its one rule was `approval_status == "approved"`, and
    that field retired on 2026-08-21 for holding one value on all 40 live bindings.  The
    stage is kept because three callers (`setup.load`, `setup_registry.snapshot_compile_
    errors`, `config_drafts.compile_draft_preview`) place it BETWEEN structural validation
    and compilation, and that position is the thing worth keeping: the next rule that is
    about "may this run" rather than "is this well formed" belongs here and nowhere else.
    Retiring the stage itself is a separate ruling with seven call sites; it is not this one.
    """
    if not isinstance(bundle, LedgerSetupBundle):
        raise TypeError("readiness requires a validated LedgerSetupBundle")
    return _Problems().finish()


def require_ready_bundle(bundle: LedgerSetupBundle) -> LedgerSetupBundle:
    issues = bundle_readiness_errors(bundle)
    if issues:
        raise issues[0]
    return bundle


def load_setup_bundle(root: str | Path, *, config_name: str = CONFIG_FILENAME,
                      catalog: Mapping[str, Any] | None = None
                      ) -> LedgerSetupBundle:
    """Load the ONE authoring file under ``root``.

    This replaced a manifest naming five files across three directories.  The manifest
    existed to enumerate them; with one file there is nothing to enumerate, and
    `setup_version` alone states the grammar generation that five `schema_version` fields
    used to state five times.

    🔴 THE "NO OTHER JSON" REFUSAL IS THE SINGLE-FILE PROMISE, NOT TIDINESS.
    The old loader refused a JSON file the manifest did not list, so a stray file could
    never be silently half-read.  The same refusal is what now makes "open one file and you
    have seen everything" true: a leftover `catalog/tables.json` beside the new file would
    otherwise sit there looking authoritative while nothing read it.  A converted root that
    still contains the originals is therefore refused BY NAME, which is exactly the state
    the converter leaves behind on purpose.

    ⚠️ "ONE FILE" IS ABOUT THE SEMANTIC SETUP, NOT THE PHYSICAL SCHEMA.  The physical half
    is `table_config.json`, which sits in the config root -- OUTSIDE this directory, and so
    outside the refusal above -- because ingestion, the chain workers and the grid author
    it too.  It is not a second setup file to keep in step; it is the file the ledger
    stopped copying.  `catalog` overrides which one is read; see `validate_bundle_errors`.
    """
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise LedgerSetupValidationError(
            "invalid_config_root", "config_root", "must be a directory")
    config_path = _resolve_config_path(
        root_path, config_name, "config_root", require_json=True)
    extras = sorted(
        path.resolve() for path in root_path.rglob("*.json")
        if path.resolve() != config_path)
    if extras:
        relative = extras[0].relative_to(root_path).as_posix()
        # 🔴 The "move it outside" clause is not politeness. `rglob` RECURSES, so keeping
        # the retired files in a backup folder INSIDE the root still trips this -- and
        # keeping the originals beside the new file is exactly what a careful operator
        # does. Without the clause the message says what tripped but not what to do, so
        # the refusal lands hardest on the most cautious reader. Measured: this is how it
        # first fired in practice.
        raise LedgerSetupValidationError(
            "unlisted_config_file", f"config_root.{relative}",
            f"the setup is one file ({config_name}); this root also contains "
            f"{relative!r} — move it outside the config root")

    document = _read_json(config_path, "ledger_config")
    issues = _root_document_errors(document)
    if issues:
        raise issues[0]
    return validate_bundle(document, catalog=catalog)


def _root_document_errors(document: Mapping[str, Any]
                          ) -> tuple[LedgerSetupValidationError, ...]:
    problems = _Problems()
    if problems.exact(
            document, "ledger_config",
            required=("setup_version", *LOGICAL_SECTIONS),
            optional=OPTIONAL_SECTIONS):
        if document.get("setup_version") != SETUP_VERSION:
            problems.add(
                "unsupported_setup_version", "ledger_config.setup_version",
                f"supported setup_version is {SETUP_VERSION}")
    return problems.finish()


def setup_bundle_errors(root: str | Path, *, config_name: str = CONFIG_FILENAME,
                        catalog: Mapping[str, Any] | None = None
                        ) -> tuple[LedgerSetupValidationError, ...]:
    """EVERY problem in one root, for the AUTHORING path.

    🔴 THIS IS NOT A REPLACEMENT FOR `load_setup_bundle`, AND THE TWO MUST NOT BE MERGED.
    A source about to write atoms should still stop at the first refusal -- there is no
    value in enumerating faults in a config that is about to be refused anyway, and every
    later check would be reading a bundle the earlier one already declared broken.  It is
    AUTHORING that needs the whole list: measured 2026-08-19, an author hand-writing a
    second source spent five save-and-run cycles discovering five problems that were all
    present in the first save.

    Everything here is read-only and nothing is compiled: the file is read, the root shape
    is checked, and the cross-section validator -- which already returns a list -- is asked
    for all of it.  I/O-shaped refusals (unreadable file, invalid JSON, a stray second JSON
    file) still RAISE, because there is no second problem to find in a file that could not
    be parsed.
    """
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise LedgerSetupValidationError(
            "invalid_config_root", "config_root", "must be a directory")
    config_path = _resolve_config_path(
        root_path, config_name, "config_root", require_json=True)
    document = _read_json(config_path, "ledger_config")
    root_issues = _root_document_errors(document)
    if root_issues:
        # The section-level validator would read sections this one just called absent or
        # misspelled, and report a second wave of consequences rather than causes.
        return root_issues
    return validate_bundle_errors(document, catalog=catalog)


def _resolve_config_path(root: Path, relative: Any, path: str, *, require_json: bool) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "must be a non-blank relative path")
    if relative != relative.strip() or "\\" in relative or any(c in relative for c in "*?[]"):
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "must be a canonical relative path without glob syntax")
    candidate = Path(relative)
    if candidate.is_absolute() or ":" in relative or any(part in ("", ".", "..")
                                                          for part in candidate.parts):
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "path must stay below the config root")
    if require_json and candidate.suffix.lower() != ".json":
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "config path must end in .json")
    try:
        resolved = (root / candidate).resolve(strict=True)
    except FileNotFoundError as exc:
        raise LedgerSetupValidationError("missing_config_file", path,
                                         f"file {relative!r} does not exist") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "resolved path escapes config root") from exc
    if not resolved.is_file():
        raise LedgerSetupValidationError("missing_config_file", path,
                                         "config path must name a file")
    return resolved


def _versioned_id(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not _VERSIONED_ID.fullmatch(value):
        problems.add("invalid_versioned_id", path, "must use nonblank-id@positive-version")


def _role_ref(value: Any, path: str, problems: _Problems, *, optional: bool = False) -> None:
    if not isinstance(value, str) or not value.startswith("$"):
        problems.add("invalid_role_ref", path, "must be a $role reference")
        return
    body = value[1:]
    if body.endswith("?"):
        body = body[:-1]
    elif optional:
        problems.add("invalid_role_ref", path, "optional qualifier must use $role?")
    if not body or any(char.isspace() for char in body):
        problems.add("invalid_role_ref", path, "role reference must not be blank")


def _nonblank_id(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        problems.add("invalid_id", path, "ID must be a non-blank trimmed string")


def _deterministic_json(value: Any, path: str, problems: _Problems) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            if not isinstance(key, str):
                problems.add("invalid_binding", path,
                             "constant object keys must be strings")
                return
            _deterministic_json(value[key], f"{path}.{key}", problems)
        return
    if _is_list(value):
        for index, item in enumerate(value):
            _deterministic_json(item, f"{path}[{index}]", problems)
        return
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        try:
            json.dumps(value, allow_nan=False)
        except ValueError:
            problems.add("invalid_binding", path,
                         "constant must be finite deterministic JSON")
        return
    problems.add("invalid_binding", path, "constant must be deterministic JSON")


def _nonblank_text(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not value.strip():
        problems.add("blank_value", path, "must be a non-blank string")


def _occurred_at_origin(occurred: Mapping, path: str, problems: _Problems) -> None:
    """A source says WHERE its time came from - a world column, or an admitted basis.

    Before this, every source had to name a column. A table with no time column could only
    be declared by pointing at something that is not a time, or by pinning a constant into
    the profile - both of which produce atoms that READ as world time and cannot be told
    apart afterwards. Declaring the absence is the honest form, so exactly one of the two
    must be present: naming both would leave the reader guessing which one won.
    """
    has_column = "column" in occurred
    has_basis = "basis" in occurred
    if has_column == has_basis:
        both = "both" if has_column else "neither"
        problems.add(
            "invalid_driver", path,
            f"declare exactly one of 'column' (the table carries world time) or 'basis' "
            f"(it does not - one of {sorted(_OCCURRED_AT_BASES)}); {both} was declared")
        return
    if has_column:
        _nonblank_text(occurred.get("column"), f"{path}.column", problems)
        return
    basis = occurred.get("basis")
    if not isinstance(basis, str) or basis not in _OCCURRED_AT_BASES:
        problems.add(
            "invalid_driver", f"{path}.basis",
            f"must be one of {sorted(_OCCURRED_AT_BASES)}, got {basis!r}")


def _nonblank_list(value: Any, path: str, problems: _Problems,
                   *, allow_empty: bool = False, item_form: str | None = None) -> None:
    """`item_form` is the item's SPELLING, for lists whose items are references.

    "must be a list with at least one item" tells an author the container is wrong and
    leaves them to guess the contents.  Optional because most lists here are plain names
    and have nothing extra to say.
    """
    if not _is_list(value) or (not value and not allow_empty):
        problems.add("invalid_type", path,
                     "must be a list" + ("" if allow_empty else " with at least one item")
                     + (f"; each item is {item_form}" if item_form else ""))
        return
    for index, item in enumerate(value):
        _nonblank_text(item, f"{path}[{index}]", problems)
    if _has_duplicate_strings(value):
        problems.add("duplicate_id", path, "list values must be unique")


def _column_list_or_text(value: Any, path: str, problems: _Problems) -> None:
    if isinstance(value, str):
        _nonblank_text(value, path, problems)
    else:
        _nonblank_list(value, path, problems)


#: How many values one attribute name holds for one subject (S-144 / A1-2, 판정 327).
#: 🔴 ABSENT MEANS `one`, which is what every declaration on disk means today - so the word
#: is only written where it changes something, and 「declared single」 never has to be
#: distinguished from 「never classified」 because for this cell they are the same answer.
ATTRIBUTE_CARDINALITY_ONE = "one"
ATTRIBUTE_CARDINALITY_MANY = "many"
ATTRIBUTE_CARDINALITIES = (ATTRIBUTE_CARDINALITY_ONE, ATTRIBUTE_CARDINALITY_MANY)
DEFAULT_ATTRIBUTE_CARDINALITY = ATTRIBUTE_CARDINALITY_ONE


def _column_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if _is_list(value):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _has_duplicate_strings(value: Any) -> bool:
    strings = _column_values(value)
    return len(strings) != len(set(strings))


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))

def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if _is_list(value):
        return [_normalize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value {value!r} is not deterministic JSON")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_virtual_joins(section: Mapping[str, Any], problems: _Problems) -> None:
    for rule_id in sorted(section, key=str):
        path = f"bundle.virtual_joins.{rule_id}"
        _nonblank_id(rule_id, path, problems)
        rule = section[rule_id]
        # 🔴 [판정 481 · 446] `materialize` IS REQUIRED HERE, NOT MERELY ALLOWED.
        # 판정 446 changed what the field's ABSENCE means: it used to be a default and it
        # now means 「read-time join」, which is retired. This validator was left on the old
        # meaning and refused the field outright, so a bundle join could pass NEITHER seat -
        # omit it and the join loader refuses the declaration, write it and this refused the
        # key. Mirroring 446 rather than just permitting the name is what keeps the two from
        # drifting apart again: there is one answer to 「is this join declared correctly」.
        #
        # `max_rewrite_rows` is OPTIONAL here on purpose. It is a ceiling, not a switch, and
        # the loader is the seat that knows whether a ceiling is required for the shape it
        # sees; requiring it in two places would be two answers to one question.
        if not problems.exact(
                rule, path,
                required=("left_table", "right_table", "join_key", "expose",
                          "join_cardinality", "enabled", "materialize"),
                optional=("fold", "max_rewrite_rows")):
            continue
        # 🔴 AND THE SENTENCE IS 446's, IMPORTED. 「field is required」 would send an operator
        # to add a key; the truth is that a capability was retired and the join has to MOVE
        # (판정 474: the same judgement spelled two ways points at opposite repairs).
        if rule.get("materialize") is not True:
            problems.add("invalid_join", f"{path}.materialize",
                         validation.READ_TIME_RETIRED_DETAIL)
        # ⚠️ SHAPE ONLY. Whether a ceiling is REQUIRED, and whether the one written is the
        # right size, is the join loader's judgement and stays there - asking it twice would
        # be two answers to one question. What this seat owes is that a DECLARED ceiling is
        # a number: an optional field with no shape check is a node whose mutation produces
        # no error, which `test_every_json_node_shape_mutation_returns_only_structured_errors`
        # exists to catch, and it caught this one.
        cap = rule.get("max_rewrite_rows")
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
            problems.add("invalid_join", f"{path}.max_rewrite_rows",
                         "must be a positive integer")
        for field in ("left_table", "right_table"):
            _nonblank_text(rule.get(field), f"{path}.{field}", problems)
        pairs = rule.get("join_key")
        if not _is_list(pairs) or not pairs:
            problems.add("invalid_join", f"{path}.join_key", "must be a non-empty list")
        else:
            for index, pair in enumerate(pairs):
                ppath = f"{path}.join_key[{index}]"
                if problems.exact(pair, ppath, required=("left", "right")):
                    _nonblank_text(pair.get("left"), f"{ppath}.left", problems)
                    _nonblank_text(pair.get("right"), f"{ppath}.right", problems)
        _nonblank_list(rule.get("expose"), f"{path}.expose", problems)
        if rule.get("join_cardinality") != "one":
            problems.add(
                "invalid_join", f"{path}.join_cardinality",
                "Ledger v2 requires join_cardinality 'one'")
        if not isinstance(rule.get("enabled"), bool):
            problems.add("invalid_type", f"{path}.enabled", "must be boolean")
        if "fold" in rule:
            _validate_join_fold(rule.get("fold"), f"{path}.fold", problems)


def _validate_join_fold(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_join", path, "must be an object of notation rule toggles")
        return
    _scan_unsafe_keys(value, path, problems)
    for name in sorted(value, key=str):
        rule_path = f"{path}.{name}"
        if str(name).lower() in _FORBIDDEN_EXECUTABLE_KEYS:
            continue
        if name not in _JOIN_FOLD_RULES:
            problems.add(
                "invalid_join", rule_path,
                f"unknown notation rule {name!r}; known rules are "
                f"{sorted(_JOIN_FOLD_RULES)}")
            continue
        enabled = value[name]
        if not isinstance(enabled, bool):
            problems.add("invalid_type", rule_path, "notation rule toggle must be boolean")
        elif enabled and name not in _IMPLEMENTED_JOIN_FOLD_RULES:
            problems.add(
                "invalid_join", rule_path,
                f"notation rule {name!r} is not implemented")


def _validate_vocabulary(section: Mapping[str, Any], problems: _Problems) -> None:
    for predicate_id in sorted(section, key=str):
        path = f"bundle.vocabulary.{predicate_id}"
        _versioned_id(predicate_id, path, problems)
        item = section[predicate_id]
        #: 🗄️ `continues` LEFT THIS TUPLE ON 2026-08-30, WITH THE CLEANUP IT WAS WAITING FOR.
        #: It said the walk stays on the same material across a predicate, so a step over it
        #: spent the material budget rather than the hop budget. The entity `class` replaced
        #: it on 2026-08-29 -- measured, the class rule reaches everything the flag reached
        #: and more -- and the tolerance stayed only because the live declaration still
        #: carried six of them and refusing those would have stopped the server reading the
        #: declaration at all. `36802e42` removed the six from the live file and the shipped
        #: sample; measured after, both carry ZERO and only `config/backup/**` snapshots
        #: still have them. So the field is refused again, which is what keeps a retired
        #: word from quietly reading as a live rule.
        if not problems.exact(
                item, path, required=("status", "subjects", "object"),
                optional=("cardinality", "absence_confirmed_by")):
            continue
        status = item.get("status")
        if not isinstance(status, str) or status not in LIFECYCLE_STATES:
            problems.add("invalid_predicate", f"{path}.status",
                         f"must be one of {sorted(LIFECYCLE_STATES)}")
        cardinality = item.get("cardinality", DEFAULT_CARDINALITY)
        if not isinstance(cardinality, str) or cardinality not in CARDINALITIES:
            problems.add("invalid_predicate", f"{path}.cardinality",
                         f"must be one of {sorted(CARDINALITIES)} (absent means {DEFAULT_CARDINALITY!r})")
        # 🔴 「이 술어가 «안 보이는» 것이 무슨 뜻인가」 (S-147-a / 판정 333). A1 has this
        # sub-axis for node keys -- `allow_null` says whether an absent key is 「원자 없음」 or
        # 「null 목적어」 -- and A2 had no counterpart at all.
        #
        # 🔴 THE VALUE IS ANOTHER PREDICATE'S NAME, not a self-contained word, and that is
        # forced rather than chosen: 「안 봤다」 and 「보고 없었다」 are separated by THE
        # EXISTENCE OF A DIFFERENT ATOM. No `absence: none|unknown` flag can say that, because
        # the fact lives outside this predicate.
        #
        # ⚠️ WHICH PREDICATE IS AN EXAMINATION IS A DOMAIN FACT, so it is declared. Code that
        # knew `inspected` by name would break 「코드에 도메인 낱말이 «없다»」, and the next
        # installation spells it something else.
        #
        # ⛔ A TYPO IS REFUSED, NEVER SWALLOWED. An unresolvable name would make the
        # denominator read 0 without a word said -- 「봤는데 없음」 counted as 「안 봤음」 -- and
        # that is a wrong number rather than a missing one.
        if "absence_confirmed_by" in item:
            confirmer = item["absence_confirmed_by"]
            where = f"{path}.absence_confirmed_by"
            if not isinstance(confirmer, str) or not confirmer.strip():
                problems.add("invalid_predicate", where,
                             "must be the id of a declared predicate")
            elif confirmer == predicate_id:
                # A predicate cannot confirm its own absence: if it is missing, so is the
                # evidence that it was looked for.
                problems.add("invalid_predicate", where,
                             "a predicate cannot confirm its own absence")
            elif confirmer not in section:
                problems.add(
                    "unknown_id", where,
                    f"{confirmer!r} is not a declared predicate; declared: "
                    f"{sorted(section)}")
            elif (section[confirmer] or {}).get("status") == "retired":
                # The same word `status` already carries, rather than a second retirement rule.
                problems.add("invalid_predicate", where,
                             f"{confirmer!r} is retired, so its presence cannot confirm "
                             f"anything about today's absences")
        _nonblank_list(item.get("subjects"), f"{path}.subjects", problems)
        obj = item.get("object")
        if problems.exact(
                obj, f"{path}.object", required=("kind", "qualifiers"),
                optional=("types", "value_type")):
            kind = obj.get("kind")
            if not isinstance(kind, str) or kind not in OBJECT_KINDS:
                problems.add("invalid_predicate", f"{path}.object.kind",
                             f"must be one of {sorted(OBJECT_KINDS)}")
            if kind == "entity_ref":
                if "types" not in obj:
                    problems.add("missing_field", f"{path}.object.types",
                                 "entity_ref object requires types")
                else:
                    _nonblank_list(obj["types"], f"{path}.object.types", problems)
            elif "types" in obj:
                problems.add("invalid_predicate", f"{path}.object.types",
                             f"{kind!r} object must not declare entity types")
            if "value_type" in obj:
                # ⚠️ SCORED THE SAME WAY `types` IS. A field that is meaningful for one
                # object kind and merely ignored on the others is a place an author can
                # write a sentence nothing reads -- which is exactly the ③′ class this
                # round exists to stop creating.
                if kind != "value":
                    problems.add("invalid_predicate", f"{path}.object.value_type",
                                 f"{kind!r} object must not declare a value type")
                elif (not isinstance(obj["value_type"], str)
                      or obj["value_type"] not in VALUE_TYPES):
                    problems.add("invalid_predicate", f"{path}.object.value_type",
                                 f"must be one of {sorted(VALUE_TYPES)} (absent means {DEFAULT_VALUE_TYPE!r})")
                elif obj["value_type"] not in EMITTABLE_VALUE_TYPES:
                    problems.add(
                        "unsupported_value_type", f"{path}.object.value_type",
                        f"{obj['value_type']!r} can be declared but the emitter does "
                        f"not read it yet, so every atom built from it would be "
                        f"refused (S-84). Until then the emittable set is "
                        f"{sorted(EMITTABLE_VALUE_TYPES)}.")
            qualifiers = obj.get("qualifiers")
            qpath = f"{path}.object.qualifiers"
            if problems.exact(
                    qualifiers, qpath, required=("required", "optional")):
                required = qualifiers.get("required")
                optional = qualifiers.get("optional")
                _nonblank_list(required, f"{qpath}.required", problems, allow_empty=True)
                _nonblank_list(optional, f"{qpath}.optional", problems, allow_empty=True)
                overlap = sorted(set(_column_values(required)) &
                                 set(_column_values(optional)))
                if overlap:
                    problems.add(
                        "invalid_predicate", qpath,
                        f"qualifier names must not be both required and optional: {overlap!r}")
                if (kind == "none"
                        and (_column_values(required) or _column_values(optional))):
                    problems.add(
                        "invalid_predicate", qpath,
                        "none object cannot declare payload qualifiers")


def _validate_entities(section: Mapping[str, Any], problems: _Problems) -> None:
    for entity_id in sorted(section, key=str):
        path = f"bundle.entities.{entity_id}"
        _versioned_id(entity_id, path, problems)
        item = section[entity_id]
        #: `class` says whether this entity is a THING THAT HAPPENS or a NAME THINGS POINT
        #: AT. Owner ruling 2026-08-29 reviving `ONTOLOGY_GRAPH_SPEC` §7.5c: a walk may
        #: reach a static node but must not leave one, because a name every instance points
        #: at is a hub - measured, `defect_kind` has 103,841 atoms and exactly ONE distinct
        #: object, so stepping out of it reaches the whole ledger and the answer drowns.
        #:
        #: OPTIONAL, AND ABSENCE MEANS `dynamic`. Not written into declarations that do not
        #: use it, for the reason `continues` is not: a field read as a default when missing
        #: must stay missing, or "declared dynamic" and "never classified" stop being
        #: distinguishable.
        #: `attributes` are the values a node carries that are NOT its identity - a
        #: wafer's product, a lot's state. Until 2026-09-08 a declaration had nowhere to
        #: put them, so the walk's table could only show what an EDGE happened to carry
        #: as a qualifier, and a predicate with no qualifiers produced a node with no
        #: columns at all. The principle is untouched - a predicate is still an edge -
        #: and what changed is that a node may hold its own values.
        #:
        #: 🔴 OPTIONAL, AND NOT AN IDENTITY. Two atoms differing only in an attribute are
        #: the SAME entity; `keys` alone decide that, here and in the compiler.
        if not problems.exact(
                item, path, required=("keys",),
                optional=("allow_null", "references", "class",
                          "attributes", "attribute_cardinality", "status")):
            continue
        if "class" in item and item["class"] not in ("static", "dynamic"):
            problems.add("invalid_entity_ref", f"{path}.class",
                         "must be static or dynamic")
        # 🔴 THE SAME TWO WORDS THE PREDICATE USES. Retiring a type used to mean DELETING
        # its declaration, which also removes the name every stored atom points at -- the
        # 「투영은 지워도 기록은 안 된다」 line, applied to the grammar. Optional, because
        # every declaration on disk predates it and means `active`.
        entity_status = item.get("status", DEFAULT_LIFECYCLE)
        if not isinstance(entity_status, str) or entity_status not in LIFECYCLE_STATES:
            problems.add("invalid_entity_ref", f"{path}.status",
                         f"must be one of {sorted(LIFECYCLE_STATES)} (absent means {DEFAULT_LIFECYCLE!r})")
        keys = item.get("keys")
        _nonblank_list(keys, f"{path}.keys", problems)
        if _has_duplicate_strings(keys):
            problems.add("duplicate_id", f"{path}.keys", "identity keys must be unique")
        # ⚰️ `key_types` IS RETIRED (판정 165 A1-3, 2026-09-09). It let an author declare
        # each identity key's TYPE and no layer ever read it -- measured: `.key_types` has
        # zero consumers in `server/`. A declaration slot with no reader is not a contract,
        # it is a copy, and the two relevant standing rules say to delete rather than to
        # build a reader: 「착지는 배선이 아니다」 and 「닿을 수 없으면 선언도 닿지 않는다 --
        # 자유도 0 인 선언은 계약이 아니라 사본」.
        #
        # ⚠️ WHAT WOULD HAVE READ IT, had a reader been built: a domain check, an ordering,
        # a range query. None of those exists, and table B's seed resolution -- the one
        # place that looked like a candidate -- was measured and does not use a key's type.
        if "attributes" in item:
            attributes = item["attributes"]
            _nonblank_list(attributes, f"{path}.attributes", problems)
            if _has_duplicate_strings(attributes):
                problems.add("duplicate_id", f"{path}.attributes",
                             "attribute names must be unique")
            # 🔴 AN ATTRIBUTE MAY NOT WEAR A KEY'S NAME. One name would then mean identity
            # in one place and a carried value in another, and the compiler's "keys decide
            # sameness" would read as false to anyone holding the declaration.
            if _is_list(attributes) and _is_list(keys):
                collide = sorted(set(_column_values(attributes))
                                 & set(_column_values(keys)))
                if collide:
                    problems.add(
                        "duplicate_id", f"{path}.attributes",
                        f"these names are already identity keys: {collide}. An attribute "
                        f"is not part of what makes this entity the same entity, so one "
                        f"name cannot be both.")
        # 🔴 「이 이름은 값을 «여럿» 든다」 (S-144 / A1-2, 판정 327). A column holds one value
        # per ROW, so a subject with two products is two rows and two registrations - and
        # the walk read that as a DISAGREEMENT, counted it in `attribute_conflicts` and
        # dropped one of the two values. There was nowhere to say the two are both true.
        #
        # ⚠️ THE SHAPE `key_types` HAD, WITH THE READER `key_types` NEVER HAD. That cell was
        # retired (판정 165) for being a declaration slot nothing consumed; this one is read
        # by the walk in the same commit that declares it, which is the whole difference.
        #
        # 🔴 A NAME THAT IS NOT AN ATTRIBUTE IS REFUSED, NOT IGNORED. `_column_values` drops
        # non-strings silently, so a cell in the wrong shape disappears without a word - and
        # an operator who typed `prodcut` here would get no plurality and no error either.
        if "attribute_cardinality" in item:
            cardinality = item["attribute_cardinality"]
            if not isinstance(cardinality, Mapping):
                problems.add("invalid_type", f"{path}.attribute_cardinality",
                             "must be an object mapping an attribute name to "
                             f"one of {list(ATTRIBUTE_CARDINALITIES)}")
            else:
                declared_attributes = set(_column_values(item.get("attributes")))
                for attribute_name in sorted(cardinality, key=str):
                    where = f"{path}.attribute_cardinality.{attribute_name}"
                    if cardinality[attribute_name] not in ATTRIBUTE_CARDINALITIES:
                        problems.add(
                            "invalid_entity_ref", where,
                            f"must be one of {list(ATTRIBUTE_CARDINALITIES)} "
                            f"(absent means {DEFAULT_ATTRIBUTE_CARDINALITY!r})")
                    if str(attribute_name) not in declared_attributes:
                        problems.add(
                            "unknown_id", where,
                            f"{attribute_name!r} is not in this entity's `attributes`. "
                            f"Cardinality says how many values a DECLARED attribute holds; "
                            f"a name only written here would carry no values at all.")
        if "allow_null" in item and not isinstance(item["allow_null"], bool):
            problems.add("invalid_type", f"{path}.allow_null", "must be boolean")
        # 🔴 THE SAME RULE AS A RETIRED SOURCE (S-177 ①). `references` is the ONE entity
        # clause whose truth depends on something OUTSIDE this entity -- it names another
        # declaration, which an operator is free to delete once nothing active points at
        # it. Every other clause here (`keys`, `attributes`, `class`) is a statement about
        # this entity alone and stays judged, because the walk still SHOWS a retired type
        # and reads those. An active predicate naming a retired type is refused as before,
        # by name, in `_retired_entity_types` -- that rule is untouched.
        if "references" in item and not is_retired(item):
            _validate_references(item["references"], f"{path}.references",
                                 keys, section, problems)


def _validate_references(value, path, own_keys, section, problems):
    """「이 엔티티의 키 하나가 «다른 엔티티»를 가리킨다」 -- the walk composes an edge from it.

    🔴 A REFERENCE IS NOT A MAPPING, AND THE WORDS SAY SO. A mapping writes an atom and is
    spelled `subject`/`predicate`/`target`; a reference composes an edge no atom backs, and is
    spelled `from`/`edge`/`to`. Reusing the mapping words would promise a reader that the
    predicate's atoms can be found. They cannot.

    🔴 EVERY UNKNOWN FIELD IS REFUSED, and so is every key name the entity does not have. A
    typo here does not fail loudly at run time -- it composes no edge, and the screen shows
    that as 「닿는 곳이 없다」, which is indistinguishable from an honest absence. The refusal is
    what keeps those two apart.

    `to.keys` is PLURAL because a container can need more than one key to be named (a lot slot
    is (lot, slot)), spelled `{target key: binding}` exactly as `bind.….keys` is, so the file
    reads one way throughout. A binding is `{"key": <own key>}` or `{"value": <const>}`, and a
    bare string is shorthand for the first.
    """
    if not _is_list(value) or not value:
        problems.add("invalid_type", path, "must be a list with at least one item")
        return
    own = set(_column_values(own_keys)) if _is_list(own_keys) else set()
    for index, ref in enumerate(value):
        here = f"{path}[{index}]"
        if not problems.exact(ref, here, required=("edge", "to"), optional=("from",)):
            continue
        edge = ref.get("edge")
        if not isinstance(edge, str) or not edge.strip() or edge != edge.strip():
            problems.add("invalid_type", f"{here}.edge",
                         "edge name must be a non-blank trimmed string")
        source = ref.get("from")
        if source is not None and problems.exact(
                source, f"{here}.from", required=(), optional=("when",)):
            when = source.get("when")
            if when is not None:
                if not isinstance(when, Mapping) or not when:
                    problems.add("invalid_type", f"{here}.from.when",
                                 "must be a non-empty object")
                else:
                    for name in sorted(when, key=str):
                        if own and name not in own:
                            problems.add(
                                "invalid_entity_ref", f"{here}.from.when.{name}",
                                "condition must name one of this entity's identity keys")
        target = ref.get("to")
        if not problems.exact(target, f"{here}.to", required=("entity", "keys")):
            continue
        entity = target.get("entity")
        if not isinstance(entity, str) or entity not in section:
            problems.add("invalid_entity_ref", f"{here}.to.entity",
                         "must name a declared entity")
        bindings = target.get("keys")
        if not isinstance(bindings, Mapping) or not bindings:
            problems.add("invalid_type", f"{here}.to.keys", "must be a non-empty object")
            continue
        declared = (section.get(entity) or {}).get("keys") if isinstance(entity, str) else None
        target_keys = set(_column_values(declared)) if _is_list(declared) else set()
        if target_keys and set(bindings) - target_keys:
            problems.add("invalid_entity_ref", f"{here}.to.keys",
                         "keys must name the target entity's identity keys")
        for name in sorted(bindings, key=str):
            binding = bindings[name]
            spot = f"{here}.to.keys.{name}"
            if isinstance(binding, str):
                binding = {"key": binding}
            if not isinstance(binding, Mapping):
                problems.add("invalid_type", spot, "must be an object or a key name")
                continue
            if len(binding) != 1 or not ({"key", "value"} & set(binding)):
                problems.add("invalid_type", spot,
                             "binding takes exactly one of 'key' or 'value'")
                continue
            if "key" in binding:
                source_key = binding["key"]
                if not isinstance(source_key, str) or (own and source_key not in own):
                    problems.add("invalid_entity_ref", f"{spot}.key",
                                 "must name one of this entity's identity keys")


def _validate_exclude_when(value: Any, path: str, problems: _Problems) -> None:
    """`[{"column": <name>, "blank": true}, ...]` - rows this source says are not its own.

    🔴 S-91. The mechanism (`__source_row_excluded`) already existed and only a PREPARER
    CLASS could emit it, so a relation whose early rows leave an identity part blank made
    no atoms at all and the only remedy was to write python. Measured in production
    2026-09-09: 995 rows read, 0 molecules, 995 refused for no identity, because the rows
    that carry one sit later in cursor order.

    A list, and a row matching ANY clause is excluded.

    ⛔ ONE PREDICATE, AND `blank` MUST BE `true`. Value comparisons are not built here:
    nothing today needs them, and a grammar that grows an operator per question is how a
    declaration turns into a query language. `blank: false` is refused rather than read as
    "keep only the blanks" - that is a different feature and it should be asked for by
    name, not arrived at by flipping a flag nobody designed to be flipped.
    """
    if value is None:
        return
    if not isinstance(value, list) or not value:
        problems.add("invalid_type", path,
                     "must be a non-empty list of exclusion conditions")
        return
    for index, clause in enumerate(value):
        spot = f"{path}[{index}]"
        if not problems.exact(clause, spot, required=("column", "blank")):
            continue
        column = clause.get("column")
        if not isinstance(column, str) or not column.strip():
            problems.add("invalid_type", f"{spot}.column",
                         "must name a column of this source's relation")
        if clause.get("blank") is not True:
            problems.add("invalid_type", f"{spot}.blank",
                         "the only supported condition is 'blank': true")


def _validate_preparation(item: Any, path: str, problems: _Problems) -> None:
    """One source's preparer body, at `sources.<id>.prepare`.

    No `_versioned_id` here and no id at all: the declaration is not named any more, it IS
    the source's preparation clause.  `implementation_id`/`implementation_version` stay,
    because the thing that is shared and versioned is the CODE the body selects, never the
    body itself.
    """
    if not problems.exact(
            item, path,
            required=("implementation_id", "implementation_version", "input_columns",
                      "output_columns", "accepts_verified_join_rules",
                      "inherit_virtual_join_rules"),
            # S-91. OPTIONAL, so all 26 shipped sources stay valid without being edited -
            # a source that says nothing here excludes nothing, which is what they all do
            # today.
            optional=("exclude_when",)):
        return
    _validate_exclude_when(item.get("exclude_when"), f"{path}.exclude_when", problems)
    _implementation(item, path, problems)
    _nonblank_list(item.get("input_columns"), f"{path}.input_columns", problems,
                   allow_empty=True)
    _column_types(item.get("output_columns"), f"{path}.output_columns", problems)
    _nonblank_list(item.get("inherit_virtual_join_rules"),
                   f"{path}.inherit_virtual_join_rules", problems, allow_empty=True)
    inputs = set(_column_values(item.get("input_columns")))
    outputs = item.get("output_columns")
    if isinstance(outputs, Mapping):
        for column in sorted(set(outputs) & inputs):
            problems.add(
                "output_column_collision", f"{path}.output_columns.{column}",
                "preparer output must not overwrite an input column")
    if not isinstance(item.get("accepts_verified_join_rules"), bool):
        problems.add("invalid_type", f"{path}.accepts_verified_join_rules",
                     "must be boolean")


def _validate_mapper(item: Any, path: str, problems: _Problems) -> None:
    """One source's mapper body, at `sources.<id>.map`.

    🔴 NO `emits`, AND ITS ABSENCE IS THE POINT (owner, 2026-08-20: 「클레임과 맵퍼 함수는
    완전 별개인데 왜 맵퍼에서 쓸 클레임을 정의함?」 -> 「닿을 수 없다면 선언도 닿으면 안됨」).
    A mapper implementation knows `SentenceShape`, never a `claim`; "which claims can this
    mapper produce" is a question it has no way to answer, and the one declaration that can
    is `bind.mappings.<sentence>.use`.  So the field is not moved, it is gone: `MapperDescriptor.emits`
    is now DERIVED from those same `use` values, which is why the two could never disagree
    and why the rule that compared them is not written here any more.
    """
    if not problems.exact(
            item, path,
            required=("implementation_id", "implementation_version", "unit",
                      "input_columns")):
        return
    _implementation(item, path, problems)
    if problems.exact(
            item.get("unit"), f"{path}.unit", required=("kind",),
            optional=("columns",)):
        kind = item["unit"].get("kind")
        if not isinstance(kind, str) or kind not in _MAPPER_UNITS:
            problems.add("invalid_mapper", f"{path}.unit.kind",
                         f"must be one of {sorted(_MAPPER_UNITS)}")
        columns = item["unit"].get("columns")
        if kind == "group_by":
            if columns is None:
                problems.add(
                    "missing_field", f"{path}.unit.columns",
                    "group_by mapper unit requires columns")
            else:
                _nonblank_list(columns, f"{path}.unit.columns", problems)
                if (_is_list(columns)
                        and isinstance(item.get("input_columns"), list)):
                    missing = sorted(set(_column_values(columns))
                                     - set(_column_values(item["input_columns"])))
                    if missing:
                        problems.add(
                            "invalid_mapper", f"{path}.unit.columns",
                            f"group_by columns must be mapper input columns: {missing}")
        elif columns is not None:
            problems.add(
                "invalid_mapper", f"{path}.unit.columns",
                "unit.columns is only valid for group_by")
    _nonblank_list(item.get("input_columns"), f"{path}.input_columns", problems,
                   allow_empty=True)


def _validate_profile(profile: Any, path: str, problems: _Problems) -> None:
    """One source's bind clause, at `sources.<id>.bind`.

    No `_versioned_id` here and no id at all -- the same retirement `_validate_preparation`
    took earlier the same day.  `source` is gone with the section for a sharper reason than
    tidiness: it was a REPEAT of the key one level up, and `_cross_validate` refused every
    value except that key, so the only thing an author could do with the field was get it
    wrong.

    🔴 `packs` WENT THE SAME WAY on 2026-08-21, for the third time in the same file.  It was
    `sorted(set(...))` of the packs the mappings' `use` names, checked for equality in BOTH
    directions -- an author could not write it better, only wrong.

    🔴 AND `use` BECAME `predicate` THE SAME DAY, when the `packs` SECTION went too.  A
    mapping named a Claim that named a predicate; it names the predicate.  The value is a
    versioned vocabulary id, not a `<pack>/<claim>` pair, so the pattern that parsed one
    left with the section.

    🔴 AND IT STAYS A RECORD WITH ONE FIELD (owner: 「ㅇㅇ 남겨」).  `bind: [...]` would read
    the same today and would have to be unfolded -- with a migration -- the first time
    `bind` carries anything besides `mappings`.

    ⚰️ **THAT DAY IS 2026-09-08 (S-52, ruling 124), AND KEEPING THE RECORD IS WHAT MADE IT
    CHEAP.** `bind` now also carries `entities`, where a source binds an entity type's
    ATTRIBUTES once. It is a sibling of `mappings` rather than a field inside each mapping
    because an attribute belongs to the ENTITY, not to a sentence: bind it per role and a
    type used by K sentences is written K times, which is not a longer declaration but a
    different one - K places to disagree, and the walk's `attribute_conflicts` would then
    be counting a disagreement this schema created. Role level still exists, as an
    OVERRIDE for the one case source level cannot express (see below).
    """
    if not problems.exact(profile, path, required=("mappings",),
                          optional=("entities",)):
        return
    _validate_bind_entities(profile.get("entities"), f"{path}.entities", problems)
    mappings = profile.get("mappings")
    if not isinstance(mappings, Mapping) or not mappings:
        problems.add("invalid_profile", f"{path}.mappings",
                     "must be a non-empty object keyed by sentence")
        return
    for sentence in sorted(mappings, key=str):
        mapping = mappings[sentence]
        mpath = f"{path}.mappings.{sentence}"
        _nonblank_id(sentence, mpath, problems)
        # S-99. OPTIONAL, so every sentence declared today stays valid unedited: a
        # sentence that says nothing here is said for every row, which is what they all do.
        if not problems.exact(mapping, mpath, required=("predicate", "bind"),
                              optional=("when",)):
            continue
        _validate_when(mapping.get("when"), f"{mpath}.when", problems)
        _versioned_id(mapping.get("predicate"), f"{mpath}.predicate", problems)
        bindings = mapping.get("bind")
        if not isinstance(bindings, Mapping) or not bindings:
            problems.add("invalid_profile", f"{mpath}.bind", "must be non-empty")
        else:
            for role in sorted(bindings):
                _nonblank_id(role, f"{mpath}.bind.{role}", problems)
                _validate_binding(bindings[role], f"{mpath}.bind.{role}", problems)


def _entity_key_columns(binding: Any) -> set:
    """The physical columns one ENTITY binding reads for its identity keys."""
    out = set()
    if not isinstance(binding, Mapping) or binding.get("kind") != "entity":
        return out
    keys = binding.get("keys")
    if not isinstance(keys, Mapping):
        return out
    for inner in keys.values():
        if isinstance(inner, Mapping) and inner.get("kind") == "column":
            column = inner.get("column")
            if isinstance(column, str):
                out.add(column)
    return out


def _validate_no_self_edge(profile, path, problems, *, executed: bool) -> None:
    """S-105 ③. An entity-to-entity sentence may not read the same identity at both ends.

    🔴 AVAILABILITY IS NOT MEANING, and this is the half that catches it. The defect
    that prompted this bound a real column - one of the source's own preparer outputs - to
    BOTH the subject and the target, so the sentence said a thing came from itself. Every
    column existed; every type checked; the statement was empty. It reached the shipped
    sample because the mapping was copied from a working one and only the predicate and the
    condition were changed - the part that had to differ for it to MEAN anything was the
    part nobody looked at.

    ⚠️ EQUALITY OF THE WHOLE KEY SET, NOT AN OVERLAP. Two entities of one type may
    legitimately share SOME key column; what cannot be is every key of the subject reading
    the same columns as every key of the target, because then the two ends are one node.

    ⛔ AND A REFLEXIVE PREDICATE WOULD GET A CELL, NOT THIS SILENCE. If a source ever
    needs to say a thing relates to itself, that is a declaration to design rather than a
    shape to permit by leaving this unchecked - nothing declares one today.
    """
    if not executed:
        # 🔴 SCORED ONLY WHERE THE BINDINGS ARE EXECUTED. A source whose role mapper is
        # PYTHON never reads these - they are placeholders the mapper replaces - so scoring
        # them refuses declarations that are correct BECAUSE nobody executes them. Measured
        # 2026-09-09: written without this distinction, the check refused the LIVE setup on
        # a placeholder that had stood harmlessly for weeks.
        #
        # ⚠️ THE SKIP IS ANNOUNCED, and not from here. This module may not import `logging`
        # (its own gate allowlists the imports, which is how that was found), and the ruling
        # asked for a LOADER line anyway: `setup.load_setup` says which sources went
        # unscored, beside the dead-cell sentence it already prints.
        return
    mappings = profile.get("mappings")
    if not isinstance(mappings, Mapping):
        return
    for sentence in sorted(mappings, key=str):
        mapping = mappings[sentence]
        bindings = mapping.get("bind") if isinstance(mapping, Mapping) else None
        if not isinstance(bindings, Mapping):
            continue
        left = _entity_key_columns(bindings.get("subject"))
        right = _entity_key_columns(bindings.get("target"))
        if left and left == right:
            problems.add(
                "invalid_profile", f"{path}.bind.mappings.{sentence}",
                f"subject and target read the same column(s) {sorted(left)!r}, so this "
                f"sentence points an edge at the node it started from")


def _validate_when(value: Any, path: str, problems: _Problems) -> None:
    """`{<column>: <value>, ...}` - the rows for which this sentence is said.

    🔴 S-99. One relation can hold rows that mean DIFFERENT predicates - a single event
    table whose rows say one thing or its opposite - and until now the grammar had nowhere
    to put that condition. The only workaround was a qualifier, which does not answer it:
    `follow` selects by PREDICATE, so both sentences would still be said for every row.

    ⚠️ A ROW THAT DOES NOT MATCH IS NOT REFUSED AND NOT EXCLUDED. It simply does not say
    THIS sentence, and it may still say another - which is what separates this from S-91's
    `exclude_when`, where the row is not the source's at all. The difference shows up as
    the per-sentence atom count of a test run, not as a refusal anywhere.

    ⛔ A MAP, AND EQUALITY ONLY. Same shape as `entities.references[].from.when`, which
    ruling 195 named as the model: keys are ANDed, there is no list, no range, no OR and
    no comparison. One spelling of "condition" in this grammar rather than two.
    """
    if value is None:
        return
    if not isinstance(value, Mapping) or not value:
        problems.add("invalid_type", path,
                     "must be a non-empty object of {column: value}")
        return
    for column in sorted(value, key=str):
        if not isinstance(column, str) or not column.strip():
            problems.add("invalid_type", f"{path}.{column}", "must name a column")
            continue
        if isinstance(value[column], (Mapping, list, tuple)) or value[column] is None:
            problems.add(
                "invalid_type", f"{path}.{column}",
                "must be a single string, number or boolean to compare the column with")


def _validate_binding(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_binding", path, "binding must be an object")
        return
    kind = value.get("kind")
    if kind == "column":
        # 🔴 `timezone` SAYS WHAT A NAIVE READING MEANS (S-84-b, 판정 09-10 13:44). A
        # `timestamp` value's Role must be timezone-aware, and the column usually holds a
        # string; what the compiler cannot know is which zone an unqualified reading is
        # in, because that is a fact about the SOURCE. Optional here and required by the
        # value-type check below, so a column binding that carries no timestamp is
        # unchanged - which is every binding on disk today.
        allowed = ("kind", "column", "timezone")
        required = ("kind", "column")
    elif kind == "constant":
        allowed = ("kind", "value")
        required = ("kind", "value")
    elif kind == "entity":
        allowed = ("kind", "entity_type", "keys", "attributes")
        required = ("kind", "entity_type", "keys")
    else:
        problems.add("invalid_binding", f"{path}.kind",
                     f"unsupported binding kind {kind!r}")
        return
    problems.exact(value, path, required=required,
                   optional=tuple(name for name in allowed if name not in required),
                   ignored=_RETIRED_BINDING_FIELDS)
    if kind == "column":
        _nonblank_text(value.get("column"), f"{path}.column", problems)
        if "timezone" in value:
            _nonblank_text(value.get("timezone"), f"{path}.timezone", problems)
    elif kind == "constant" and "value" in value:
        _deterministic_json(value["value"], f"{path}.value", problems)
    elif kind == "entity":
        _versioned_id(value.get("entity_type"), f"{path}.entity_type", problems)
        keys = value.get("keys")
        if not isinstance(keys, Mapping) or not keys:
            problems.add("invalid_entity_ref", f"{path}.keys", "must be non-empty")
        else:
            for key in sorted(keys):
                _nonblank_id(key, f"{path}.keys.{key}", problems)
                _validate_binding(keys[key], f"{path}.keys.{key}", problems)
                if isinstance(keys[key], Mapping) and keys[key].get("kind") == "entity":
                    problems.add(
                        "invalid_binding", f"{path}.keys.{key}.kind",
                        "entity identity keys allow only column or constant bindings")
        attributes = value.get("attributes")
        if "attributes" in value and not isinstance(attributes, Mapping):
            problems.add("invalid_type", f"{path}.attributes", "must be an object")
        elif isinstance(attributes, Mapping):
            for name in sorted(attributes):
                _nonblank_id(name, f"{path}.attributes.{name}", problems)
                _validate_binding(attributes[name], f"{path}.attributes.{name}", problems)
                if (isinstance(attributes[name], Mapping)
                        and attributes[name].get("kind") == "entity"):
                    # Same rule as an identity key, for the same reason: an entity-valued
                    # attribute is an EDGE wearing a value's clothes, and edges are
                    # predicates. `references` is where a key points at another entity.
                    problems.add(
                        "invalid_binding", f"{path}.attributes.{name}.kind",
                        "entity attributes allow only column or constant bindings")


def _validate_sources(section: Mapping[str, Any], problems: _Problems) -> None:
    """Every source, in the order it RUNS.

    🔴 `driver` NAMED TWO JOBS AT ONCE AND IS GONE (owner, 2026-08-20: 「애초에 지금 컨피그
    스키마가 잘못돼 있는건데」).  Reading a physical batch and turning it into sentences are
    different steps with different column universes, and both sat under one key -- which is
    how the question "where does a preparer go" cost a round the day before.  The four
    clauses now stand as SIBLINGS of `relation`, and the file reads in the order execution
    happens:

        relation   the physical table this source reads.  UNMOVED -- `prepared_columns`
                   starts from it, and moving it would drag that with it for nothing
        read       unit, identity, group_by, order_by, occurred_at, cursor, probe
        prepare    the preparer body, character for character as it was
        map        the mapper body, character for character as it was
        bind       the profile body, character for character as it was

    The file itself is written `sort_keys=True`, so on disk these sit `bind · map · prepare
    · read`.  That is deliberate and is not fixed here: the serialization is canonical hash
    material, and the ORDER A READER SEES is made by the skeleton, which lists them in the
    order above.
    """
    for source_id in sorted(section, key=str):
        path = f"bundle.sources.{source_id}"
        _nonblank_id(source_id, path, problems)
        source = section[source_id]
        if not problems.exact(
                source, path, required=("relation", "read", "prepare", "map", "bind"),
                optional=("status",)):
            continue
        _nonblank_text(source.get("relation"), f"{path}.relation", problems)
        # 🔴 SAME TWO WORDS AGAIN. Retiring a source is deleting it today, and the exact
        # check then refuses every other key -- so a source that has stopped being read
        # cannot be left on record saying so.
        source_status = source.get("status", DEFAULT_LIFECYCLE)
        if not isinstance(source_status, str) or source_status not in LIFECYCLE_STATES:
            problems.add("invalid_driver", f"{path}.status",
                         f"must be one of {sorted(LIFECYCLE_STATES)} (absent means {DEFAULT_LIFECYCLE!r})")
        # ⚰️ `decision_key` IS NOT HERE (ruling, 2026-09-09 08:54). The judgement unit is a
        # property of the TABLE, and the readers that need it -- the virtual join and the
        # enrichment resolver -- read the CATALOG, not this bundle. Declaring it on the
        # ledger source would have made two places for one fact. It lives beside `kind`
        # in the catalog adapter above, and this validator reads it from there if it ever
        # needs to.
        # 🔴 A RETIRED SOURCE IS NOT READ, SO ITS CONTENT IS NOT READ EITHER (S-177 ①,
        # owner 2026-09-11: 「아예 못 읽는 선언은 retired 가 안 먹던데」). Retiring a source
        # means 「this one is no longer read」, and the three clauses below all ask what
        # WOULD BE READ -- which columns the preparer takes, which the profile binds, which
        # mapper turns them into sentences. Judging them anyway made retirement answer a
        # question nobody asked: a source whose relation lost a column REFUSED THE WHOLE
        # BUNDLE, so the ledger stopped on a declaration that had already said it was done.
        #
        # ⚠️ THE SHAPE IS STILL JUDGED, and deliberately: `exact` above has already refused
        # an unknown key and a missing clause, and `relation`/`status` are read below by
        # everything that SHOWS the source. What is skipped is the CONTENT -- and only the
        # content can be falsified by the world moving on, which is the whole defect.
        if is_retired(source):
            continue
        # Each clause is judged on its own: one malformed clause must not silence the
        # other three, or an author fixes four rounds of one refusal at a time.
        _validate_profile(source.get("bind"), f"{path}.bind", problems)
        _validate_preparation(source.get("prepare"), f"{path}.prepare", problems)
        _validate_mapper(source.get("map"), f"{path}.map", problems)
        read = source.get("read")
        # 🔴 `cursor` IS NOT ASKED ANY MORE -- IT WAS THE SAME CONTRACT, ASKED TWICE.
        # `_cross_validate` scored `order_by` and `cursor.columns` in ONE loop under ONE
        # predicate (each must cover a catalog-declared unique key), so the two questions
        # had the same answer set and the operator had nothing to decide between them --
        # owner, 2026-08-21: 「커서 어차피 복붙할건데 왜 적으라 그래?」.  A cursor says how
        # far a read got, which can only be said in the order that read ran, so the value
        # is DERIVED from `order_by` in `validate_bundle` rather than declared.  The name
        # is swallowed here because every config on disk still carries one.
        if not problems.exact(
                read, f"{path}.read",
                required=("unit", "identity", "group_by", "order_by", "occurred_at"),
                optional=("registration_probe",), ignored=("cursor",)):
            continue
        _validate_registration_probe(
            read.get("registration_probe"), f"{path}.read.registration_probe",
            problems)
        source_unit = read.get("unit")
        if not isinstance(source_unit, str) or source_unit not in _SOURCE_UNITS:
            problems.add("invalid_driver", f"{path}.read.unit",
                         f"must be one of {sorted(_SOURCE_UNITS)}")
        for field in ("identity", "group_by", "order_by"):
            _nonblank_list(read.get(field), f"{path}.read.{field}", problems,
                           allow_empty=(field == "group_by"))
        group_by = read.get("group_by")
        identity = read.get("identity")
        if source_unit == "row" and _is_list(group_by) and group_by:
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "row unit requires an empty group_by list")
        if source_unit == "group" and _is_list(group_by) and not group_by:
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "group unit requires at least one group_by column")
        if (_is_list(group_by) and _is_list(identity)
                and any(isinstance(column, str) and column not in identity
                        for column in group_by)):
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "group_by columns must be included in identity")
        occurred = read.get("occurred_at")
        if problems.exact(
                occurred, f"{path}.read.occurred_at",
                required=("timezone",), optional=("column", "basis")):
            _occurred_at_origin(occurred, f"{path}.read.occurred_at", problems)
            timezone = occurred.get("timezone")
            _nonblank_text(timezone, f"{path}.read.occurred_at.timezone", problems)
            if isinstance(timezone, str) and timezone.strip():
                try:
                    ZoneInfo(timezone)
                except ZoneInfoNotFoundError:
                    problems.add("invalid_timezone", f"{path}.read.occurred_at.timezone",
                                 f"unknown timezone {timezone!r}")


def _validate_registration_probe(value: Any, path: str, problems: _Problems) -> None:
    """Which BASE columns can name an entity that might already be registered.

    🔴 WHY THIS IS A DECLARATION AND NOT AN INFERENCE.
    The driver asks the store, once per page, which of this batch's subjects already exist,
    so a `register` atom is emitted only on FIRST sight.  That question is asked BEFORE
    preparation, on physical column names, while the Profile binds POST-preparation logical
    names -- so the answer cannot be read off the bindings.  Until this declaration existed
    the driver hard-coded one source's column names, which is why exactly one source could
    run at all.

    🔴 THE DIRECTION OF ERROR IS NOT SYMMETRIC, AND THAT IS THE WHOLE SAFETY ARGUMENT.
    The probe result is used only to SUPPRESS a register atom for a subject already in the
    store.  Naming a column that contributes no subject is therefore free -- it yields
    candidates no atom mentions, and they match nothing.  MISSING a column is not free: a
    subject that is already registered goes unsuppressed and the batch emits a duplicate
    `register`.  So the declaration must be a SUPERSET of the subjects the atoms can
    mention, and over-declaring is the safe side to err on.

    `list_separator` exists because a column may carry a positional list of ids in one
    string.  Probing for the unsplit string would find none of them -- an
    under-approximation, the unsafe direction.  The retired grammar declared this as
    `list_separator` too; the current one had lost it into a hard-coded separator.
    """
    if value is None:
        return
    if not _is_list(value):
        problems.add("invalid_registration_probe", path, "must be a list")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not problems.exact(
                item, item_path, required=("entity_type", "columns"),
                optional=("list_separator",)):
            continue
        entity_type = item.get("entity_type")
        _versioned_id(entity_type, f"{item_path}.entity_type", problems)
        if isinstance(entity_type, str):
            if entity_type in seen:
                problems.add(
                    "duplicate_registration_probe", f"{item_path}.entity_type",
                    f"entity type {entity_type!r} is probed twice; merge the columns")
            seen.add(entity_type)
        _nonblank_list(item.get("columns"), f"{item_path}.columns", problems)
        if "list_separator" in item:
            separator = item.get("list_separator")
            if not isinstance(separator, str) or not separator:
                problems.add(
                    "invalid_registration_probe", f"{item_path}.list_separator",
                    "must be a non-empty string")


def _cross_registration_probe(value: Any, path: str, relation: Any,
                              physical: set[str], tables: Mapping[str, Any],
                              entities: Mapping[str, Any],
                              problems: _Problems) -> None:
    """The probed entity must exist, be single-keyed, and name real base columns."""
    if not _is_list(value):
        return
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        item_path = f"{path}[{index}]"
        entity_type = item.get("entity_type")
        entity = entities.get(entity_type) if isinstance(entity_type, str) else None
        if entity is None:
            problems.add(
                "unknown_entity_type", f"{item_path}.entity_type",
                f"entity type {entity_type!r} is not declared")
            continue
        keys = entity.get("keys")
        if _is_list(keys) and len(keys) != 1:
            # A composite-key entity needs one column per key part, and guessing which
            # declared column feeds which part is exactly the kind of inference this
            # declaration exists to remove. Refuse rather than probe a partial identity:
            # a partial probe under-approximates, which is the direction that duplicates
            # `register` atoms.
            problems.add(
                "unsupported_registration_probe", f"{item_path}.entity_type",
                f"entity type {entity_type!r} has {len(keys)} identity keys; the probe "
                f"supports single-keyed entities only")
            continue
        if isinstance(relation, str) and _is_list(item.get("columns")) and tables.get(relation):
            for column in item["columns"]:
                if isinstance(column, str) and column not in physical:
                    problems.add(
                        "unknown_column", f"{item_path}.columns",
                        f"{relation!r} has no column {column!r}")


def _cross_validate(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                    problems: _Problems) -> None:
    # The physical half of every cross-check below comes from `table_config.json`, not
    # from the ledger file.  The checks themselves are unchanged: what moved is WHO
    # ANSWERS "does this relation have this column, and is this ordering unique".
    tables = catalog
    entities = bundle["entities"]
    vocabulary = bundle["vocabulary"]
    sources = bundle["sources"]

    _cross_vocabulary(vocabulary, entities, problems)
    # `_cross_packs` stood here and checked a Claim against the predicate it emitted --
    # object kind agreement, every required qualifier present, no qualifier the predicate
    # does not allow, every `$role` endpoint declared with a compatible kind.  Every one of
    # those compared two declarations that `predicate_claim` now derives from ONE, so they
    # are not relaxed: they are unwritable.  The half that survives -- "is this predicate
    # known, and is it active" -- moved into `_cross_profile_contract`, which is where a
    # predicate is now named.
    #
    # The bind contract is a question about the LEDGER FILE alone -- does this predicate
    # exist, does its derived Claim declare this role -- so it is asked for every source,
    # including one whose relation is undeclared and which the loop below skips.
    for source_id, source in sources.items():
        if is_retired(source):
            continue
        profile = source.get("bind")
        if isinstance(profile, Mapping):
            _cross_profile_contract(
                f"bundle.sources.{source_id}.bind", profile, vocabulary, problems,
                entities)

    for rule_id, rule in bundle["virtual_joins"].items():
        path = f"bundle.virtual_joins.{rule_id}"
        _relation_columns(rule.get("left_table"), [p.get("left") for p in rule.get("join_key", [])
                                                   if isinstance(p, Mapping)],
                          tables, f"{path}.left_table", problems)
        right_columns = [p.get("right") for p in rule.get("join_key", [])
                         if isinstance(p, Mapping)] + list(rule.get("expose", [])
                                                           if _is_list(rule.get("expose")) else [])
        _relation_columns(rule.get("right_table"), right_columns, tables,
                          f"{path}.right_table", problems)
        right_keys = [pair["right"] for pair in rule["join_key"]]
        right_table = tables.get(rule["right_table"])
        if (isinstance(right_table, Mapping)
                and not _table_has_unique_key(right_table, right_keys)):
            problems.add(
                "invalid_join", f"{path}.join_key",
                "right join columns require an exact declared UNIQUE key or index")

    # 🔴 THE UNDECLARED RELATION IS THE ROOT REFUSAL, SO IT IS ANSWERED FIRST AND ALONE.
    # Measured while wiring this: with the relation missing from the catalog, the first
    # error an operator saw was `unknown_column` on a MAPPER's `input_columns` -- because
    # `_Problems.finish()` sorted by path and `bundle.mappers.` preceded `bundle.sources.`.
    # (Both bodies now sit UNDER the source, so that particular ordering no longer applies;
    # the skip below is still what keeps the column complaints from burying the root.)
    # Every one of those complaints is downstream of "the table is not declared" and each
    # points at the wrong file to fix.  `ledger_admin.check_source_declaration` already
    # ruled this way for the legacy syntax ("before the column checks, because it is the
    # ROOT refusal"); this is the same rule, not a second one.  Only the affected source
    # is skipped -- an unrelated source keeps being validated.
    # 🔴 A RETIRED SOURCE'S RELATION MAY BE GONE, AND THAT IS NOT A FAULT (S-177 ①). The
    # table a source stopped reading is exactly the table an operator is then free to drop,
    # so asking the catalogue about it turns 「retired」 into 「the bundle will not load」.
    unresolved_sources = {
        source_id for source_id, source in sources.items()
        if not is_retired(source) and source.get("relation") not in tables
    }
    for source_id in sorted(unresolved_sources):
        _relation_columns(sources[source_id].get("relation"), (), tables,
                          f"bundle.sources.{source_id}.relation", problems)

    for source_id, source in sources.items():
        if source_id in unresolved_sources or is_retired(source):
            continue
        path = f"bundle.sources.{source_id}"
        relation = source.get("relation")
        driver = source["read"]
        base_columns = []
        if _is_list(driver.get("order_by")):
            base_columns.extend(driver["order_by"])
        if isinstance(driver.get("occurred_at"), Mapping):
            # A declared basis names no source column - its time comes from the row's own
            # ingestion stamp, which the schema builder puts on every table.
            occurred_column = driver["occurred_at"].get("column")
            if isinstance(occurred_column, str):
                base_columns.append(occurred_column)
        _relation_columns(relation, base_columns, tables, f"{path}.relation", problems)
        physical = set(_table_columns(tables, relation))
        _cross_registration_probe(
            driver.get("registration_probe"), f"{path}.read.registration_probe",
            relation, physical, tables, entities, problems)
        table = tables.get(relation)
        if isinstance(table, Mapping):
            # ONE ordering, scored once.  This was a two-entry loop over `order_by` and
            # `cursor.columns` under a single predicate -- which is the measurement that
            # retired the second declaration: any value satisfying one satisfied the
            # other, so the pair could never disagree about anything the validator asked.
            # The cursor now IS this list (see `_derived_cursor`), so scoring it again
            # would score the same value twice and report one fault as two.
            columns = driver.get("order_by")
            if (_is_list(columns)
                    and not _columns_cover_declared_unique_key(table, columns)):
                problems.add(
                    "invalid_cursor", f"{path}.read.order_by",
                    "ordering must include every column of a catalog-declared "
                    "business_key, composite_key, or UNIQUE index")

        profile = source.get("bind") if isinstance(source.get("bind"), Mapping) else None
        profile_path = f"{path}.bind"

        prep = source.get("prepare") if isinstance(source.get("prepare"), Mapping) else {}
        prep_path = f"{path}.prepare"
        available = set(physical)
        if prep:
            for column in prep.get("input_columns", []):
                if column not in physical:
                    problems.add("unknown_column", f"{prep_path}.input_columns",
                                 f"column {column!r} is not in relation {relation!r}")
            if isinstance(prep.get("output_columns"), Mapping):
                for column in sorted(set(prep["output_columns"]) & physical):
                    problems.add(
                        "output_column_collision",
                        f"{prep_path}.output_columns.{column}",
                        f"preparer output collides with physical relation {relation!r}")
                available.update(prep["output_columns"])
            # S-91. The column has to BE in the relation, and it has to be read by a
            # preparer that looks at it.
            for index, clause in enumerate(prep.get("exclude_when") or []):
                if not isinstance(clause, Mapping):
                    continue
                column = clause.get("column")
                if isinstance(column, str) and column not in physical:
                    problems.add(
                        "unknown_column", f"{prep_path}.exclude_when[{index}].column",
                        f"column {column!r} is not in relation {relation!r}")
            # 🔴 REFUSED BY NAME RATHER THAN IGNORED (판정 194 ㉡). Only the generic
            # `direct-join` preparer reads this clause; a source that declares it under
            # some other implementation would have it silently do nothing, which is the
            # mirror image of the two-paths problem this feature exists to avoid. A
            # preparer class that wants to exclude rows already emits the marker itself.
            if prep.get("exclude_when") and prep.get("implementation_id") != "direct-join":
                problems.add(
                    "invalid_driver", f"{prep_path}.exclude_when",
                    f"only the 'direct-join' preparer reads exclude_when; this source "
                    f"declares {prep.get('implementation_id')!r}, whose implementation "
                    f"emits the row-exclusion marker itself")
            inherited_rules = prep.get("inherit_virtual_join_rules", [])
            if inherited_rules and not prep.get("accepts_verified_join_rules"):
                problems.add(
                    "invalid_driver", f"{prep_path}.accepts_verified_join_rules",
                    "must be true when the source inherits virtual join rules")
        for index, rule_id in enumerate(prep.get("inherit_virtual_join_rules", [])):
            rule = bundle["virtual_joins"].get(rule_id)
            rpath = f"{prep_path}.inherit_virtual_join_rules[{index}]"
            if rule is None:
                problems.add("unknown_join_rule", rpath, f"unknown rule {rule_id!r}")
            elif not rule.get("enabled"):
                problems.add("invalid_driver", rpath, f"join rule {rule_id!r} is disabled")
            elif rule.get("left_table") != relation:
                problems.add("invalid_driver", rpath,
                             f"join rule left_table must be {relation!r}")
            else:
                declared_inputs = set(prep.get("input_columns", []))
                left_keys = {
                    pair.get("left") for pair in rule.get("join_key", [])
                    if isinstance(pair, Mapping)
                }
                missing_inputs = sorted(left_keys - declared_inputs)
                if missing_inputs:
                    problems.add(
                        "invalid_driver", rpath,
                        f"join rule {rule_id!r} left key column(s) {missing_inputs!r} "
                        f"must be declared by {prep_path}.input_columns")

        for field in ("identity", "group_by"):
            for index, column in enumerate(driver.get(field, [])):
                if column not in available:
                    problems.add(
                        "unknown_column", f"{path}.read.{field}[{index}]",
                        f"column {column!r} is not in prepared EventFrame schema")

        mapper = source.get("map") if isinstance(source.get("map"), Mapping) else None
        mapper_path = f"{path}.map"
        if mapper is not None:
            for column in mapper.get("input_columns", []):
                if column not in available:
                    problems.add("unknown_column", f"{mapper_path}.input_columns",
                                 f"column {column!r} is not in EventFrame schema")
            if (mapper.get("unit", {}).get("kind") == "group_by"
                    and not driver.get("group_by")):
                problems.add("invalid_mapper", f"{mapper_path}.unit.kind",
                             "group_by mapper requires source group_by columns")
        if profile is not None:
            # S-99. The column has to exist where the mapper will look for it, which is
            # the PREPARED frame - relation columns plus preparer outputs. That is the set
            # S-91's `exclude_when` is checked against, and ruling 195 asked for the same
            # function rather than a second opinion about what a column is.
            # S-105 ③. Reads nothing but the profile, so it is independent of the
            # `bindable` question and lands ahead of it.
            _mapper = source.get("map") if isinstance(source.get("map"), Mapping) else {}
            _validate_no_self_edge(
                profile, path, problems,
                executed=_mapper.get("implementation_id") == "declarative-role")
            profile_mappings = profile.get("mappings")
            for sentence in sorted(profile_mappings if isinstance(profile_mappings, Mapping)
                                   else {}, key=str):
                mapping = profile_mappings[sentence]
                when = mapping.get("when") if isinstance(mapping, Mapping) else None
                if not isinstance(when, Mapping):
                    continue
                for column in sorted(when, key=str):
                    if isinstance(column, str) and column not in available:
                        problems.add(
                            "unknown_column",
                            f"{path}.bind.mappings.{sentence}.when.{column}",
                            f"column {column!r} is not in prepared EventFrame schema")
            # The EventFrame schema this source's Profile binds against is `available`,
            # which is only known HERE -- so the bind/column half of the Profile contract
            # is asked inside the source loop, while the file-only half was asked above.
            _cross_profile_source(profile_path, profile, entities, vocabulary,
                                  available, problems)
        if profile is not None and isinstance(mapper, Mapping):
            # The two-direction set equality between `map.emits` and these `use` values
            # stood here until 2026-08-21.  It is not relaxed -- it is unwritable: the
            # mapper no longer declares the set, `MapperDescriptor.emits` is compiled FROM
            # these very refs, and a rule comparing a value with its own source states
            # nothing.
            mapper_inputs = set(mapper.get("input_columns", []))
            # 🔴 THE SAME ENUMERATION THE DERIVATION USES. Counting binding columns here
            # and deriving them there is how the two came to disagree about what a mapper
            # must hold.
            for column, column_path in required_mapper_input_columns(
                    mapper, profile, profile_path):
                if column not in mapper_inputs:
                    problems.add(
                        "invalid_mapper", f"{mapper_path}.input_columns",
                        f"Profile column {column!r} at {column_path} is missing")


def _cross_vocabulary(vocabulary: Mapping[str, Any], entities: Mapping[str, Any],
                      problems: _Problems) -> None:
    for predicate_id, predicate in vocabulary.items():
        path = f"bundle.vocabulary.{predicate_id}"
        for index, entity_type in enumerate(predicate["subjects"]):
            if entity_type not in entities:
                problems.add("unknown_entity_type", f"{path}.subjects[{index}]",
                             f"unknown entity type {entity_type!r}"
                             + _did_you_mean(entity_type, entities, "entity types"))
        obj = predicate["object"]
        if obj["kind"] == "entity_ref":
            for index, entity_type in enumerate(obj["types"]):
                if entity_type not in entities:
                    problems.add("unknown_entity_type", f"{path}.object.types[{index}]",
                                 f"unknown entity type {entity_type!r}"
                                 + _did_you_mean(entity_type, entities, "entity types"))


def _validate_bind_entities(section: Any, path: str, problems: _Problems) -> None:
    """`bind.entities.<type>.attributes` - one source, one place per entity type.

    Shape only; whether the NAMES exist on the type is a cross-section question and is
    asked where the rest of the entity references are resolved.
    """
    if section is None:
        return
    if not isinstance(section, Mapping):
        problems.add("invalid_type", path, "must be an object keyed by entity type")
        return
    for entity_type in sorted(section, key=str):
        epath = f"{path}.{entity_type}"
        _versioned_id(entity_type, epath, problems)
        item = section[entity_type]
        if not problems.exact(item, epath, required=("attributes",)):
            continue
        attributes = item.get("attributes")
        if not isinstance(attributes, Mapping) or not attributes:
            problems.add("invalid_binding", f"{epath}.attributes",
                         "must be a non-empty object keyed by attribute name")
            continue
        for name in sorted(attributes):
            _nonblank_id(name, f"{epath}.attributes.{name}", problems)
            _validate_binding(attributes[name], f"{epath}.attributes.{name}", problems)
            if (isinstance(attributes[name], Mapping)
                    and attributes[name].get("kind") == "entity"):
                problems.add(
                    "invalid_binding", f"{epath}.attributes.{name}.kind",
                    "entity attributes allow only column or constant bindings")


def _retired_entity_types(predicate: Mapping[str, Any],
                          entities: Mapping[str, Any]) -> tuple:
    """The entity types this predicate names that the declaration has retired.

    ⚠️ IT ASKS THE PREDICATE, NOT THE BINDING. A binding names a COLUMN; the entity types a
    sentence commits to are the predicate's `subjects` and, when its object is an
    `entity_ref`, that object's `types`. Reading the bindings instead would miss exactly
    the subject - the one every sentence has.

    An entity type that is not declared at all is somebody else's refusal
    (`unknown_entity_type`), so an absent one is passed over here rather than reported
    twice under a word that would send the author to the wrong field.
    """
    if not isinstance(entities, Mapping):
        return ()
    named = list(predicate.get("subjects") or ())
    objects = predicate.get("object")
    if isinstance(objects, Mapping) and objects.get("kind") == "entity_ref":
        named.extend(objects.get("types") or ())
    retired = []
    for entity_id in named:
        item = entities.get(entity_id)
        if isinstance(item, Mapping) and item.get("status", DEFAULT_LIFECYCLE) != "active":
            retired.append(entity_id)
    return tuple(sorted(set(retired)))


def _cross_profile_contract(path: str, profile: Mapping[str, Any],
                            vocabulary: Mapping[str, Any], problems: _Problems,
                            entities: Mapping[str, Any] = None) -> None:
    for sentence, mapping in sorted(profile.get("mappings", {}).items()):
        mpath = f"{path}.mappings.{sentence}"
        predicate_id = mapping.get("predicate")
        predicate = vocabulary.get(predicate_id)
        if predicate is None:
            problems.add("unknown_predicate", f"{mpath}.predicate",
                         f"unknown predicate {predicate_id!r}"
                         + _did_you_mean(predicate_id, vocabulary, "predicates"))
            continue
        if predicate.get("status") != "active":
            problems.add("inactive_predicate", f"{mpath}.predicate",
                         f"predicate {predicate_id!r} is not active")
        # 🔴 AND THE TYPES IT SPEAKS ABOUT (S-103, ruling 198). Retiring an entity type used
        # to be a word nothing read, so every sentence about it went on being said and the
        # ledger went on growing rows for a type the author had declared dead. Named per
        # type rather than as one "something is retired", because a sentence can name
        # several and the author has to know WHICH one to edit.
        for retired in _retired_entity_types(predicate, entities):
            problems.add("inactive_entity_type", f"{mpath}.predicate",
                         f"predicate {predicate_id!r} speaks about entity type "
                         f"{retired!r}, which is retired")
        roles = predicate_claim(predicate_id, predicate, entities)["roles"]
        bindings = mapping["bind"]
        for role in sorted(bindings):
            if role not in roles:
                problems.add("unknown_role", f"{mpath}.bind.{role}",
                             f"role {role!r} is not declared by predicate "
                             f"{predicate_id!r}"
                             + _did_you_mean(role, roles, "roles"))
            if role in roles:
                allowed = role_binding_kinds(roles[role])
                if bindings[role].get("kind") not in allowed:
                    problems.add("invalid_binding", f"{mpath}.bind.{role}.kind",
                                 f"binding kind is not allowed for role {role!r}")
                # 🔴 A `time` ROLE FILLED FROM A COLUMN MUST SAY ITS TIMEZONE (S-84-b).
                # The Role validator wants a timezone-aware datetime and a column usually
                # holds a string; without this the declaration would compile and every
                # atom built from it would then be refused at translation - which is the
                # exact trap 판정 178 narrowed the form to avoid. Refused HERE, where an
                # author can still fix it, and named rather than implied.
                # ⚠️ THE VALUE ROLE ONLY, AND `occurred_at` IS THE REASON THE SCOPE HAS
                # TO BE NAMED. It is a `time` role too, and it already has a timezone -
                # the source declares it on `read.occurred_at`, which is what makes that
                # declaration mean "the timezone of this source's naive values". Its
                # binding's column is documented as ignored ALWAYS. Requiring the field
                # there refused every existing declaration - measured, fifty reds on the
                # first run - so the requirement belongs to the role that has no other
                # place to get one.
                if (role == VALUE_ROLE
                        and roles[role].get("kind") == "time"
                        and bindings[role].get("kind") == "column"
                        and not str(bindings[role].get("timezone") or "").strip()):
                    problems.add(
                        "missing_timezone", f"{mpath}.bind.{role}.timezone",
                        f"role {role!r} carries a timestamp, so its column binding must "
                        f"declare the timezone a naive reading is in - the compiler "
                        f"cannot know it and every atom would be refused without it")
                if (roles[role].get("kind") == "symbolic"
                        and bindings[role].get("kind") == "constant"
                        and bindings[role].get("value") not in
                        # 🔴 The roster is always absent since `packs` left, so this
                        # membership test reads an empty list and this branch cannot fire.
                        # `predicate_claim` above emits no `symbolic` kind either, so the
                        # guarding condition is dead as well. Left in place: it states what
                        # a symbolic Role would have to satisfy, and that sentence is the
                        # thing worth keeping until an axis produces one again.
                        roles[role].get("allowed_values", [])):
                    problems.add(
                        "invalid_symbolic_constant", f"{mpath}.bind.{role}.value",
                        f"constant {bindings[role].get('value')!r} is not registered "
                        f"by symbolic role {role!r}")
        for role in sorted(roles):
            descriptor = roles[role]
            if descriptor.get("required") and role not in bindings:
                problems.add("missing_required_role", f"{mpath}.bind.{role}",
                             f"predicate {predicate_id!r} requires role {role!r}")
    # `packs` was checked here in both directions -- every declared pack had to be used and
    # every used pack had to be declared -- until 2026-08-21, when the list itself went.
    # `ProfileDescriptor` no longer carries one either: nothing read it.
    #
    # 🔴 `_ambiguous_sentences` AND `_sentence_signature` LEFT THE SAME DAY, and NOT because
    # the rule was relaxed.  They refused two mappings a mapper could not tell apart, back
    # when a mapper picked one by structure.  `mappings` is now a MAP keyed by the sentence,
    # so "two mappings realizing one sentence" is not a thing a config can say -- JSON has
    # one value per key.  The signature function went with it: it existed only to be the
    # same expression `roleframe.ProfileSentences._resolve` matched on, and that expression
    # is now a dict lookup with nothing to mirror.


def _cross_profile_source(path: str, profile: Mapping[str, Any],
                          entities: Mapping[str, Any],
                          vocabulary: Mapping[str, Any], available: set[str],
                          problems: _Problems) -> None:
    # Source-level attribute bindings resolve against the same entity section and the same
    # frame columns as the role-level ones, so they are asked here rather than in a second
    # pass that could drift from this one.
    _bind_entities_refs(path, profile, entities, available, problems)
    for sentence, mapping in sorted(profile["mappings"].items()):
        mpath = f"{path}.mappings.{sentence}"
        for role, binding in mapping["bind"].items():
            _binding_refs(binding, f"{mpath}.bind.{role}", entities, available, problems)
        predicate = vocabulary.get(mapping["predicate"])
        if predicate is not None:
            _cross_binding_entity_types(
                mapping["bind"], predicate, entities, f"{mpath}.bind", problems)


def _cross_binding_entity_types(bindings: Mapping[str, Any],
                                predicate: Mapping[str, Any],
                                entities: Mapping[str, Any],
                                path: str, problems: _Problems) -> None:
    """Do the two entity ENDPOINTS name types this predicate admits?

    The endpoints are read by their canonical names rather than through an `emit` clause's
    `$role` references: a derived Claim always spells them `subject` and `target`, so the
    indirection had exactly one possible answer.  The refusal moves with them -- it now
    addresses the binding the author wrote instead of a `bundle.packs.…emit` path that no
    longer exists.
    """
    subject = bindings.get(SUBJECT_ROLE)
    if isinstance(subject, Mapping) and subject.get("kind") == "entity":
        entity_type = subject.get("entity_type")
        if entity_type in entities and entity_type not in predicate.get("subjects", []):
            problems.add("invalid_entity_ref", f"{path}.{SUBJECT_ROLE}.entity_type",
                         f"entity {entity_type!r} is not an allowed predicate subject")
    predicate_object = (predicate.get("object", {})
                        if isinstance(predicate.get("object"), Mapping) else {})
    target = bindings.get(TARGET_ROLE)
    if isinstance(target, Mapping) and target.get("kind") == "entity":
        entity_type = target.get("entity_type")
        allowed = predicate_object.get("types", [])
        if entity_type in entities and entity_type not in allowed:
            problems.add("invalid_entity_ref", f"{path}.{TARGET_ROLE}.entity_type",
                         f"entity {entity_type!r} is not an allowed predicate object")


def _binding_refs(binding: Any, path: str, entities: Mapping[str, Any],
                  available: set[str], problems: _Problems) -> None:
    if not isinstance(binding, Mapping):
        return
    if binding.get("kind") == "column" and binding.get("column") not in available:
        problems.add("unknown_column", f"{path}.column",
                     f"column {binding.get('column')!r} is not in EventFrame schema")
    if binding.get("kind") == "entity":
        entity_type = binding.get("entity_type")
        descriptor = entities.get(entity_type)
        if descriptor is None:
            problems.add("unknown_entity_type", f"{path}.entity_type",
                         f"unknown entity type {entity_type!r}")
        elif isinstance(binding.get("keys"), Mapping) and set(binding["keys"]) != set(descriptor.get("keys", [])):
            problems.add("invalid_entity_ref", f"{path}.keys",
                         "entity binding must contain exactly the registered identity keys")
        bound_attributes = binding.get("attributes")
        if descriptor is not None and isinstance(bound_attributes, Mapping):
            # 🔴 THE TYPE OWNS THE LIST OF NAMES; A SENTENCE ONLY FILLS THEM. Without this
            # a typo would ride all the way to the walk as a column nobody declared, and
            # the screen reads its column names off `/declaration` - so the operator would
            # be told a name the ontology never had. Refused HERE, with the form path, so
            # the test-run box can point at the box the name was typed into.
            declared = set(_column_values(descriptor.get("attributes") or []))
            for name in sorted(set(bound_attributes) - declared):
                problems.add(
                    "unknown_entity_attribute", f"{path}.attributes.{name}",
                    f"{entity_type!r} declares no attribute {name!r}"
                    f"{_did_you_mean(name, declared, 'attribute')}")
        for key, child in binding.get("keys", {}).items() if isinstance(binding.get("keys"), Mapping) else ():
            _binding_refs(child, f"{path}.keys.{key}", entities, available, problems)
        for name, child in (sorted(bound_attributes.items())
                            if isinstance(bound_attributes, Mapping) else ()):
            _binding_refs(child, f"{path}.attributes.{name}", entities, available, problems)


def _bind_entities_refs(path: str, profile: Mapping[str, Any],
                        entities: Mapping[str, Any], available, problems) -> None:
    """The two refusals ruling 124 names, both of them cross-section.

    (a) a source-level attribute name the TYPE never declared - same rule as the role
        level, asked where the source binds it so the operator is pointed at the box they
        typed in;
    (b) 🔴 ONE SENTENCE USING ONE TYPE IN TWO ROLES. A `die -> die` transfer binds
        `Die@1` as both subject and target, and a SOURCE-level attribute cannot say which
        of the two it is about - both readings are defensible and the compiler must not
        pick. Refused by name, and the fix is the role-level override, so the message
        names the path to type it into.
    """
    section = profile.get("entities")
    for entity_type in sorted(section or {}, key=str):
        descriptor = entities.get(entity_type)
        epath = f"{path}.entities.{entity_type}"
        bound = (section[entity_type] or {}).get("attributes")
        if not isinstance(bound, Mapping):
            continue
        if descriptor is None:
            problems.add("unknown_entity_type", epath,
                         f"unknown entity type {entity_type!r}")
            continue
        declared = set(_column_values(descriptor.get("attributes") or []))
        for name in sorted(set(bound) - declared):
            problems.add(
                "unknown_entity_attribute", f"{epath}.attributes.{name}",
                f"{entity_type!r} declares no attribute {name!r}"
                + _did_you_mean(name, declared, "attribute"))
        for name, child in sorted(bound.items()):
            _binding_refs(child, f"{epath}.attributes.{name}", entities, available,
                          problems)

    for sentence, mapping in sorted(profile.get("mappings", {}).items()):
        bindings = mapping.get("bind")
        if not isinstance(bindings, Mapping):
            continue
        roles_by_type: dict = {}
        for role in sorted(bindings):
            binding = bindings[role]
            if isinstance(binding, Mapping) and binding.get("kind") == "entity":
                roles_by_type.setdefault(binding.get("entity_type"), []).append(role)
        for entity_type, roles in sorted(roles_by_type.items(), key=lambda kv: str(kv[0])):
            if len(roles) < 2 or entity_type not in (section or {}):
                continue
            for role in roles:
                if isinstance(bindings[role].get("attributes"), Mapping):
                    continue
                problems.add(
                    "ambiguous_entity_attributes",
                    f"{path}.mappings.{sentence}.bind.{role}.attributes",
                    f"this sentence binds {entity_type!r} as {sorted(roles)}, so the "
                    f"source-level attributes cannot say which one they describe. Bind "
                    f"them on each role of this sentence instead.")


def required_mapper_input_columns(mapper: Mapping[str, Any], profile: Mapping[str, Any],
                                 profile_path: str) -> tuple[tuple[str, str], ...]:
    """Every column a mapper's `input_columns` MUST hold, with where each one is demanded.

    🔴 ONE ENUMERATION, TWO CALLERS (S-196, 판정 306-b 되돌림). The validator refuses an
    `input_columns` that misses one of these, and the authoring form DERIVES that same list —
    so the two have to be answering one question. They were not: the derivation was 「the
    prepared frame minus what `read` already reads」, which subtracts away exactly the columns
    a group or a binding needs, and a bundle rebuilt from it was refused by its own validator.

    ⛔ AND THE FIX MAY NOT BE A HAND-WRITTEN LIST. The first repair added the group columns
    only, and the next source fell over on its BINDING columns — a list extended by hand
    misses whatever the next declaration uses. This enumerates the kinds; a new kind is added
    here and both callers learn it at once.

    ⚠️ THE PATHS RIDE ALONG because the refusals name where the demand comes from — 「Profile
    column 'base_id' at …bind.subject.keys.x.column is missing」 sends an operator to the
    declaration that wants it, which 「it is missing」 alone does not.
    """
    demanded: list[tuple[str, str]] = []
    unit = mapper.get("unit") if isinstance(mapper.get("unit"), Mapping) else {}
    if unit.get("kind") == "group_by":
        # A row unit declares that there IS no group, so it demands nothing here.
        for column in _column_values(unit.get("columns") or ()):
            demanded.append((column, f"{profile_path}.unit.columns"))
    demanded.extend(_profile_binding_columns(profile_path, profile))
    seen: set = set()
    out: list[tuple[str, str]] = []
    for column, where in demanded:
        if column not in seen:
            seen.add(column)
            out.append((column, where))
    return tuple(out)


def _profile_binding_columns(path: str, profile: Mapping[str, Any]
                             ) -> tuple[tuple[str, str], ...]:
    """Every column a profile's bindings name, with where each is named.

    🔴 TOLERANT OF A HALF-BUILT PROFILE, AND THAT IS A REQUIREMENT NOW (S-196). This indexed
    `profile["mappings"]` and `mapping["bind"]` directly, which is safe for the VALIDATOR —
    `validate_bundle_errors` returns before cross-validation if anything is structurally
    wrong, and the file says so where it does it. It is NOT safe for the authoring form,
    which runs on a bundle being written: measured, three ordinary half-built shapes raised
    (`{}`, a mapping with no `bind`, a `bind` of `None`), and the screen an operator is using
    to finish the declaration would have gone blank.

    ⚠️ THE ANSWER DOES NOT MOVE. Measured across all 15 sources of the live bundle before the
    merge: the strict traversal and the tolerant one disagreed on ZERO. That measurement is
    what made this safe to unify rather than a hope.
    """
    out: list[tuple[str, str]] = []
    mappings = profile.get("mappings") if isinstance(profile, Mapping) else None
    if not isinstance(mappings, Mapping):
        return ()
    for sentence, mapping in sorted(mappings.items(), key=lambda pair: str(pair[0])):
        base = f"{path}.mappings.{sentence}.bind"
        bind = mapping.get("bind") if isinstance(mapping, Mapping) else None
        if not isinstance(bind, Mapping):
            continue
        for role in sorted(bind, key=str):
            out.extend(_binding_columns(bind[role], f"{base}.{role}"))
    return tuple(out)


def _binding_columns(binding: Mapping[str, Any], path: str) -> list[tuple[str, str]]:
    if binding["kind"] == "column":
        return [(binding["column"], f"{path}.column")]
    out: list[tuple[str, str]] = []
    if binding["kind"] == "entity":
        for key in sorted(binding["keys"]):
            out.extend(_binding_columns(binding["keys"][key], f"{path}.keys.{key}"))
        # An attribute's column is read from the same frame as a key's, so it belongs in
        # the same census - otherwise a source could declare a prepared column for an
        # attribute and nothing would notice it was never produced.
        for name in sorted(binding.get("attributes") or {}):
            out.extend(_binding_columns(binding["attributes"][name],
                                        f"{path}.attributes.{name}"))
    return out


def _table_has_unique_key(table: Mapping[str, Any], columns: Sequence[str]) -> bool:
    target = tuple(columns)
    for field in ("business_key", "composite_key"):
        if field in table and tuple(_column_values(table[field])) == target:
            return True
    return any(
        index["unique"] is True and tuple(index["columns"]) == target
        for index in table.get("indexes", [])
    )


def _columns_cover_declared_unique_key(table: Mapping[str, Any],
                                       columns: Sequence[str]) -> bool:
    candidate = {column for column in columns if isinstance(column, str)}
    declared: list[tuple[str, ...]] = []
    for field in ("business_key", "composite_key"):
        if field in table:
            declared.append(tuple(_column_values(table[field])))
    declared.extend(
        tuple(index.get("columns", ()))
        for index in table.get("indexes", [])
        if isinstance(index, Mapping) and index.get("unique") is True
    )
    return any(key and set(key).issubset(candidate) for key in declared)


def _relation_columns(relation: Any, columns: Sequence[Any], tables: Mapping[str, Any],
                      path: str, problems: _Problems) -> None:
    if relation not in tables:
        # 🔴 NAME THE TABLE AND THE NEXT ACTION.  A table the ledger reads but ingestion
        # never writes -- `void` is the live shape of this -- can be missing from
        # `table_config.json`, and the answer is to DECLARE IT THERE, never to keep a copy
        # here: that file is the physical authority, and declaring a table in it brings
        # drift detection and the grid along with it.  Same refusal
        # `ledger_admin.check_source_declaration` already gives for the legacy syntax, so
        # an operator meets one sentence rather than two.
        problems.add(
            "unknown_relation", path,
            f"relation {relation!r} is not declared in {PHYSICAL_CATALOG_FILENAME}; "
            f"declare the table there first — the ledger reads the physical schema from "
            f"that file and an undeclared table has no columns, no key, and no drift "
            f"check")
        return
    known = set(_table_columns(tables, relation))
    for column in columns:
        if not isinstance(column, str) or column not in known:
            problems.add("unknown_column", path,
                         f"column {column!r} is not in relation {relation!r}")


def _table_columns(tables: Mapping[str, Any], relation: Any) -> tuple[str, ...]:
    table = tables.get(relation)
    if not isinstance(table, Mapping) or not isinstance(table.get("columns"), Mapping):
        return ()
    return tuple(table["columns"])


def _implementation(item: Mapping[str, Any], path: str, problems: _Problems) -> None:
    _nonblank_text(item.get("implementation_id"), f"{path}.implementation_id", problems)
    version = item.get("implementation_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        problems.add("invalid_version", f"{path}.implementation_version",
                     "must be a positive integer")


def _column_types(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_type", path, "must be an object")
        return
    for name in sorted(value):
        _nonblank_id(name, f"{path}.{name}", problems)
        _nonblank_text(value[name], f"{path}.{name}", problems)


def _binding_kind_list(value: Any, path: str, problems: _Problems) -> None:
    _nonblank_list(value, path, problems)
    if _is_list(value):
        for index, kind in enumerate(value):
            if kind not in ("column", "constant", "entity"):
                problems.add("invalid_binding", f"{path}[{index}]",
                             f"unsupported binding kind {kind!r}")


def _default_binding_kinds(role_kind: Any) -> tuple[str, ...]:
    return ("entity",) if role_kind == "entity" else ("column", "constant")


def _scan_unsafe_keys(value: Any, path: str, problems: _Problems) -> None:
    stack: list[tuple[Any, str]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, Mapping):
            for key in sorted(current, key=str, reverse=True):
                child_path = _path(current_path, str(key))
                if str(key).lower() in _FORBIDDEN_EXECUTABLE_KEYS:
                    problems.add("unsafe_declaration", child_path, "field is not allowed")
                stack.append((current[key], child_path))
        elif _is_list(current):
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], f"{current_path}[{index}]"))


def _read_json(path: Path, logical_path: str) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, "config file is not valid UTF-8") from exc
    except OSError as exc:
        raise LedgerSetupValidationError(
            "config_read_failed", logical_path,
            f"could not read {path.name}: {exc.__class__.__name__}") from exc
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant)
    except _DuplicateKey as exc:
        raise LedgerSetupValidationError(
            "duplicate_id", logical_path, f"duplicate JSON key {exc.key!r}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path,
            f"invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    except _InvalidJsonConstant as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, str(exc)) from exc
    except RecursionError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, "JSON nesting is too deep") from exc
    if not isinstance(value, Mapping):
        raise LedgerSetupValidationError("invalid_type", logical_path,
                                         "JSON root must be an object")
    return value


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey(key)
        out[key] = value
    return out


def _reject_json_constant(value: str) -> None:
    raise _InvalidJsonConstant(f"non-standard JSON constant {value!r} is not allowed")
