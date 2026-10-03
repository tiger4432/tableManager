"""Physical DDL for `ledger_events` and the translator cursor. ONE spelling, here.

The migration script under `server/migrations/` is the operator's entry point and this
module is what it runs, so there is no second copy of the DDL to drift. `store.py` calls
the same functions, which is what lets a test build the real table in a scratch schema
instead of a lookalike (`SQLite accepts what PostgreSQL refuses` - the third time that
lesson was paid for in this project was 2026-08-05).

🔴 TIME PARTITIONED FROM DAY ONE
---------------------------------
`LEDGER_SLICE_1_BRIEF` §3-1: "첫날부터 시간 파티션(나중에 붙이면 스키마 재작성이라는
것이 본 세션에서 실측됨)". Converting a populated table to a partitioned one is a full
rewrite - there is no `ALTER TABLE ... PARTITION BY`. So the empty table is created
partitioned, and the translator creates the month it is about to write into.

WHAT THE CONSTRAINTS ARE FOR
-----------------------------
Each CHECK below is a rule from the design that would otherwise live only in prose:

  * ⚰️ `ck_ledger_register_has_no_object` IS GONE (S-77, 2026-09-09). It read
    `(predicate = 'register') = (object_kind IS NULL)` -- a DOMAIN WORD in the storage
    layer, and the storage layer is the one place that cannot be changed by editing a
    declaration. Which predicates are objectless is a DECLARED fact (`object.kind:
    none`), and `roleframe` already refuses an emission whose object kind disagrees
    with its vocabulary signature -- in both directions, by config path. So the check
    was a second, narrower spelling of a rule that already had an author, and its
    narrowness was the bug: a second objectless predicate (`retire@1`) could be
    declared, compiled, emitted, and then REFUSED BY THE DATABASE. What remains here
    is the structural invariant that owes nothing to any vocabulary:
    `ck_ledger_objectless_carries_only_qualifiers`.
  * `ck_ledger_subject_keys_is_object` - §3's `subject` row. The incident was a
    concatenated key collapsing when a piece was blank; storing a bare string here would
    reintroduce it at the storage layer, below every Python check.
  * `ck_ledger_no_self_supersede` - a correction that supersedes itself is a cycle the
    resolver would follow forever.

WHY THE UNIQUE INDEX IS ON COLUMNS AND NOT ON A HASH
-----------------------------------------------------
A hash index key would have to be computed identically by Python (at write time) and by
PostgreSQL (in the index expression), and those two do not spell JSON the same way -
`json.dumps(separators=(",",":"))` versus jsonb's own `::text`. Two spellings of one key
is exactly how a unique index stops matching what the writer computes, and it fails
SILENTLY (every row looks new). Indexing the columns themselves has no second spelling:
PostgreSQL compares jsonb to jsonb, semantically, and the writer computes nothing.

`coalesce(object_payload, '{}'::jsonb)` rather than the bare column, because NULLs in a
unique index are DISTINCT from each other on every PostgreSQL before 15 - two identical
`register` atoms would both be accepted. An empty object is a safe stand-in: no predicate's
signature accepts `{}` as a payload, so it can never collide with a real one.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone

import db_safety
import paths

logger = logging.getLogger("Ledger.Schema")


@dataclass(frozen=True)
class WorldNames:
    """Every name one ledger world is read and written under."""
    world: str | None               # None: the default
    schema: str | None              # None: the default's own, through `search_path`
    ledger: str
    cursor: str
    row_ref: str
    view: str | None                # the branch's walk relation; the default has none
    read_relation: str              # what the walk reads
    declaration_root: str
    draft_root: str                 # the explorer's drafts of THIS world's declaration
    base_root: str | None           # the declaration of the first world beneath; None: none
    space_statements: tuple         # what makes the world's own namespace; () for the default
    beneath: tuple = ()             # the worlds it stands on, top first, by name

    @property
    def declaration_path(self) -> str:
        from .setup_bundle import CONFIG_FILENAME

        return os.path.join(self.declaration_root, CONFIG_FILENAME)


#: What an operator types after `--world`. Lower case, so the schema name needs no quoting.
_WORLD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")

#: Where the branches' declaration roots live, one folder each, in the config directory.
_BRANCH_ROOTS = "ontology_worlds"

#: The default world's name where one is written - the layout's «operating» and «beneath»
#: (총괄 e67ef53f3). No branch is ever made under it.
DEFAULT_WORLD = "default"

#: Which world operates and what each stands on, ONE file beside the branches (총괄 e67ef53f3
#: ㄱ): {"operating": name, "beneath": {name: [name, ...]}, "history": [...]}. Absent, or a
#: world it does not name: the default operates and a branch stands on the default.
_LAYOUT_FILE = "worlds.json"
_layouts = {}


def _layout_path() -> str:
    return paths.config_path(_BRANCH_ROOTS, _LAYOUT_FILE)


def layout() -> dict:
    """The layout as the file says now - read again whenever it changes (one stat a call)."""
    path = _layout_path()
    try:
        status = os.stat(path)
        stamp = (status.st_mtime_ns, status.st_size)
    except FileNotFoundError:
        stamp = None
    if path not in _layouts or _layouts[path][0] != stamp:
        data = {}
        if stamp is not None:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        _layouts[path] = (stamp, data)
    return _layouts[path][1]


def _write_layout(data: dict) -> None:
    path = _layout_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)
    _layouts.pop(path, None)


def operating_world() -> str:
    """The world every seat that names none reads and writes (총괄 e67ef53f3 ②)."""
    return layout().get("operating") or DEFAULT_WORLD


def _declaration_root(world: str) -> str:
    return (paths.config_path("ontology") if world == DEFAULT_WORLD
            else paths.config_path(_BRANCH_ROOTS, world))


def _beneath(world: str) -> tuple:
    """What `world` stands on, top first, as the layout writes it - the default when it does
    not. Itself, one world twice, or a name that is no world name is refused."""
    chain = tuple(layout().get("beneath", {}).get(world, (DEFAULT_WORLD,)))
    if (world in chain or len(set(chain)) != len(chain)
            or any(name != DEFAULT_WORLD and not _WORLD_NAME.match(str(name)) for name in chain)):
        raise ValueError(f"ledger world {world!r} cannot stand on {list(chain)}: itself, a "
                         f"world twice, or a name that is not a world name")
    return chain


def world_names(world: str | None = None) -> WorldNames:
    """🔴 THE ONE SEAT FOR 「WHICH WORLD -> WHICH NAMES」 (총괄 60d7e8e42 · fb7ece9a3). Every
    other seat asks this; one that tests which world it is in anywhere else is a second door.

    No name is the OPERATING world (총괄 e67ef53f3) - the default until the layout names
    another - so every seat that names none follows it; `DEFAULT_WORLD` is the default by name.
    The default is the ledger as it always was - bare names through `search_path` - so an
    install with no branch issues the statements it always did (the drift oracle in
    `test_a_ledger_world_is_a_set_of_names`). A branch `w_<name>` is its own schema holding
    the sources it speaks for, and the walk reads its view: its atoms over those of the worlds
    it stands on (`ensure_view`). A branch name that is not a name is refused, never folded.
    """
    world = world or operating_world()
    if world == DEFAULT_WORLD:
        return WorldNames(None, None, "ledger_events", "ledger_translator_cursor",
                          "ledger_source_row_ref", None, "ledger_events",
                          _declaration_root(DEFAULT_WORLD),
                          paths.config_path("backup", "ontology_drafts"), None, ())
    if not _WORLD_NAME.match(str(world)):
        raise ValueError(
            f"a ledger world is named by lower-case letters, digits and _: {world!r}")
    beneath = _beneath(world)
    space = f"w_{world}"
    # 🔴 BESIDE THE DEFAULT'S ROOT, NEVER INSIDE IT, and the drafts beside the default's
    # drafts: a declaration root holds ONE json (`setup_bundle.load_setup_bundle` refuses any
    # other it finds by recursion), so a branch or its drafts inside `ontology/` would make
    # the default itself unloadable.
    return WorldNames(world, space, f"{space}.ledger_events",
                      f"{space}.ledger_translator_cursor", f"{space}.ledger_source_row_ref",
                      f"{space}.ledger_view", f"{space}.ledger_view", _declaration_root(world),
                      paths.config_path("backup", "ontology_world_drafts", world),
                      _declaration_root(beneath[0]) if beneath else None,
                      (f"CREATE SCHEMA IF NOT EXISTS {space}",), beneath)


def require_world(world: str | None = None) -> WorldNames:
    """`world_names` for a world that EXISTS - what every read door asks. A branch nobody
    declared is refused by name with the list; it is never read as the default, and never as
    the shipped sample (`ledger.config.load` falls back to the sample for a missing file)."""
    names = world_names(world)
    if names.world is not None and names.world not in worlds():
        raise LookupError(f"no ledger world {names.world!r}; declared: {worlds() or 'none'}")
    return names


def worlds() -> list[str]:
    """The branches there are: a declaration file under `<config>/ontology_worlds/<name>/`."""
    from .setup_bundle import CONFIG_FILENAME

    base = paths.config_path(_BRANCH_ROOTS)
    return [name for name in (sorted(os.listdir(base)) if os.path.isdir(base) else ())
            if _WORLD_NAME.match(name) and name != DEFAULT_WORLD
            and os.path.isfile(os.path.join(_declaration_root(name), CONFIG_FILENAME))]


def world_listing() -> dict:
    """The worlds a screen picks from - the default first, then the branches - and the one that
    operates: the one shape every answer that lists them carries (총괄 e51e3e417)."""
    return {"worlds": [DEFAULT_WORLD, *worlds()], "operating": operating_world()}


def operate(world: str, by=None) -> dict:
    """Make `world` the operating world from the next read on; the history keeps who and when.
    A world not declared is refused by name (`require_world`)."""
    name = require_world(world).world or DEFAULT_WORLD
    entry = {"world": name, "by": str(by or "operator"),
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    data = dict(layout())
    data["operating"] = name
    data["history"] = [*data.get("history", []), entry]
    _write_layout(data)
    return entry


def stand(world: str, beneath) -> tuple:
    """What a world about to be made stands on - written before its declaration, which starts
    as the first of them (nothing: the skeleton). Each must be declared - so not itself - and
    none twice; a world already made is refused."""
    names = world_names(world)
    if names.world is None or names.world in worlds():
        raise ValueError(f"ledger world {names.world or DEFAULT_WORLD!r} is already made; it "
                         f"stands where it stands")
    chain = tuple(beneath)
    unknown = [name for name in chain if name != DEFAULT_WORLD and name not in worlds()]
    if unknown:
        raise LookupError(f"no ledger world {unknown}; declared: {worlds() or 'none'}")
    if len(set(chain)) != len(chain):
        raise ValueError(f"ledger world {names.world!r} cannot stand on {list(chain)}: a world "
                         f"twice")
    data = dict(layout())
    data["beneath"] = {**data.get("beneath", {}), names.world: list(chain)}
    _write_layout(data)
    return chain


_DEFAULT = world_names(DEFAULT_WORLD)
LEDGER_TABLE = _DEFAULT.ledger
CURSOR_TABLE = _DEFAULT.cursor

#: Which PHYSICAL ROW each translated fact came from (S-54-b).
#:
#: 🔴 IT EXISTS BECAUSE A ROW THAT NO LONGER SPEAKS CANNOT BE ASKED. `source_raw_ref` is
#: built from a row's `order_by` values at translation time, so a withdrawal aimed at the
#: CURRENT translation finds nothing to aim with in precisely the cases where the old atoms
#: must go: the row was DELETED (S-54-b), or it is still there and is no longer this source's
#: row -- excluded by `exclude_when`, or edited until the declared column is blank (S-101).
#: This table is what can still name what to withdraw, because the ref is written down WHILE
#: the row is still speaking. Both `withdraw_deleted_rows` and `rescope` read it.
#:
#: ⚠️ THE KEY IS `(relation, row_id)` AND NOT `(source, row_id)`, because of who asks. The
#: question arrives from the outbox as "these rows of this TABLE are gone", and the outbox
#: does not know the ledger's sources -- teaching it would be the layer violation ruling 132
#: refused. `source_who` is what comes BACK, so one deleted row can withdraw the atoms of
#: every source that reads that table.
ROW_REF_TABLE = _DEFAULT.row_ref

#: The seven columns the unique index compares. Named once, used by the DDL and by the
#: writer's `ON CONFLICT` reasoning, so "what makes two atoms the same claim" has one
#: definition.
#:
#: 🔴 THREE OF THEM ARE DIGESTS, AND THIS FILE SAID OTHERWISE UNTIL 2026-08-29. Live has
#: carried `md5(...)` on the two jsonb columns and on `source_raw_ref` since `4bdbff36`,
#: which is what took this index from 1,123.6MB to 159.7MB. The spelling here never
#: followed, and `CREATE UNIQUE INDEX IF NOT EXISTS` asks whether the NAME is taken, never
#: whether the definition matches -- so live silently skipped it and a fresh deployment
#: silently built the fat one. Two boxes, two different indexes, no error on either.
#:
#: ⚠️ UNIQUENESS IS THEREFORE ON THE DIGEST, not on the value. Two atoms whose
#: `subject_keys` differ but whose md5 collides count as the same claim, and
#: `insert_atoms`'s `ON CONFLICT DO NOTHING` is untargeted -- so the loser is dropped
#: without a word. At this ledger's size that is not worth guarding against; it is worth
#: knowing, because the failure would look like an atom that never arrived.
DEDUPE_COLUMNS = (
    "occurred_at", "predicate", "subject_type", "md5(subject_keys::text)",
    "md5(coalesce(object_payload, '{}'::jsonb)::text)", "source_translator_ver",
    "md5(source_raw_ref)",
)


#: 🔴 ONE SPELLING, READ BY THE `CREATE` AND BY THE `ALTER`. A fresh install gets this
#: constraint from `CREATE_LEDGER` and an existing one gets it from the migration in
#: `ensure_schema`; two spellings is how the two end up enforcing different rules, which is
#: exactly what happened to `uq_ledger_atom` (`4bdbff36`) -- live silently kept the old
#: definition because `IF NOT EXISTS` asks about the NAME, never about the body.
OBJECTLESS_PAYLOAD_CONSTRAINT = "ck_ledger_objectless_carries_only_qualifiers"

#: 🔴 「목적어 없는 원자는 «수식어만» 든다」. `register` says nothing about an object and
#: everything about its SUBJECT, and since S-52 the attributes it carries ride in
#: `object_payload.qualifiers` -- which `envelope.registration_fingerprint` reads and the walk
#: turns into a node's columns. The retired rule below refused that shape outright, so a
#: declaration that gave an entity one attribute could not be written at all.
#:
#: ⚠️ THE RULE IS STILL A RULE. What may ride there is `qualifiers` and NOTHING else: an
#: objectless atom carrying a `value` or a `type` is an object wearing no name, and the
#: check refuses it exactly as before.
OBJECTLESS_PAYLOAD_CHECK = """(
        object_kind IS NOT NULL
        OR object_payload IS NULL
        OR (jsonb_typeof(object_payload) = 'object'
            AND object_payload <> '{}'::jsonb
            AND object_payload - 'qualifiers' = '{}'::jsonb))"""

#: 🪦 What this replaces: `CHECK (object_kind IS NOT NULL OR object_payload IS NULL)`.
#: Named so the migration can drop it, and kept named after it is gone so the next reader
#: can tell "this install predates attributes" from "somebody dropped a constraint".
RETIRED_OBJECTLESS_CONSTRAINT = "ck_ledger_objectless_has_no_payload"

#: 🪦 S-77. `CHECK ((predicate = 'register') = (object_kind IS NULL))` -- the storage
#: layer naming a predicate. 🔴 「코드에 도메인 낱말이 «없다»」 is an ARCHITECTURE rule,
#: not a style one, and this is why: the rule it enforced was already declared
#: (`object.kind: none`) and already checked where the declaration can answer back
#: (`roleframe` refuses an emission that disagrees with its vocabulary signature, in both
#: directions, by config path). Being NARROWER than the declaration is what made it a
#: defect rather than redundancy: declare a SECOND objectless predicate and the atom
#: compiles, emits, and is refused by the database -- three layers from the line an
#: operator wrote.
#:
#: ⚠️ KEPT AS A NAME so a reader can tell 「this install predates S-77」 from 「somebody
#: dropped a constraint」, exactly as `RETIRED_OBJECTLESS_CONSTRAINT` is.
RETIRED_REGISTER_OBJECT_CONSTRAINT = "ck_ledger_register_has_no_object"

#: The basis a not-an-event atom carries - an entity reference's, and a mapping's that binds no event
#: time (총괄 29047aedc · 0c9b6e3c0). Spelled once, in `setup_bundle`; the translator's stamp reads it.
from .setup_bundle import NOT_AN_EVENT_BASIS  # noqa: E402


def reads_as_event_time(basis) -> bool:
    """🔴 THE ONE ANSWER to 「is this atom's `occurred_at` the moment something happened」
    (총괄 29047aedc · 3bf28f893): only an atom with no basis. Every reader that takes the ledger's
    time AS AN EVENT TIME - a window, a timeline, a first sighting, an edge's shown time - asks
    this or `event_time_sql`, never a basis string of its own. Ordering claims is not that
    reading: it keeps the stored time for every atom (총괄 3bf28f893 `orders_claims`) - and a
    not-an-event atom stores its molecule's time, so it orders by that (총괄 0c9b6e3c0 ①)."""
    return basis is None


