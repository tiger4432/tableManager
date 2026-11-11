"""The ledger's translation over a page read by SQL (lead 10-31 ② stage 1): one SELECT of the columns a declarative
source names, the page held as CELLS (column -> tuple), and today's judges called on them - no DataFrame per
molecule. It writes nothing; `python -m ledger sql-shadow` holds it against the Python path atom by atom. A source
whose mapper is code is not this path's (`NotCovered`) - it stays on the Python path and is counted apart."""
from __future__ import annotations

import json

from . import roleframe
from .event_frame import SourcePreparationContext, SourcePreparationError, named_columns, prepared_molecules
from .setup_bundle import executes_the_bindings


class NotCovered(Exception):
    """The source's mapper is code, not its declaration - the Python path translates it."""


def covers(plan) -> bool:
    return executes_the_bindings(plan.driver.mapper.implementation.implementation_id)


#: the switch (lead 11-01 stage 3): `ingestion_settings.json` "ledger_translate" - "python" sends every source back
#: to the Python path; anything else, or absent, is "sql". One for the deployment, no switch a source. Read a page,
#: held until the file changes (`read_ingestion_settings`), so a process takes a change at its next page
TRANSLATE_SETTING = "ledger_translate"
#: the words the log line and the run's result both say (the run stores it as `translated_by_label`)
TRANSLATED_BY = "translated by"
_said_path = {}


def translate_path(plan) -> str:
    """"sql" or "python" for this source's next page - python when the switch says so or the mapper is code (a code
    mapper stays on the Python path until stage 4). Said a source at a process's first page of it and at each change
    of its path - the path it goes by, not the switch alone (C 11-01: a code mapper went by python under a «sql» line)."""
    import logging

    from ingestion.settings import read_ingestion_settings

    value = read_ingestion_settings().get(TRANSLATE_SETTING, "sql")
    path = "python" if value == "python" or not covers(plan) else "sql"
    if _said_path.get(plan.source_id) != path:
        logging.getLogger(__name__).warning("[Ledger] %s %s %s (ingestion_settings.json %s: %r%s)", plan.source_id,
                                            TRANSLATED_BY, path, TRANSLATE_SETTING, value,
                                            "" if covers(plan) else " - its mapper is code")
    _said_path[plan.source_id] = path
    return path


def translated_by(plan, start) -> str:
    """A run's path: the one it started on, or «sql → python» when the switch changed under it."""
    end = translate_path(plan)
    return start if start == end else "%s → %s" % (start, end)


def read_page(connection, plan, **page) -> list:
    """The page's rows - the columns the declaration names (`named_columns`; no other column reaches an atom, 판정
    201), by the read `backfill` pages with (`after` · `upper` · `limit` · `scope`)."""
    from .backfill import _fetch_v2_lineage_rows

    return _fetch_v2_lineage_rows(connection, plan, named_columns(plan), **page)


def event_results(snapshot, source_id, rows) -> tuple:
    """A page's rows -> (one `roleframe.LedgerV2DryRunResult` a molecule, the preparation context with its refusals
    and excluded rows) - the same results `runtime_v2.preview_cursor_batch` hands the gate."""
    cells = {column: tuple(row[column] for row in rows) for column in rows[0]} if rows else {}
    results, context, _row_ids = cells_results(snapshot, source_id, cells, len(rows))
    return results, context