def event_time_sql(alias: str) -> str:
    """The SQL spelling of `reads_as_event_time` for the atom aliased `alias`."""
    return "(%s.occurred_at_basis IS NULL)" % alias


def create_ledger_sql(names: WorldNames) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {names.ledger} (
    id                    UUID        NOT NULL,
    subject_type          TEXT        NOT NULL,
    subject_keys          JSONB       NOT NULL,
    predicate             TEXT        NOT NULL,
    object_kind           TEXT,
    object_payload        JSONB,
    occurred_at           TIMESTAMPTZ NOT NULL,
    occurred_at_basis     TEXT,
    source_who            TEXT        NOT NULL,
    source_translator_ver TEXT        NOT NULL,
    source_raw_ref        TEXT        NOT NULL,
    supersedes            UUID,
    source_event_id       UUID        NOT NULL,
    source_event_state    TEXT        NOT NULL,
    CONSTRAINT ck_ledger_object_kind CHECK (
        object_kind IS NULL OR object_kind IN ('value', 'entity_ref', 'event_ref')),
    CONSTRAINT {OBJECTLESS_PAYLOAD_CONSTRAINT} CHECK {OBJECTLESS_PAYLOAD_CHECK},
    CONSTRAINT ck_ledger_subject_keys_is_object CHECK (
        jsonb_typeof(subject_keys) = 'object'),
    CONSTRAINT ck_ledger_no_self_supersede CHECK (
        supersedes IS NULL OR supersedes <> id),
    CONSTRAINT ck_ledger_source_event_state CHECK (
        source_event_state IN ('source_molecule', 'source_record', 'legacy_atom')),
    CONSTRAINT ck_ledger_occurred_at_basis CHECK (
        occurred_at_basis IS NULL OR occurred_at_basis IN ('ingested')),
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at)
"""


CREATE_LEDGER = create_ledger_sql(_DEFAULT)

def create_row_ref_sql(names: WorldNames) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {names.row_ref} (
    relation       TEXT NOT NULL,
    row_id         TEXT NOT NULL,
    source_who     TEXT NOT NULL,
    source_raw_ref TEXT NOT NULL,
    row_fingerprint TEXT,
    -- 🔴 THE REF IS IN THE KEY. One physical row can appear under SEVERAL claim refs: one
    -- event may emit several sentences over different subsets of its rows, and each
    -- subset produces its own `source_raw_ref`. Keyed without it, the second sentence
    -- would overwrite the first and its atoms would survive the row's deletion.
    PRIMARY KEY (relation, row_id, source_who, source_raw_ref)
)
"""


CREATE_ROW_REF = create_row_ref_sql(_DEFAULT)

#: 🔴 THE FLATTENED READ (총괄 0fb9e9390, 소유자 「원자들 검색」 · 「원자별 참조 행 rowid」): one row
#: per (atom, source row), keys and payload as plain text in their STORED spelling, for the
#: main grid (`kind: view`). An atom no row refers to - a source that read a view - keeps one
#: row with its source cells empty (LEFT JOIN). The source row column is `source_row_id`,
#: not `row_id`: the grid orders by a `row_id` column when one exists, and here it repeats.
ATOM_ROWS_VIEW = "ledger_atom_rows"
#: Atom -> its rows (the join, a page) and row -> its refs (a `source_row_id` filter). On the
#: ref table only: the ledger's own write path carries no new index.
ROW_REF_RAW_INDEX = "idx_ledger_row_ref_raw"
ROW_REF_ROW_INDEX = "idx_ledger_row_ref_row"


def row_ref_indexes(names: WorldNames, concurrently: bool = False) -> tuple:
    how = "CONCURRENTLY " if concurrently else ""
    return (f"CREATE INDEX {how}IF NOT EXISTS {ROW_REF_RAW_INDEX} ON {names.row_ref} "
            f"(source_who, md5(source_raw_ref))",
            f"CREATE INDEX {how}IF NOT EXISTS {ROW_REF_ROW_INDEX} ON {names.row_ref} (row_id)")


def atom_rows_view_name(names: WorldNames) -> str:
    return f"{names.schema}.{ATOM_ROWS_VIEW}" if names.schema else ATOM_ROWS_VIEW


def world_relation(table: str, world: str | None = None) -> str:
    """The relation the grid reads `table` through in `world` - the operating one when none is
    named (총괄 2bb20ff56). Each world has its own ledger atom view; every other table is the one
    table. A world named and not declared is refused by name, never folded to the default."""
    names = require_world(world) if world or table == ATOM_ROWS_VIEW else None
    return atom_rows_view_name(names) if table == ATOM_ROWS_VIEW else table


def _plain(column):
    """`k=v / k=v`, keys in order, each value in its STORED spelling (jsonb text: 1.0 stays 1.0)."""
    return (f"(SELECT string_agg(k || '=' || v, ' / ' ORDER BY k) "
            f"FROM jsonb_each_text({column}) AS kv(k, v))")


#: The view's columns and what each reads - ONE spelling, so the catalogue's column list is
#: scored against this tuple rather than against a copy.
ATOM_ROWS_SELECT = (
    # the atom's own uuid, NOT `::text`: a page orders by it, and only the uuid walks the
    # ledger's primary key in order - measured, `::text` sorted all 2.3M rows per page (14 s)
    ("atom_id", "e.id"),
    ("occurred_at", "e.occurred_at"),
    ("subject_type", "e.subject_type"),
    ("subject", _plain("e.subject_keys")),
    ("predicate", "e.predicate"),
    ("object", "CASE WHEN e.object_kind = 'entity_ref' THEN (e.object_payload->>'type') || ' ' || "
               + _plain("e.object_payload->'keys'")
               + " WHEN e.object_kind = 'value' THEN e.object_payload->>'value' END"),
    ("qualifiers", _plain("e.object_payload->'qualifiers'")),
    ("source_who", "e.source_who"),
    ("source_relation", "r.relation"),
    ("source_row_id", "r.row_id"),
    # 총괄 271f4512a ④: empty = `occurred_at` is the event's time, `ingested` = it is not.
    # LAST, because `CREATE OR REPLACE VIEW` can only append columns to a view that exists.
    ("occurred_at_basis", "e.occurred_at_basis"),
)
ATOM_ROWS_COLUMNS = tuple(name for name, _expression in ATOM_ROWS_SELECT)


def atom_rows_view_sql(names: WorldNames) -> str:
    columns = ",\n       ".join(f"{expression} AS {name}" for name, expression in ATOM_ROWS_SELECT)
    return f"""
CREATE OR REPLACE VIEW {atom_rows_view_name(names)} AS
SELECT {columns}
  FROM {names.ledger} e
  LEFT JOIN {names.row_ref} r
    ON r.source_who = e.source_who
   AND md5(r.source_raw_ref) = md5(e.source_raw_ref)
   AND r.source_raw_ref = e.source_raw_ref
"""