def cells_results(snapshot, source_id, cells, rows: int) -> tuple:
    """The page as cells (column -> tuple of `rows` values) -> (the results, the preparation context, {row ref: row
    id} of the rows a molecule took - what `runtime_v2._row_ref_index` reads off the Python path's frames)."""
    from .event_frame import FRAME_ROW_ID_COLUMN

    plan = snapshot.source_plans[source_id]
    if not covers(plan):
        raise NotCovered(f"{source_id}: mapper {plan.driver.mapper.implementation.implementation_id!r} is code")
    context = SourcePreparationContext(snapshot, plan)
    if not rows:
        return (), context, {}
    missing = [column for column in named_columns(plan) if column not in cells]
    if missing:
        raise SourcePreparationError(
            "source_preparation_incomplete", "source_batch.columns",
            f"base cursor batch is missing physical columns: {missing}")
    mapper = roleframe.MapperContext(snapshot, plan)
    descriptor, profile = plan.driver.mapper, plan.profile
    results = []
    ids, row_ids = cells.get(FRAME_ROW_ID_COLUMN), {}
    for positions, row_refs, instant, attrs in prepared_molecules(context, cells, rows):
        if ids is not None:
            row_ids.update((str(ref), str(ids[position])) for position, ref in zip(positions, row_refs)
                           if ids[position] is not None and ref is not None)
        molecule = {column: tuple(values[position] for position in positions) for column, values in cells.items()}
        molecule[roleframe.SOURCE_ROW_REF_COLUMN] = tuple(row_refs)
        molecule[roleframe.SOURCE_OCCURRED_AT_COLUMN] = (instant,) * len(positions)
        emissions, unsaid = [], []
        units = roleframe.unit_partition(mapper, descriptor, molecule, len(positions),
                                         roleframe.checked_row_refs(row_refs))
        for index, (unit, refs, _whole) in enumerate(units):
            columns = {column: tuple(values[position] for position in unit) for column, values in molecule.items()}
            produced = roleframe.declared_emissions(mapper, profile, columns, refs, len(unit))
            roleframe.unit_emissions(mapper, profile, index, produced, None, columns, emissions, unsaid)
        results.append(roleframe.dry_run_result(
            mapper, attrs, roleframe.role_rows_of(mapper, attrs, emissions, unsaid, descriptor, profile)))
    return tuple(results), context, row_ids


def atom_records(plan, results) -> list:
    """The atoms `results` hand the gate (`runtime_v2`: registrations filtered, time basis stamped, event ids minted),
    each as one sorted-key JSON line of its semantic fields and its basis - what the shadow compares."""
    import json

    from . import runtime_v2

    groups = runtime_v2._filtered_event_atoms(results, ())
    runtime_v2._stamp_occurred_at_basis(plan, groups)
    records = []
    for atoms in groups:
        for atom in atoms:
            atom.ensure_source_event_identity()
            records.append(json.dumps(dict(runtime_v2._semantic_atom(atom), basis=atom.occurred_at_basis),
                                      sort_keys=True, default=str, ensure_ascii=False))
    return records


def shadow_source(engine, setup, source, page_rows=2000, max_pages=None, show=3) -> dict:
    """Every page of `source` translated by both paths, read only - the backfill's pages (page key order, cut at the
    same `after`). -> rows, pages, atoms each path, the atoms only one path made (count and the first `show`),
    refusals, excluded rows by cause (and the pages whose causes differ) and seconds each path."""
    import time
    from collections import Counter

    from . import backfill, runtime_v2
    from .setup import preview_selected_cursor_batch

    plan = setup.snapshot.source_plans[source]
    page_key, readable = backfill._page_key(plan), backfill._readable_columns(engine, plan)
    said = {"source": source, "rows": 0, "pages": 0, "atoms": {"python": 0, "sql": 0},
            "only": {"python": 0, "sql": 0}, "first": {"python": [], "sql": []},
            "refused": {"python": 0, "sql": 0}, "excluded": {"python": {}, "sql": {}}, "excluded_pages_differ": 0,
            "seconds": {"python": 0.0, "sql": 0.0}}
    after = None
    while max_pages is None or said["pages"] < max_pages:
        raw = engine.raw_connection()
        try:
            full = backfill._fetch_v2_lineage_rows(raw, plan, readable, after=after, limit=page_rows)
            narrow = read_page(raw, plan, after=after, limit=page_rows)
        finally:
            raw.close()
        if not full:
            break
        said["pages"] += 1
        said["rows"] += len(full)
        frame = backfill._v2_frame(full)
        started = time.perf_counter()
        with roleframe.times_read(backfill.times_read_of(engine, plan, frame)):
            preview = preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                                    known_registrations=(), translate="python")
            python = atom_records(plan, preview.event_results)
        said["seconds"]["python"] += time.perf_counter() - started
        started = time.perf_counter()
        cells = {column: tuple(row[column] for row in narrow) for column in narrow[0]}
        with roleframe.times_read(backfill.times_read_of(engine, plan, cells)):
            results, context = event_results(setup.snapshot, source, narrow)
            sql = atom_records(plan, results)
        said["seconds"]["sql"] += time.perf_counter() - started
        said["refused"]["python"] += len(preview.refusals)
        said["refused"]["sql"] += len(context.refusals)
        kept_out = {"python": dict(preview.excluded_rows or {}), "sql": dict(context.excluded_rows or {})}
        said["excluded_pages_differ"] += kept_out["python"] != kept_out["sql"]
        for name, causes in kept_out.items():
            for cause, n in causes.items():
                said["excluded"][name][cause] = said["excluded"][name].get(cause, 0) + n
        for name, mine, theirs in (("python", python, sql), ("sql", sql, python)):
            said["atoms"][name] += len(mine)
            extra = list((Counter(mine) - Counter(theirs)).elements())
            said["only"][name] += len(extra)
            said["first"][name].extend(extra[:max(0, show - len(said["first"][name]))])
        after = full[-1][page_key]
    said["seconds"] = {name: round(value, 1) for name, value in said["seconds"].items()}
    said["rows_per_s"] = {name: (round(said["rows"] / value) if value else None)
                          for name, value in said["seconds"].items()}
    return said