def create_cursor_sql(names: WorldNames) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {names.cursor} (
    source               TEXT        PRIMARY KEY,
    translator_ver       TEXT        NOT NULL,
    cursor_value         JSONB       NOT NULL,
    molecules_done       BIGINT      NOT NULL DEFAULT 0,
    atoms_written        BIGINT      NOT NULL DEFAULT 0,
    atoms_deduped        BIGINT      NOT NULL DEFAULT 0,
    molecules_refused    BIGINT      NOT NULL DEFAULT 0,
    incomplete_molecules BIGINT      NOT NULL DEFAULT 0,
    refusal_reasons      JSONB,
    source_head          JSONB,
    head_probed_at       TIMESTAMPTZ,
    row_census           JSONB,
    rows_indexed         BIGINT,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


CREATE_CURSOR = create_cursor_sql(_DEFAULT)

#: `refusal_reasons` in one sentence, so the shape is not learned from the writer's SQL:
#: `{reason: {"count": <bigint>, "last_at": "<UTC ISO-8601>"}}`, one entry per
#: `gate.REFUSAL_REASONS` name that has ever fired for this source.
#:
#: 🔴 IT IS A BREAKDOWN, NOT A SECOND OPINION (ruling R-2026-08-13-F). The two aggregate
#: integers beside it are the AUTHORITY and this column explains one of them, so it
#: ACCUMULATES exactly as `molecules_refused` does and `sum(count) == molecules_refused`
#: for every row the current writer has owned end to end. If the breakdown were written
#: outside the cursor-advance transaction it would drift from the aggregate, and that
#: disagreement would then read as a false alarm on the very screen built to show
#: trouble - a status strip that cries wolf about its own bookkeeping is worse than none.
#: `store._advance_cursor` therefore writes both in ONE statement, and
#: `test_ledger_l1_pg.py` pins the equality at write time.
#:
#: NULL is NOT `{}` and the difference is load-bearing. NULL means "this row predates the
#: column" - both development databases held such a row with `molecules_refused = 1` when
#: this shipped - so its aggregate can never be broken down and the reader says so rather
#: than rendering an empty breakdown that reads as "no refusals". `{}` means the writer
#: has owned this row and nothing has been refused.
REFUSAL_REASONS_COLUMN = "refusal_reasons"

# Ledger Graph's global entity catalogue and entity-centred subgraph are the named
# consumers that admit these indexes.  The first is partial—registrations are O(entities),
# not O(atoms).  The second pays per atom because an arbitrary issued entity must be able
# to retrieve every claim about itself without scanning all monthly partitions.
REGISTER_SEARCH_INDEX = "idx_ledger_register_search"
SUBJECT_ENTITY_INDEX = "idx_ledger_subject_entity"
SOURCE_EVENT_INDEX = "idx_ledger_source_event"
OBJECT_ENTITY_INDEX = "idx_ledger_object_entity"


def register_search_index_sql(names: WorldNames) -> str:
    return (f"CREATE INDEX IF NOT EXISTS {REGISTER_SEARCH_INDEX} ON {names.ledger} "
            f"USING gin ((subject_keys::text) gin_trgm_ops) WHERE predicate = 'register'")


def subject_entity_index_sql(names: WorldNames) -> str:
    return (f"CREATE INDEX IF NOT EXISTS {SUBJECT_ENTITY_INDEX} ON {names.ledger} "
            f"(subject_type, subject_keys)")


REGISTER_SEARCH_INDEX_SQL = register_search_index_sql(_DEFAULT)
SUBJECT_ENTITY_INDEX_SQL = subject_entity_index_sql(_DEFAULT)
SOURCE_EVENT_INDEX_SPECS = (
    (SOURCE_EVENT_INDEX, "(source_event_id, occurred_at, id)",
     "WHERE source_event_id IS NOT NULL"),
    (OBJECT_ENTITY_INDEX,
     "((object_payload->>'type'), (object_payload->'keys'))",
     "WHERE object_kind = 'entity_ref'"),
)


def source_event_index_sql(names: WorldNames) -> str:
    return (f"CREATE INDEX IF NOT EXISTS {SOURCE_EVENT_INDEX} ON {names.ledger} "
            f"{SOURCE_EVENT_INDEX_SPECS[0][1]} {SOURCE_EVENT_INDEX_SPECS[0][2]}")


def object_entity_index_sql(names: WorldNames) -> str:
    return (f"CREATE INDEX IF NOT EXISTS {OBJECT_ENTITY_INDEX} ON {names.ledger} "
            f"{SOURCE_EVENT_INDEX_SPECS[1][1]} {SOURCE_EVENT_INDEX_SPECS[1][2]}")


SOURCE_EVENT_INDEX_SQL = source_event_index_sql(_DEFAULT)
OBJECT_ENTITY_INDEX_SQL = object_entity_index_sql(_DEFAULT)

# Existing ledgers receive only nullable columns during ordinary startup.  That is a
# metadata-only additive change; the bounded operator migration owns the historical
# backfill and constraint validation.  New writes always populate both columns.
def ledger_additions(names: WorldNames) -> tuple:
    return (
        ("source_event_id",
         f"ALTER TABLE {names.ledger} ADD COLUMN source_event_id UUID"),
        ("source_event_state",
         f"ALTER TABLE {names.ledger} ADD COLUMN source_event_state TEXT"),
    )


LEDGER_ADDITIONS = ledger_additions(_DEFAULT)

#: Columns added to an EXISTING cursor table. `ensure_schema` applies them, so a
#: translator can never meet a table it cannot write into - the ordering hazard that
#: `add_frame_confirmation.py` documents (a reader reaching a column its migration has
#: not created yet) is real here in the WRITE direction too. The read side is defended
#: separately: `ledger_trace.coverage` asks the catalogue which of these exist before it
#: selects them, so a web server that boots before the migration serves an answer rather
#: than a 500.
#: ⚰️ `caught_up_at` IS RETIRED (판정 173). It answered "has this source nothing past its
#: cursor", and there is no cursor to be past: the initial load stages CREATE events like
#: every other change, and a row already translated is named by the row index and is never
#: staged twice. The question the column existed for is now
#: `backfill.rows_not_yet_translated`, which is exact rather than observed.
#:
#: 🔴 NO MIGRATION DROPS IT (판정 165, the `supersedes` prescription). An installed
#: database keeps the column with NOBODY WRITING IT, which is safe because nothing reads
#: it either; a DROP would be a schema change bought for nothing, on a table an operator
#: may be looking at. A fresh install simply never creates it.

#: 🔴 「표 행 N · 색인 M · 남은 N−M」, MEASURED SEPARATELY AND STAMPED (S-58,
#: 판정 180). The request path may not count: `relation_rows` on a ten-million-row table
#: and `count(DISTINCT row_id)` on the index are both scans, and D5 forbids a scan inside
#: a request. So a paced job measures and this column HOLDS the answer, with the shape
#: `ledger_trace.measured` gives every published number -- what it is, how it was
#: obtained, and WHEN. A reader that finds NULL says 「not measured yet」, which is a
#: different sentence from 「zero rows」.
ROW_CENSUS_COLUMN = "row_census"

#: How many DISTINCT physical rows this source currently has an index line for.
#:
#: 🔴 A COUNTED VALUE, BECAUSE COUNTING IT WAS THE LAST SCAN (S-122-b, 판정 250). The
#: census asked `count(DISTINCT row_id)` over the index for every source, every tick -
#: measured on the QA box 2.055 s for the largest source, which is not cheaper than the
#: relation scan the same round removed. The two seats that MOVE the index are both inside
#: the atoms' own transaction, so a counter maintained there is exact by construction
#: rather than by a repair job.
#:
#: ⚠️ `NULL` MEANS 「NOT COUNTED YET」 AND NOT 「ZERO」, the same distinction `row_census`
#: makes beside it. A source that has never been planted gets counted exactly once - by the
#: tick, once in its life - and is maintained from then on.
#:
#: ⚠️ DISTINCT ROWS, NOT REF LINES. One physical row wears several refs when a source emits
#: more than one sentence about it, and counting lines instead is what made the remainder
#: go negative before. So the increment counts rows gaining their FIRST line and the
#: decrement counts rows losing their LAST.
ROWS_INDEXED_COLUMN = "rows_indexed"

#: (총괄 bb9b1c19c (나)) The row as its source read it, printed on its index line
#: (`store.row_fingerprint_sql`). NULL = not yet printed.
ROW_FINGERPRINT_COLUMN = "row_fingerprint"


def row_ref_additions(names: WorldNames) -> tuple:
    return ((ROW_FINGERPRINT_COLUMN,
             f"ALTER TABLE {names.row_ref} ADD COLUMN {ROW_FINGERPRINT_COLUMN} TEXT"),)


def cursor_additions(names: WorldNames) -> tuple:
    return (
        (REFUSAL_REASONS_COLUMN,
         f"ALTER TABLE {names.cursor} ADD COLUMN {REFUSAL_REASONS_COLUMN} JSONB"),
        (ROW_CENSUS_COLUMN,
         f"ALTER TABLE {names.cursor} ADD COLUMN {ROW_CENSUS_COLUMN} JSONB"),
        (ROWS_INDEXED_COLUMN,
         f"ALTER TABLE {names.cursor} ADD COLUMN {ROWS_INDEXED_COLUMN} BIGINT"),
    )


CURSOR_ADDITIONS = cursor_additions(_DEFAULT)

# 🔴 EVERY INDEX BELOW HAS A NAMED CONSUMER, AND THAT IS THE ADMISSION RULE.
#
# Measured on this box at 300,000 atoms of the shapes this translator actually produces
# (VACUUM ANALYZE, PostgreSQL 18.3): the heap is 312.8 B/atom - within half a percent of
# the 312.3 B/atom the design measured independently - and indexes are the larger half of
# the bill. So an index nobody queries is not free: it is ~0.3-0.6 GB at ten million
# atoms, paid forever, to answer nothing.
#
# Three candidates were built, measured and then REMOVED for exactly that reason. They
# are recorded here with their prices so that adding one back is a decision with a number
# attached rather than a fresh guess:
#
#   idx_ledger_type_pred_time (subject_type, predicate, occurred_at)   64.4 B/atom
#       No consumer. The trace walk filters on the subject key, not on the type.
#   idx_ledger_subject_gin  USING gin (subject_keys jsonb_path_ops)    38.3 B/atom
#       Serves `subject_keys @> '{...}'`. Nothing asks that today; the walk asks
#       `subject_keys->>'lot' = ...`, which a GIN cannot answer. Add it when a consumer
#       needs to look a subject up by a key OTHER than `lot` (the reverse-radius query
#       of week 3 is the likely first one).
#   idx_ledger_id (id)                                                 31.6 B/atom
#       Redundant. The primary key is (id, occurred_at) with `id` LEADING, so the
#       watermark scan `WHERE id > :cursor ORDER BY id` already has an index per
#       partition and a MergeAppend across them.
def indexes(names: WorldNames) -> tuple:
    return (
        # CONSUMER: idempotency - `store.insert_atoms`'s `ON CONFLICT DO NOTHING`, proven by
        # `test_the_unique_index_holds_when_the_cursor_is_reset`. Risk 1 of the brief. The
        # cursor is the FIRST answer (a re-run reads nothing); this is the one that still
        # holds when somebody resets the cursor.
        # PRICE: 284.6 B/atom, the single largest line in the bill, because it carries
        # `source_raw_ref` plus both jsonb columns. That is the cost of schema-enforced
        # idempotency and it is stated so the trade can be re-decided rather than rediscovered.
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_atom ON {names.ledger} "
        f"({', '.join(DEDUPE_COLUMNS)})",

        # CONSUMER: `server/ledger_trace.py`'s recursive lineage walk (the slice's other
        # lane), which asks `subject_keys->>'lot' = :lot AND predicate = ANY(...)`.
        # 🔴 Its shape is dictated by a property of that query rather than by taste: the walk
        # carries NO `occurred_at` predicate, because "everything about this lot" has no time
        # bound - so partition pruning can never help it and every partition is visited on
        # every hop. Declared on the parent so PostgreSQL cascades it to partitions that do
        # not exist yet, which is what makes a monthly partition created next year still fast.
        f"CREATE INDEX IF NOT EXISTS idx_ledger_subject_lot ON {names.ledger} "
        f"((subject_keys->>'lot'), predicate)",

        # CONSUMER: `store.existing_registrations`, once per page rather than once per row -
        # a per-entity lookup is what makes a ten-million row backfill quadratic. PARTIAL,
        # because registers are O(entities) while the table is O(atoms), so this index stops
        # growing long before the table does. PRICE: 16.6 B/atom and falling.
        f"CREATE INDEX IF NOT EXISTS idx_ledger_register ON {names.ledger} "
        f"(subject_type, subject_keys) WHERE predicate = 'register'",

        # CONSUMER: `GET /api/ledger/entities?q=...`. Partial trigram over structured
        # identities: a contains search is useful in the picker, but casting every ledger
        # atom to text at request time is forbidden. `pg_trgm` is a database bootstrap
        # prerequisite (`setup/init_db.py`); the migration names its absence rather than
        # silently running the slow query.
        register_search_index_sql(names),

        # CONSUMER: the generic entity-centred graph. Exact (type, structured keys) probes
        # occur once per bounded frontier and can use this B-tree on every partition.
        subject_entity_index_sql(names),
    )


INDEXES = indexes(_DEFAULT)

# Built inline only for a brand-new empty ledger.  On an existing ledger these are
# intentionally owned by `add_ledger_source_events.py`, which uses CONCURRENTLY.  Letting
# ordinary writer startup build them synchronously would turn a read feature deployment
# into an unbounded write-path lock.
def source_event_indexes(names: WorldNames) -> tuple:
    return (source_event_index_sql(names), object_entity_index_sql(names))


SOURCE_EVENT_INDEXES = source_event_indexes(_DEFAULT)


def month_bounds(when: datetime):
    """`(start, end, suffix)` for the UTC month containing `when`.

    Everything is computed in UTC and the bounds are written with an explicit offset.
    A partition bound given without one is interpreted in the SESSION's TimeZone, so the
    same DDL run from two processes with different `TZ` would produce partitions that do
    not line up - and the row that falls in the gap fails to insert at all.
    """
    utc = when.astimezone(timezone.utc)
    start = datetime(utc.year, utc.month, 1, tzinfo=timezone.utc)
    end = datetime(utc.year + (utc.month // 12), (utc.month % 12) + 1, 1,
                   tzinfo=timezone.utc)
    return start, end, f"{start.year:04d}_{start.month:02d}"


def partition_name(when: datetime, names: WorldNames = _DEFAULT) -> str:
    return f"{names.ledger}_{month_bounds(when)[2]}"


#: The relations this module creates and owns, by name. One spelling, because two lists of
#: 「which tables are the ledger's」 drift and the one a maintenance pass walks would then be
#: the one nobody updated.
FIXED_TABLES = (LEDGER_TABLE, CURSOR_TABLE, ROW_REF_TABLE)

#: Monthly partitions are named `<LEDGER_TABLE>_<YYYY_MM>` (see `partition_name`), so a
#: caller that must recognise them without knowing WHICH months exist matches this prefix
#: against the relations the database actually reports.
PARTITION_PREFIX = f"{LEDGER_TABLE}_"


def owns_table(name: str) -> bool:
    """Is this relation one of the ledger's own?

    ⚠️ EXISTING PARTITIONS ONLY, and that falls out of asking the DATABASE rather than
    generating month names: a caller passes what `pg_class` (or a view over it) reported,
    so a month that was never created cannot be named here.
    """
    if not name:
        return False
    return name in FIXED_TABLES or name.startswith(PARTITION_PREFIX)


def create_partition_sql(when: datetime, names: WorldNames = _DEFAULT):
    start, end, _ = month_bounds(when)
    name = partition_name(when, names)
    return (f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {names.ledger} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')")


def _relation_exists(cursor, name: str) -> bool:
    """Catalogue gate before any DDL.

    Not decoration: a failed DDL statement poisons the transaction and every query after
    it fails for a reason that has nothing to do with the query. Asking the catalogue
    first is this project's standing rule for exactly that (server-pm lessons file).
    """
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
    return bool(cursor.fetchone()[0])


def constraint_exists(cursor, table: str, name: str) -> bool:
    """Does `table` carry a constraint called `name`? Catalogue first, as everywhere here."""
    cursor.execute(
        "SELECT 1 FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
        "WHERE rel.oid = to_regclass(%s) AND con.conname = %s", (table, name))
    return cursor.fetchone() is not None


def ensure_register_object_constraint_dropped(cursor,
                                              names: WorldNames = _DEFAULT) -> bool:
    """Drop S-77's retired constraint on an install that predates the removal.

    Returns whether it did anything. Idempotent: a fresh install never creates it, so the
    catalogue is asked and no DDL is issued -- which matters because `ensure_schema` runs
    at the start of the chain daemon and of every `backfill.run` (S-88).

    🔴 A DROP CANNOT FAIL ON EXISTING DATA, which is the whole safety argument. Removing a
    CHECK weakens the table: every row that satisfied it still satisfies what remains, there
    is no scan, and there is nothing to fix before or after. That is the opposite of the
    widening below, which had to argue its way to the same place.

    ⚠️ WHAT IS NOT DROPPED WITH IT: `ck_ledger_objectless_carries_only_qualifiers`. That
    one is structural -- an objectless atom carries qualifiers and nothing else -- and it
    names no predicate, so it stays true whatever any declaration says.
    """
    if not constraint_exists(cursor, names.ledger, RETIRED_REGISTER_OBJECT_CONSTRAINT):
        return False
    logger.info("[Ledger] dropping %s (S-77: the storage layer stops naming a predicate)",
                RETIRED_REGISTER_OBJECT_CONSTRAINT)
    cursor.execute(f"ALTER TABLE {names.ledger} "
                   f"DROP CONSTRAINT {RETIRED_REGISTER_OBJECT_CONSTRAINT}")
    return True


def ensure_objectless_payload_constraint(cursor, names: WorldNames = _DEFAULT) -> bool:
    """Widen the objectless-payload rule on an install that predates attributes.

    Returns whether it did anything, so a caller can say so. Idempotent: an install that
    already carries the constraint asks the catalogue and issues no DDL, which matters
    because `ensure_schema` runs at the start of the chain daemon and of every
    `backfill.run` (S-88).

    🔴 NO SCAN, AND `NOT VALID` IS NOT A SHORTCUT HERE. Measured on this deployment's
    PostgreSQL (18.3) against a scratch partitioned table: `ADD CONSTRAINT ... NOT VALID`
    on a PARTITIONED PARENT is accepted and recurses to every partition, and a later
    `VALIDATE CONSTRAINT` on the parent marks parent and partitions valid. `NOT VALID`
    already enforces the rule on every INSERT and UPDATE from this moment; what it skips is
    re-reading the rows already there -- which on a ledger of this shape is the whole cost.

    🔴 AND NO EXISTING ROW CAN VIOLATE IT, so the validation is a formality rather than a
    risk. The new rule is the old one OR one more disjunct, i.e. strictly WEAKER: every row
    that satisfied `object_kind IS NOT NULL OR object_payload IS NULL` still satisfies this.
    That is why the scan is left to `scripts/migrate_ledger_objectless_payload_constraint.py
    --apply` and is not taken here: an operator starting a backfill has not asked for a full
    read of the ledger, and there is nothing this could find.

    ⚠️ DROP AND ADD RIDE IN THE CALLER'S TRANSACTION, so there is no window in which the
    table carries neither rule. Both are catalogue-only.
    """
    if constraint_exists(cursor, names.ledger, OBJECTLESS_PAYLOAD_CONSTRAINT):
        return False
    logger.info("[Ledger] widening %s to %s", RETIRED_OBJECTLESS_CONSTRAINT,
                OBJECTLESS_PAYLOAD_CONSTRAINT)
    if constraint_exists(cursor, names.ledger, RETIRED_OBJECTLESS_CONSTRAINT):
        cursor.execute(f"ALTER TABLE {names.ledger} "
                       f"DROP CONSTRAINT {RETIRED_OBJECTLESS_CONSTRAINT}")
    cursor.execute(
        f"ALTER TABLE {names.ledger} ADD CONSTRAINT {OBJECTLESS_PAYLOAD_CONSTRAINT} "
        f"CHECK {OBJECTLESS_PAYLOAD_CHECK} NOT VALID")
    return True


def column_exists(connection, table: str, column: str) -> bool:
    """Does `table` carry `column`, in the schema `search_path` resolves it to?

    The same catalogue-first rule as `_relation_exists`, one level down, and it is
    resolved through `to_regclass` rather than by matching `information_schema` on a bare
    table name: this box has a second copy of these tables in a scratch schema, and an
    unqualified `information_schema` match reports on whichever one it meets first
    (the defect `add_ledger_events.report` documents for `pg_indexes`).

    Takes a DBAPI connection OR an open cursor, because both callers exist: `ensure_schema`
    already holds a cursor and a migration script holds a connection.
    """
    sql = ("SELECT EXISTS (SELECT 1 FROM pg_attribute "
           "WHERE attrelid = to_regclass(%s) AND attname = %s "
           "AND attnum > 0 AND NOT attisdropped)")
    if hasattr(connection, "execute"):                      # already a cursor
        connection.execute(sql, (table, column))
        return bool(connection.fetchone()[0])
    with connection.cursor() as cursor:
        cursor.execute(sql, (table, column))
        return bool(cursor.fetchone()[0])


def _ensure_trigram(cursor):
    """Install `pg_trgm`, because one of `INDEXES` cannot be built without it.

    🔴 MEASURED 2026-08-29 ON AN EMPTY DATABASE: `ensure_schema` did not survive one.
    It died on `gin_trgm_ops` - the trigram operator class - long before the atom table
    was usable, and the live box never showed it because the extension was installed
    there by hand at some point nobody recorded. Exactly the shape of the index defect
    fixed in the same round: a premise that is invisible wherever it already holds.
    The owner's definition of done is a new environment starting from a declaration and
    no code edits; a schema that cannot be built is short of the starting line.

    ⚠️ A MISSING PRIVILEGE IS NAMED, NOT SWALLOWED. `CREATE EXTENSION` needs rights an
    application role may not have, and the honest failure there is a sentence saying so -
    a silent pass would hand the operator the same invisible half-built schema this
    function was just fixed for, one layer down.
    """
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as exc:
        raise RuntimeError(
            "pg_trgm is required for the trigram index and this role cannot create it: "
            "%s. Install it once as a superuser (CREATE EXTENSION pg_trgm) and re-run."
            % exc) from exc


def ensure_row_ref_table(cursor, names: WorldNames = _DEFAULT):
    """Make the row index exist. Idempotent, and the ONLY spelling of its DDL.

    Called from `ensure_schema` and from the index backfill, because an install that has
    not run a translation since this table was added has no table for the backfill to write
    into -- and `UndefinedTable` from inside a paced job is a worse answer than making it.
    """
    cursor.execute(create_row_ref_sql(names))


def ensure_schema(connection, names: WorldNames = _DEFAULT):
    """Create the ledger, the cursor table and the indexes. Idempotent, additive only.

    No DROP, and the only ALTER is `CURSOR_ADDITIONS` - columns ADDED to the cursor
    table, each gated on the catalogue so an up-to-date database issues no DDL and takes
    no lock at all. Takes a DBAPI connection and commits once at the end, so a failure
    leaves nothing half-built.

    🔴 Why the ALTER is here rather than only in the migration script: the writer calls
    this on every run, so a translator can never reach a cursor table that is missing a
    column it is about to write. `add_ledger_refusal_reasons.py` remains the operator's
    entry point and the audit trail - it calls this same function, so there is still ONE
    spelling of the DDL (the rule `add_ledger_events.py` states).
    """
    with connection.cursor() as cursor:
        for statement in names.space_statements:
            cursor.execute(statement)
        ledger_existed = _relation_exists(cursor, names.ledger)
        cursor.execute(create_ledger_sql(names))
        # An install that predates attributes still carries the narrow rule, and the
        # translator is about to write an atom the narrow rule refuses. See the function.
        ensure_objectless_payload_constraint(cursor, names)
        ensure_register_object_constraint_dropped(cursor, names)
        cursor.execute(create_cursor_sql(names))
        row_ref_existed = _relation_exists(cursor, names.row_ref)
        ensure_row_ref_table(cursor, names)
        for column, statement in ledger_additions(names):
            if not column_exists(cursor, names.ledger, column):
                logger.info("[Ledger] adding %s.%s", names.ledger, column)
                cursor.execute(statement)
        for column, statement in cursor_additions(names):
            # Gated rather than `ADD COLUMN IF NOT EXISTS`: that spelling still takes
            # ACCESS EXCLUSIVE on the table to decide it has nothing to do, and this runs
            # at every chain-daemon start and every `backfill.run` (S-88).
            if not column_exists(cursor, names.cursor, column):
                logger.info("[Ledger] adding %s.%s", names.cursor, column)
                cursor.execute(statement)
        for column, statement in row_ref_additions(names):
            if not column_exists(cursor, names.row_ref, column):
                logger.info("[Ledger] adding %s.%s", names.row_ref, column)
                cursor.execute(statement)
        _ensure_trigram(cursor)
        for statement in indexes(names):
            cursor.execute(statement)
        if not ledger_existed:
            for statement in source_event_indexes(names):
                cursor.execute(statement)
        # A table that already has rows gets these from `add_ledger_atom_rows.py`,
        # CONCURRENTLY - here they would lock the ref table at every start.
        if not row_ref_existed:
            for statement in row_ref_indexes(names):
                cursor.execute(statement)
        if not _relation_exists(cursor, atom_rows_view_name(names)):
            cursor.execute(atom_rows_view_sql(names))
    connection.commit()


def changed_sources(names) -> frozenset:
    """The sources a world speaks for because its declaration differs from that of the world
    beneath it that speaks for each (총괄 60d7e8e42 1 · e67ef53f3 ④) - no new judge: each
    source's cursor fingerprint (the material that can change ITS atoms) compared by
    `LedgerStore.restamp_decision`, the one seat that says two fingerprints are the same. A
    source on one side only, or one a loader refused on one side, has no fingerprint there and
    so differs; refused on BOTH, there is nothing new to say and the atoms beneath stay in the
    view (총괄 10-01). A world standing on nothing - the default too - has nothing to differ
    from."""
    return _declared_speakers(names)[0] if names.beneath else frozenset()


def _fingerprints(root) -> dict:
    from .setup import load_setup
    from .setup_bundle import LedgerSetupValidationError
    from .setup_registry import cursor_translator_version

    snapshot = load_setup(root).snapshot
    out = {}
    for source_id in snapshot.source_plans:
        try:
            out[source_id] = cursor_translator_version(snapshot, source_id)
        except LedgerSetupValidationError:
            out[source_id] = None
    return out


def _differing(base: dict, this: dict) -> frozenset:
    from .store import LedgerStore

    refused_on_both = {source_id for source_id in set(base) & set(this)
                       if base[source_id] is None and this[source_id] is None}
    return frozenset(
        source_id for source_id in (set(base) | set(this)) - refused_on_both
        if LedgerStore.restamp_decision(base.get(source_id), this.get(source_id))[0]
        != "already")


def _declared_speakers(names) -> list:
    """Per world of the chain, top first: the sources its declaration speaks for - those whose
    fingerprint differs from the world beneath it in the chain that speaks for them, as the
    cell layers' «the upper one wins». The bottom speaks for all of its own (None)."""
    prints = [_fingerprints(root) for root in
              (names.declaration_root, *(_declaration_root(b) for b in names.beneath))]
    below, spoken = dict(prints[-1]), [None]
    for this in reversed(prints[:-1]):
        differs = _differing(below, this)
        spoken.insert(0, differs)
        for source_id in differs:
            if source_id in this:
                below[source_id] = this[source_id]
            else:
                below.pop(source_id, None)
    return spoken


def world_deletion(engine, world: str) -> dict:
    """What deleting a ledger branch takes - its schema, with every atom, cursor and index row
    in it, and its declaration and draft files. READ ONLY. The default is no branch and is
    never deleted (총괄 8d10633ae ㉢: the preview comes first because a DROP is not undone);
    nor is the operating world, or one another world stands on (총괄 e67ef53f3) - by name."""
    names = require_world(world)
    if names.world is None:
        raise ValueError("the default ledger world is not a branch and is never deleted")
    if names.world == operating_world():
        raise ValueError(f"ledger world {world!r} is the operating world - operate another first")
    standing = [other for other in worlds() if names.world in _beneath(other)]
    if standing:
        raise ValueError(f"ledger world {world!r} is beneath {standing} - they stand on it")
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (names.ledger,))
            atoms = 0
            if cursor.fetchone()[0]:
                cursor.execute(f"SELECT count(*) FROM {names.ledger}")
                atoms = int(cursor.fetchone()[0])
    finally:
        connection.rollback()
        connection.close()
    files = sorted(str(path) for root in (names.declaration_root, names.draft_root)
                   if os.path.isdir(root) for path in Path(root).rglob("*") if path.is_file())
    return {"world": names.world, "schema": names.schema, "atoms": atoms, "files": files}


def drop_world(engine, world: str, expect_atoms: int) -> dict:
    """Delete a ledger branch: its schema, CASCADE, and its two folders - only when the caller
    confirms the atom count its preview showed, so a branch that moved since is not taken."""
    preview = world_deletion(engine, world)
    if int(expect_atoms) != preview["atoms"]:
        raise ValueError(f"branch {world!r} now holds {preview['atoms']} atom(s), not "
                         f"{expect_atoms} - preview it again")
    names = world_names(world)
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {names.schema} CASCADE")
        connection.commit()
    finally:
        connection.close()
    for root in (names.declaration_root, names.draft_root):
        if os.path.isdir(root):
            shutil.rmtree(root)
    _ensured.discard(names.schema)
    data = dict(layout())
    if names.world in data.get("beneath", {}):
        data["beneath"] = {k: v for k, v in data["beneath"].items() if k != names.world}
        _write_layout(data)
    return {**preview, "deleted": True}


def ensure_world(engine, names: WorldNames) -> None:
    """A branch's own schema and tables, before its translation reads or writes them. The
    default has no namespace of its own to make, and its tables are the daemon's and the
    CLI's to ensure (S-88) - so a library call on the default does nothing here. Once made in
    this process, a world whose ledger is still there is not made again: the live follow-up
    writes an operating branch every batch."""
    if not names.space_statements:
        return
    connection = engine.raw_connection()
    try:
        if names.schema in _ensured:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (names.ledger,))
                if cursor.fetchone()[0]:
                    return
        ensure_schema(connection, names)
        _ensured.add(names.schema)
    finally:
        connection.rollback()
        connection.close()


_ensured = set()


def ensure_view(engine, names: WorldNames, source=None) -> None:
    """A branch's walk relation: one leg per world of its chain, top first, each leg minus the
    atoms of every source a leg above it speaks for (`chain_speakers`), so translating an
    unchanged source there cannot double it. Standing on nothing: its own leg alone. The
    default has no view. A write that names its `source` keeps a view that already shows that
    source from this world - its speakers cannot have moved; the live follow-up writes so.

    🔴 THE FILTER SITS OUTSIDE THE UNION, ON A LEG MARKER. Box EXPLAIN 09-30: a `WHERE` on
    the partitioned default's leg keeps the planner from flattening the union, and every
    walk read seq-scanned every partition (0.43 ms -> 775 ms); outside, both legs keep their
    indexes. The columns are named - the default's own, in its order - because two tables
    grown by different histories of `ALTER` need not agree on `*`. Dropped and made again in
    one commit: a view's column list is fixed when it is created.
    """
    if not names.view:
        return
    connection = engine.raw_connection()
    try:
        made = _made_with(connection, names)
        if source is not None and made and source in (made[0][1] or ()):
            connection.rollback()
            return
        _write_view(connection, names)
    finally:
        connection.close()


def _write_view(connection, names: WorldNames) -> None:
    speakers = chain_speakers(connection, names)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(%s) "
            "AND attnum > 0 AND NOT attisdropped ORDER BY attnum", (_DEFAULT.ledger,))
        columns = ", ".join('"%s"' % row[0] for row in cursor.fetchall())
        # The leg label is the world's name - checked by `_WORLD_NAME`, so it is spelled inline.
        selects, conditions, excluded, above = [], [], [], set()
        for world, spoken in speakers:
            selects.append(f"SELECT '{world}'::text AS world_leg, {columns} "
                           f"FROM {world_names(world).ledger}")
            if above:
                conditions.append(f"NOT (world_leg = '{world}' AND source_who = ANY (%s::text[]))")
                excluded.append(sorted(above))
            above |= set(spoken or ())
        cursor.execute(f"DROP VIEW IF EXISTS {names.view}")
        cursor.execute(
            f"CREATE VIEW {names.view} AS SELECT * FROM ({' UNION ALL '.join(selects)}) legs"
            + (f" WHERE {' AND '.join(conditions)}" if conditions else ""), excluded or None)
        # What it was made from rides on it, so the live follow-up reads the same answer.
        cursor.execute(f"COMMENT ON VIEW {names.view} IS %s", (json.dumps(
            [[world, None if spoken is None else sorted(spoken)] for world, spoken in speakers]),))
    connection.commit()


def chain_speakers(connection, names: WorldNames) -> list:
    """🔴 WHICH WORLD OF A CHAIN SPEAKS FOR WHICH SOURCE - the one seat (총괄 e67ef53f3 ④ ·
    86d5061a0). Per world, top first: (its name, the sources it speaks for in this chain) - its
    declaration differs from that of the world beneath that speaks for each, or it has written
    them; each source once, in the topmost. The bottom (None) speaks for the rest. The view
    shows each source from that world, and the live follow-up writes it there."""
    legs = (names.world or DEFAULT_WORLD, *names.beneath)
    declared = _declared_speakers(names) if names.beneath else [None]
    out, above = [], set()
    with connection.cursor() as cursor:
        for world, said in zip(legs, declared):
            if said is None:
                out.append((world, None))
                continue
            cursor.execute(f"SELECT DISTINCT source_who FROM {world_names(world).ledger}")
            spoken = frozenset((set(said) | {row[0] for row in cursor.fetchall()}) - above)
            out.append((world, spoken))
            above |= spoken
    return out


def followed_by(engine, names: WorldNames | None = None) -> list:
    """`chain_speakers` of a world - the operating one when none is named - as its view was
    last made with them: one catalogue read, so the live follow-up writes each source into the
    world the view shows it from. A view made before they rode on it is answered afresh."""
    names = names or world_names()
    if not names.view:
        return [(names.world or DEFAULT_WORLD, None)]
    connection = engine.raw_connection()
    try:
        return _made_with(connection, names) or chain_speakers(connection, names)
    finally:
        connection.rollback()
        connection.close()