def differs(said) -> bool:
    """The two paths are the same only when the atoms, the refusals and every page's excluded rows by cause are."""
    return bool(any(said["only"].values()) or said["refused"]["python"] != said["refused"]["sql"]
                or said["excluded_pages_differ"])


# --------------------------------------------------------------------------- the walk's compile (lead 11-06, engine=virtual)
# A declarative source as COLUMN MAPS over its own table (owner 11-07 «행별로 순수함수로 노드 및 엣지 키, 속성 맵핑 -
# sql 컬럼 맵핑 컴파일»): a leg is one sentence (or one entity reference a sentence's entity carries) - the column each
# end's keys, each qualifier, the time and the row's name are read from, and the rows it says. A walk reads those columns
# (`Leg.read`) and makes a row's atom in Python by the translator's own functions (`Leg.atom`) - nothing computed per
# row in SQL, no second spelling of the mapping. `contracts/ledger_sql_compile` holds it and the translator to one
# expectation. What this compile does not read leaves the source out by name (`NotCompiled`) - the answer lists it.

class NotCompiled(Exception):
    """A source the walk's compile does not read - why, in the answer's `engine.left_out`."""


_TEXT, _FLOAT, _INTEGER, _TIME = "text", "float", "integer", "time"
_NUMBERS = (_FLOAT, _INTEGER, "numeric")


#: The object end of a sentence with no object (a registration): no type, no key - no node names it, and its atom's
#: object kind is None, as the stored compiler writes it (`roleframe`, `is_registration`).
NO_OBJECT = (None, {})


class Leg:
    """One sentence or reference of one source as a column map. `ends` {arm: (bare type, {key: spec})} - the subject
    is the outgoing end; a spec is {"column", "declared", "kind", "zone"} or {"constant": spelled}. `qualifiers` {name:
    spec}; `required` the specs that must not be blank for the row to say anything (a reference's sentence's own keys
    too); `kept` the rows it says - SQL over the table's own cells; `columns` {arm: the text columns its keys are read
    from as they are} - an index on one of them serves the arm, else the answer says «scan»; `naive` its time column
    holds no zone (read on the declared one)."""

    def __init__(self, plan, sentence, predicate, ends, qualifiers, required, kept, basis, version, columns, naive):
        self.source, self.relation, self.sentence, self.predicate = plan.source_id, plan.relation, sentence, predicate
        self.ends, self.qualifiers, self.required, self.kept = ends, qualifiers, required, kept
        self.basis, self.version, self.columns, self.plan, self.world_name = basis, version, columns, plan, None
        self.naive = naive
        self.attributes = frozenset()           # the qualifiers read from entity attributes - a blank one says nothing
        self.value = None                       # a value object's value - its spec (`_value`), None for any other
        self.time = plan.driver.occurred_at

    def key(self, spec) -> str:
        """The SQL that spells a column key - the join's own (`notation_norm.key_expression_text`)."""
        import notation_norm

        column = spec["column"]
        return notation_norm.key_expression_text(
            f"w.{_quoted(column)}", rules=notation_norm.rules_for_column(self.relation, column),
            text_column=spec["kind"] == _TEXT, zone=spec.get("zone"), number_column=spec["kind"] in _NUMBERS)

    def columns_of(self, arm) -> list:
        """[(key, spec)] of an end's column keys, in key order - the order a read selects and compares them in."""
        return [(key, spec) for key, spec in sorted(self.ends[arm][1].items()) if "column" in spec]

    def named(self, arm, entities) -> list:
        """[(entity, its column keys' texts in `columns_of` order)] of the `entities` [(type, keys, ...)] this end can
        name: its type, its key names, text for each (a key the SQL spells is text) and a constant key's own spelling."""
        bare, specs = self.ends[arm]
        out = []
        for item in entities:
            keys = item[1] or {}
            if item[0] != bare or set(keys) != set(specs):
                continue
            texts = []
            for key, spec in sorted(specs.items()):
                if not isinstance(keys[key], str) or keys[key] != spec.get("constant", keys[key]):
                    break
                if "column" in spec:
                    texts.append(keys[key])
            else:
                out.append((item, tuple(texts)))
        return out

    def said(self) -> list:
        """[SQL] - the rows that say something: kept, every key not blank as the SQL spells it, and the time there."""
        keys = {spec["column"]: spec for spec in self.required if "column" in spec}
        # one blank-key judge: the key as the join spells it, trimmed - `assy_key_number` / `assy_key_instant` give NULL
        # where `crud.is_blank_key_part` says blank (NaN, infinity, from KEY_EXACT_LIMIT, unreadable), btrim the spaces
        out = [*self.kept, *(f"btrim({self.key(spec)}) <> ''" for _column, spec in sorted(keys.items()))]
        return out + [f"{self.at()} IS NOT NULL"]

    def at(self) -> str:
        """The time as the SQL orders and bounds it."""
        return f"w.{_quoted(self.time.column)}"

    def edge(self, instant):
        """`instant` as the time column compares - itself, or its wall clock on the zone."""
        if self.naive:
            from zoneinfo import ZoneInfo

            return instant.astimezone(ZoneInfo(str(self.time.timezone))).replace(tzinfo=None)
        return instant

    def instant(self, value):
        """The time a row says, read by the translator's function (`_aware_time`), or None when it does not read."""
        from .event_frame import SourcePreparationError, _aware_time

        try:
            return _aware_time(value if hasattr(value, "tzinfo") else roleframe._plain(value), self.time.timezone,
                               f"read.{self.time.column}")
        except SourcePreparationError:
            return None


def _held(value, spec):
    """A frontier key value as the column holds it - text as it is, a number as the column's number, a time key
    (`zone`) on a time column as its instant (`expression._wall`, what `map_overlay.time_key_text` spells from; a
    zoneless column its wall clock there); None when it cannot be one."""
    if value is None:
        return None
    if spec.get("zone") and spec["kind"] in (_TIME, "timestamp without time zone"):
        import expression
        from utils.time_format import _zone

        moment = expression._wall(value, _zone(spec["zone"]))
        return moment if moment is None or spec["kind"] == _TIME else moment.replace(tzinfo=None)
    if spec.get("zone") or spec["kind"] == _TEXT:
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if spec["kind"] == _FLOAT:
        return number
    if spec["kind"] == _INTEGER:
        return int(number) if number.is_integer() else None
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _quoted(name) -> str:
    return '"%s"' % str(name).replace('"', '""')


def _literal(value) -> str:
    return "'%s'" % str(value).replace("'", "''")


def column_kinds(fetch, relation) -> dict:
    """{column: text | float | integer | numeric | time | its PostgreSQL type} of `relation` as the database holds it."""
    rows = fetch("SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                 "WHERE a.attrelid = to_regclass(%(relation)s) AND a.attnum > 0 AND NOT a.attisdropped",
                 {"relation": relation})
    kinds = {}
    for name, kind in rows:
        kinds[name] = (_TEXT if kind.startswith(("character", "text")) else
                       _FLOAT if kind in ("double precision", "real") else
                       _INTEGER if kind in ("integer", "bigint", "smallint") else
                       "numeric" if kind.startswith("numeric") else
                       _TIME if kind == "timestamp with time zone" else kind)
    return kinds