def speaker(chain, source) -> str:
    """The world of `chain` - `followed_by`'s answer, top first - that speaks for `source`: the
    topmost that names it, else the bottom, which speaks for the rest. Where the live follow-up
    writes it, and so where a census measures it and a backfill writes it (총괄 8b81e79a0)."""
    for world, spoken in chain:
        if spoken is None or source in spoken:
            return world


def speaking_world(engine, source, world=None) -> str:
    """The world `source` is translated and counted in, by name (총괄 8b81e79a0): not named,
    the one that speaks for it in the operating world's chain (`speaker`), as the live
    follow-up writes it; named, it must be the one that speaks for it in its own chain -
    refused by name with the one that does. A world that does not speak for a source would
    write nothing for it, and say nothing."""
    from .setup import LedgerSetupError

    names = require_world(world)
    said = speaker(followed_by(engine, names), source)
    if world is not None and said != (names.world or DEFAULT_WORLD):
        raise LedgerSetupError(
            "world_does_not_speak", "world",
            f"{source} is spoken for by {said}, not {world} - run with --world {said}, or "
            f"without --world")
    return said


def speaking_cursor(chain, read, columns, where="") -> dict:
    """{source: (world, *columns)}: each source's cursor row from the world that speaks for it
    in `chain` (`followed_by`'s answer), `read(sql)` giving the rows. Its census is measured and
    stored there (총괄 8b81e79a0); a row another world holds for it is not its answer."""
    rows = {}
    for world, _spoken in chain:
        for row in read(f"SELECT source, {', '.join(columns)} "
                        f"FROM {world_names(world).cursor} {where}"):
            if speaker(chain, row[0]) == world:
                rows[row[0]] = (world, *row[1:])
    return rows