def _column(kinds, column, why):
    if column not in kinds:
        raise NotCompiled(f"{why}: column {column!r} is not in the table")
    return f"w.{_quoted(column)}", kinds[column]


def _present(kinds, column) -> str:
    """The cell is not blank (`is_blank_source_value`): NULL, a NaN, or text of spaces is blank."""
    cell, kind = _column(kinds, column, "a column the read names")
    if kind == _TEXT:
        return f"btrim({cell}) <> ''"
    if kind in _NUMBERS:
        return f"({cell} IS NOT NULL AND {cell}::float8 <> 'NaN'::float8)"
    return f"{cell} IS NOT NULL"


def _when(kinds, when, why) -> str:
    """`roleframe._unit_says` over one row: each column says its value (`when_says` - a blank cell is "", a value is
    `clean_str_value`'s), or `{"not": ...}` none of them. A text column only: storage holds it stripped."""
    from database.crud import clean_str_value

    said = []
    for column, expected in when.items():
        cell, kind = _column(kinds, column, why)
        if kind != _TEXT:
            raise NotCompiled(f"{why}: a `when` on a {kind} column")
        negated = isinstance(expected, dict)
        values = expected["not"] if negated else expected
        targets = ", ".join(sorted({_literal(clean_str_value(v)) for v in (
            values if isinstance(values, (list, tuple)) else (values,))}))
        said.append(f"coalesce({cell}, '') {'NOT ' if negated else ''}IN ({targets})")
    return " AND ".join(said) or "true"


def _key(relation, kinds, binding, why) -> dict:
    """One key part's spec - a constant spelled (`map_overlay.canonical_key_value`), or the column with its declared
    type, the database's kind and the zone a time column is read on."""
    import map_overlay

    if binding.get("kind") == "constant":
        return {"constant": map_overlay.canonical_key_value(roleframe._plain(binding.get("value")), None)}
    if binding.get("kind") != "column":
        raise NotCompiled(f"{why}: a key bound by {binding.get('kind')!r}")
    _cell, kind = _column(kinds, binding.get("column"), why)
    declared = map_overlay.declared_column_type(relation, binding.get("column"))
    zone = map_overlay.key_time_zone(relation, binding.get("column"))
    if not zone and kind not in _NUMBERS and (kind != _TEXT or declared == "number"):
        raise NotCompiled(f"{why}: a {declared or 'text'} key read from a {kind} column")
    return {"column": binding["column"], "declared": declared, "kind": kind, "zone": zone}


def _entity(relation, kinds, binding, why):
    """(bare type, {key: spec}) of an entity role."""
    from .setup_bundle import bare_name, entity_type_column

    if binding.get("kind") != "entity" or entity_type_column(binding):
        raise NotCompiled(f"{why}: an entity role bound by {binding.get('kind')!r} or a type read per row")
    return bare_name(binding["entity_type"]), {key: _key(relation, kinds, child, f"{why}.keys.{key}")
                                                for key, child in (binding.get("keys") or {}).items()}


def _naive(plan, kinds) -> bool:
    """Whether a leg's time column holds no zone - its SQL compares the wall clock on the declared one. The column holds
    a time (the validator refuses a source whose time column is not declared datetime, owner 11-07 «원장 소스에는
    datetime만»); a table not yet converted to its declaration is refused here."""
    occurred = plan.driver.occurred_at
    _cell, kind = _column(kinds, occurred.column, "read.occurred_at")
    if kind == _TIME:
        return False
    if kind == "timestamp without time zone":
        if not occurred.timezone:
            raise NotCompiled("read.occurred_at: a time without a zone - declare read.occurred_at.timezone")
        return True
    raise NotCompiled(f"read.occurred_at: a time read from a {kind} column")


def _missing(spec) -> str:
    """SQL: the cell of a value `spec` is missing - NULL, an empty text, a float NaN (`roleframe._is_missing`, spaces
    present)."""
    cell = f"w.{_quoted(spec['column'])}"
    return {_TEXT: f"({cell} IS NULL OR {cell} = '')", _FLOAT: f"({cell} IS NULL OR {cell} = 'NaN')"}.get(
        spec["kind"], f"({cell} IS NULL)")


def _value(kinds, binding, why) -> dict:
    """A value object's value or a qualifier's spec - a constant, or a text or number column read as it holds it (the
    stored compiler keeps the cell as it came, `roleframe._plain`; a qualifier's `roleframe._attribute_value`)."""
    if binding.get("kind") == "constant":
        return {"constant": roleframe._plain(binding.get("value"))}
    if binding.get("kind") != "column" or binding.get("timezone") or binding.get("format"):
        raise NotCompiled(f"{why}: a value bound by {binding.get('kind')!r} or read as a time")
    _cell, kind = _column(kinds, binding.get("column"), why)
    if kind not in (_TEXT, *_NUMBERS):
        raise NotCompiled(f"{why}: a value read from a {kind} column")
    return {"column": binding["column"], "kind": kind}


def compile_source(snapshot, plan, kinds, world) -> tuple:
    """(`plan`'s legs - a sentence each, each entity reference its entities carry, each registration its roles'
    attributes make - , what it does not read: «attributes of <type> not read», «<sentence>: a value object not read»,
    «<sentence>: qualifier <name> not read», each an engine.left_out line, its source still read) or `NotCompiled`.
    Attributes as the stored translator writes them (`roleframe`): a subject's attribute named as a qualifier of its sentence is that
    qualifier; a role the source registers (`registered_roles`) says «register» of its node with its attributes."""
    from collections.abc import Mapping

    import map_overlay

    from .setup_bundle import NOT_AN_EVENT_BASIS, REGISTER_PREDICATE, bare_name, is_event_time_role, is_registration
    from .setup_registry import REGISTRATION_DERIVATION_PREFIX

    if not plan.runs:
        raise NotCompiled("not planned: %s" % ((plan.refusal or {}).get("message") or plan.status))
    if not covers(plan):
        raise NotCompiled("its mapper is code")
    driver = plan.driver
    if driver.group_by or driver.mapper.unit_kind not in ("row", "event"):
        raise NotCompiled("a molecule of more than one row (read.group_by or map.unit)")
    context = roleframe.MapperContext(snapshot, plan)
    naive = _naive(plan, kinds)
    kept = [_present(kinds, column) for column in dict.fromkeys(
        (*driver.cursor_columns, *driver.identity,
         *(clause["column"] for clause in driver.exclude_when if clause.get("when") is None)))]
    kept += [f"NOT ({_when(kinds, clause['when'], 'read.exclude_when')})"
             for clause in driver.exclude_when if clause.get("when") is not None]
    legs, prefix, unread, registered = [], f"ledger-v2:{snapshot.snapshot_sha256}#", set(), set()
    for sentence, mapping in sorted(plan.profile.mappings.items()):
        emission_plan = roleframe._emission_plan(context, mapping.predicate_id, mapping.config_path)
        emission = emission_plan.emission
        # a sentence with no object (a registration) says its subject only - its object end is none (`NO_OBJECT`)
        objectless = is_registration(emission.object_kind)
        valued, value = emission.object_kind == "value", None
        if emission.object_kind != "entity_ref" and not objectless and not valued:
            unread.add(f"{sentence}: a {emission.object_kind} object not read")     # the sentence alone, not its source
            continue
        if valued:                              # no far node - its value is the atom's object (`roleframe`)
            try:
                value = _value(kinds, mapping.bindings[emission.object_role.role_id], f"{sentence}.value")
            except NotCompiled:
                unread.add(f"{sentence}: a value object not read")
                continue
        named = {role: mapping.bindings[reference.role_id]
                 for role, reference in (("subject", emission.subject), ("object", emission.object_role))
                 if not ((objectless or valued) and role == "object")}
        ends = {role: _entity(plan.relation, kinds, binding, f"{sentence}.{role}") for role, binding in named.items()}
        ends.setdefault("object", NO_OBJECT)
        qualifiers, from_attributes, needed, unsaid = {}, set(), [], None
        subject_attributes = named["subject"].get("attributes") or {}
        for name, reference in emission.qualifiers.items():
            binding = mapping.bindings.get(reference.role_id)
            attribute = binding is None and name in subject_attributes
            binding = subject_attributes[name] if attribute else binding
            if binding is None:
                continue
            role = emission_plan.claim.roles.get(reference.role_id)
            if role is None or (role.required and attribute):
                unsaid = f"{sentence}: qualifier {name} not read"           # the sentence alone, not its source
                break
            try:
                qualifiers[name] = _value(kinds, binding, f"{sentence}.{name}")
            except NotCompiled:
                if not attribute:
                    unsaid = f"{sentence}: qualifier {name} not read"
                    break
                unread.add(f"attributes of {ends['subject'][0]} not read")    # its value out, not the source
                continue
            if attribute:
                from_attributes.add(name)
            if role.required and "column" in qualifiers[name]:     # blank, it unsays this sentence alone
                needed.append(f"NOT {_missing(qualifiers[name])}")
        if unsaid:
            unread.add(unsaid)
            continue
        event = any(is_event_time_role(role) for role in mapping.bindings)
        basis = driver.occurred_at.basis if event else NOT_AN_EVENT_BASIS
        first = {"object": [], **{role: _text_columns(binding.get("keys") or {}, kinds) for role, binding in named.items()}}
        kept_here = [*kept, _when(kinds, dict(mapping.when), f"{sentence}.when")] if mapping.when else kept
        if value and "column" in value:         # a blank value unsays this sentence alone (`event_frame._blank_cells`)
            needed.append(f"NOT {_missing(value)}")
        kept_here = [*kept_here, *needed]
        said = [spec for _type, keys in ends.values() for spec in keys.values()]
        legs.append(Leg(plan, sentence, emission_plan.predicate_runtime_id,
                        {"outgoing": ends["subject"], "incoming": ends["object"]}, qualifiers, said, kept_here, basis,
                        prefix + sentence, {"outgoing": first["subject"], "incoming": first["object"]}, naive))
        legs[-1].attributes, legs[-1].value = frozenset(from_attributes), value
        for role_id in mapping.registered_roles:
            binding = mapping.bindings[role_id]
            end = _entity(plan.relation, kinds, binding, f"{sentence}.{role_id}")
            try:
                specs = {name: _value(kinds, child, f"{sentence}.{role_id}.attributes.{name}")
                         for name, child in sorted((binding.get("attributes") or {}).items())}
            except NotCompiled:
                unread.add(f"attributes of {end[0]} not read")
                continue
            # its time rule is the naming sentence's (`runtime_v2._stamp_occurred_at_basis`); one registration of a
            # node per row, as the translator makes one per molecule: the same end and
            # attributes on the same rows is the same atom (`roleframe._reference_rows`, «made»)
            once = (end[0], json.dumps(end[1], sort_keys=True), json.dumps(specs, sort_keys=True), tuple(kept_here))
            if once in registered:
                continue
            registered.add(once)
            derivation = f"{REGISTRATION_DERIVATION_PREFIX}{sentence}"
            legs.append(Leg(plan, derivation, REGISTER_PREDICATE, {"outgoing": end, "incoming": NO_OBJECT}, specs, said,
                            [*kept_here, _one_present(specs)], basis, prefix + derivation,
                            {"outgoing": _text_columns(binding.get("keys") or {}, kinds), "incoming": []}, naive))
            legs[-1].attributes = frozenset(specs)
        for role, binding in named.items():
            bare, keys = ends[role]
            for reference in getattr(snapshot.entities.get(binding["entity_type"]), "references", ()):
                own = {key: child for key, child in (binding.get("keys") or {}).items()}
                if any((own.get(key) or {}).get("kind") != "constant" for key, _value in reference.when):
                    raise NotCompiled(f"{sentence}.{role}: a reference whose `when` reads a column")
                if not all(roleframe.when_says(map_overlay.canonical_key_value(
                        roleframe._plain(own[key].get("value")), None), value) for key, value in reference.when):
                    continue
                target = {}
                for target_key, kind, value in reference.keys:
                    if kind == "key" and value not in keys:
                        raise NotCompiled(f"{sentence}.{role}: a reference to a key {value!r} it does not bind")
                    target[target_key] = keys[value] if kind == "key" else {
                        "constant": map_overlay.canonical_key_value(roleframe._plain(value), None)}
                pointed = {target_key: own.get(value) if kind == "key" else None
                           for target_key, kind, value in reference.keys}
                legs.append(Leg(plan, reference.derivation, bare_name(reference.predicate_id),
                                {"outgoing": (bare, keys), "incoming": (bare_name(reference.target_type), target)},
                                {}, said, kept_here, NOT_AN_EVENT_BASIS, prefix + reference.derivation,
                                {"outgoing": first[role], "incoming": _text_columns(pointed, kinds)}, naive))
    return legs, sorted(unread)