def _made_with(connection, names: WorldNames):
    """The speakers a world's view was last made with - None when there is no view, or it was
    made before they rode on it."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT obj_description(to_regclass(%s), 'pg_class')", (names.view,))
        said = cursor.fetchone()[0]
    return ([(world, None if spoken is None else frozenset(spoken))
             for world, spoken in json.loads(said)] if said else None)


def ensure_partition(connection, when: datetime, known=None,
                     names: WorldNames = _DEFAULT):
    """Make sure the month containing `when` exists. Returns the partition name.

    Runs in its OWN transaction and commits before returning. That is deliberate: if
    partition creation ran inside the atom transaction and failed, the failure would roll
    back the molecule too and the operator would see an atomicity refusal for what is
    really a DDL problem. Two transactions keep the two failures distinguishable.

    `known` is an optional set the caller keeps across calls, so a backfill that stays
    inside one month issues one catalogue query instead of one per batch.
    """
    name = partition_name(when, names)
    if known is not None and name in known:
        return name
    try:
        with connection.cursor() as cursor:
            # 🔴 `CREATE TABLE ... PARTITION OF` takes ACCESS EXCLUSIVE on the PARENT,
            # so it queues behind every open reader of `ledger_events` - including a
            # reader belonging to the same process. That is not hypothetical: the first
            # run of this backfill wedged for minutes because its own page-reading
            # connection sat idle-in-transaction holding ACCESS SHARE while this
            # statement waited for it. `backfill.py` now ends that transaction before it
            # writes, and this timeout is the second net: a self-block must FAIL, with a
            # message that says what it was waiting for, rather than hang. A hung
            # process gives an operator nothing to diagnose (an instrument that goes
            # blind under its own fault is this project's own 2026-08-11 lesson).
            cursor.execute("SET LOCAL lock_timeout = '%s'" % db_safety.DDL_LOCK_TIMEOUT)
            if not _relation_exists(cursor, name):
                cursor.execute(create_partition_sql(when, names))
                logger.info("[Ledger] created partition %s for %s", name,
                            when.astimezone(timezone.utc).date())
        connection.commit()
    except Exception as exc:
        # A racing creator is the expected reason to land here; anything else must not
        # be allowed to poison the connection for the caller's next statement. The
        # rollback is mandatory before the re-check: a failed statement leaves the
        # transaction aborted and every query after it fails for an unrelated reason
        # (server-pm lessons file).
        connection.rollback()
        with connection.cursor() as cursor:
            if not _relation_exists(cursor, name):
                if db_safety.waited_past_the_lock_timeout(exc):
                    raise RuntimeError(
                        f"could not create partition {name}: another session (possibly "
                        f"this process's own reader) holds a lock on "
                        f"{names.ledger}. Partition DDL needs ACCESS EXCLUSIVE on the "
                        f"parent table. Original error: {exc}") from exc
                raise
        connection.commit()
    if known is not None:
        known.add(name)
    return name


def ensure_partitions_for_range(connection, first: datetime, last: datetime):
    """Every month from `first` to `last` inclusive. Returns the names it ensured."""
    names = []
    cursor_month = month_bounds(first)[0]
    end = month_bounds(last)[0]
    while cursor_month <= end:
        names.append(ensure_partition(connection, cursor_month))
        cursor_month = month_bounds(cursor_month + timedelta(days=32))[0]
    return names


def partitions(connection, names: WorldNames = _DEFAULT):
    """The ledger's partitions, by name. For the report and for a health check."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_get_expr(c.relpartbound, c.oid)
            FROM pg_class parent
            JOIN pg_inherits inh ON inh.inhparent = parent.oid
            JOIN pg_class c ON c.oid = inh.inhrelid
            WHERE parent.oid = to_regclass(%s)
            ORDER BY c.relname
        """, (names.ledger,))
        return [(name, bound) for name, bound in cursor.fetchall()]