def _one_present(specs) -> str:
    """SQL: one of the attribute `specs` has a value - the translator registers a node only then (`_attribute_values`:
    a blank cell says nothing; `_missing`)."""
    said = ["true" if roleframe._is_missing(spec["constant"]) is False else "false" for spec in specs.values()
            if "constant" in spec]
    said += [f"NOT {_missing(spec)}" for spec in specs.values() if "column" in spec]
    return "(" + " OR ".join(said or ["false"]) + ")"


def _text_columns(keys, kinds):
    """The text columns an end's keys are read from as they are - what a table's index can serve the join on."""
    return [binding["column"] for _key, binding in sorted(keys.items())
            if (binding or {}).get("kind") == "column" and kinds.get(binding["column"]) == _TEXT]


def compile_world(snapshot, fetch, world) -> tuple:
    """(legs, left out [{source, world, why}]) of one world's declaration - `fetch(sql, params)` reads the tables'
    column types."""
    legs, left_out = [], []
    for source, plan in sorted(snapshot.source_plans.items()):
        try:
            kinds = column_kinds(fetch, plan.relation) if plan.runs else {}
            read, unread = compile_source(snapshot, plan, kinds, world)
            for leg in read:
                leg.world_name = world
                legs.append(leg)
            left_out.extend({"source": source, "world": world, "why": why} for why in unread)
        except NotCompiled as why:
            left_out.append({"source": source, "world": world, "why": str(why)})
    return legs, left_out


def main(argv=None) -> int:
    """`python -m ledger sql-shadow` - every page of every declarative source through both paths, read only; exit 1
    when the atoms, the refusals or a page's excluded rows by cause differ."""
    import argparse
    import json
    import sys

    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser(
        prog="python -m ledger sql-shadow",
        description="Translate every page by the Python path and the SQL path and compare the atoms (writes nothing)")
    parser.add_argument("--world", default=None, help="this world; the operating one when absent")
    parser.add_argument("--source", action="append", default=None, help="this source (repeatable); every one when absent")
    parser.add_argument("--page-rows", type=int, default=2000)
    parser.add_argument("--max-pages", type=int, default=None, help="stop each source after this many pages")
    parser.add_argument("--show", type=int, default=3, help="atoms shown per side when they differ")
    args = parser.parse_args(argv)

    from database.database import engine as live
    from . import schema
    from .setup import load_setup

    setup = load_setup(schema.require_world(args.world).declaration_root)
    engine = create_engine(live.url, connect_args={"options": "-c default_transaction_read_only=on"})
    plans = {name: plan for name, plan in setup.snapshot.source_plans.items() if plan.runs}
    wanted = args.source or sorted(plans)
    different = False
    for source in wanted:
        if source not in plans:
            print(json.dumps({"source": source, "skipped": "not a planned source"}, ensure_ascii=False))
            continue
        if not covers(plans[source]):
            print(json.dumps({"source": source, "skipped": "mapper is code - the Python path translates it"},
                             ensure_ascii=False))
            continue
        said = shadow_source(engine, setup, source, args.page_rows, args.max_pages, args.show)
        different = different or differs(said)
        print(json.dumps(said, ensure_ascii=False), flush=True)
    print("DIFFERENT" if different else "SAME", file=sys.stderr)
    return 1 if different else 0
