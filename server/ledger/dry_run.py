"""「이 선언이 낳을 원자」 - the REAL translators, over a connection that cannot write.

Ruling R-2026-08-15-M ⑥ makes the dry run the second of three save steps and the brief
spells out what it may not be: 「드라이런을 «샘플 미리보기»로 대충 하지 말 것 - 실제
번역기를 태운다. 가짜 미리보기는 조용한 거짓말이다.」 A preview that renders what the
declaration *says* rather than what the translator *does* is worse than none, because the
operator would approve a declaration on the strength of a screen that agreed with them by
construction.

WHAT IS REUSED, AND WHY THE DRIVER LOOP IS NOT
-----------------------------------------------
Everything that decides what an atom IS comes from `backfill`: its fetch functions, its
page/group cutting, its molecule grouping, the three translator classes, and
`gate.screen_molecule`. What is NOT reused is `backfill`'s driver loop, and the reason is
that the loop's job is precisely the part a dry run must not do - advance a cursor and
flush a batch. Reusing it with a `write=False` flag would put the write path one boolean
away from a preview, and this project has already paid for a flag that decides whether
something is real.

🔴 ZERO WRITES IS STRUCTURAL, NOT A PROMISE
--------------------------------------------
The connection's transaction is opened with `SET TRANSACTION READ ONLY` before anything
else runs, and `begin_read_only()` reads it back from PostgreSQL rather than trusting
that the statement was sent. Any INSERT/UPDATE/DDL on that transaction - including
`ensure_schema`'s `CREATE TABLE`, which is why it is deliberately not called - raises
`read-only sql transaction` (SQLSTATE 25006). The guarantee therefore does not depend on
this module never calling a writer; it depends on PostgreSQL refusing one.

TRANSACTION-SCOPED, NOT SESSION-SCOPED, and that is a pooling fact rather than a taste:
`engine.raw_connection()` hands back a POOLED connection, so
`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` would follow the connection back
into the pool and make somebody else's write fail. `SET TRANSACTION` dies with its
transaction, so a leaked one is impossible.

WHY IT ALWAYS READS FROM THE HEAD OF THE SOURCE
------------------------------------------------
The cursor is not consulted. The question the screen asks is "what does THIS DECLARATION
produce", not "what is left to do" - and on a source that is already fully translated a
cursor-respecting preview would show nothing at all, which reads as「선언이 아무것도 안
낳는다」when the truth is「이미 다 했다」. The consequence is worth naming rather than
hiding: registers the ledger already holds are suppressed by the translator exactly as
they would be in a real run, so `registers_suppressed` is reported.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging

logger = logging.getLogger("Ledger.DryRun")

#: How many SOURCE ROWS a preview reads. The brief says「소스 N행(예: 20행)」. Capped
#: rather than free, because this runs on the request path against a table that may hold
#: ten million rows and the page fetch is `LIMIT n` on a keyset - cheap at 20, and not a
#: thing an operator should be able to turn into a full scan by typing a big number.
DEFAULT_ROWS = 20
MAX_ROWS = 200

#: How many atoms come back in the envelope list. The COUNTS are always complete; this
#: caps only the rendering, and `truncated` says so rather than the list ending quietly.
MAX_ATOMS_RENDERED = 200


class DryRunUnavailable(RuntimeError):
    """The preview could not run at all. Carries the operator's sentence."""

    def __init__(self, detail_ko: str, detail_en: str = ""):
        super().__init__(detail_en or detail_ko)
        self.detail_ko = detail_ko


def begin_read_only(connection):
    """Open this connection's transaction READ ONLY and prove it took.

    Returns what PostgreSQL says, not what we asked for. `SHOW transaction_read_only`
    is the server's own answer, so a statement that silently did not apply (a driver in
    autocommit, a connection already inside a transaction) shows up here instead of
    showing up as a write.
    """
    # 🔴 `SET TRANSACTION` must be the FIRST statement of a transaction, and this
    # connection comes from a POOL. A connection handed back with work still open would
    # make the statement raise 25001 - and a raw driver error here would surface as a
    # 500 rather than as「쓰기 0을 보장할 수 없어 중단했습니다」. Ending whatever was open
    # costs one round trip and there is nothing of ours to lose: we have not run yet.
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SHOW transaction_read_only")
        return str(cursor.fetchone()[0]).lower() == "on"


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def envelope_of(atom) -> dict:
    """One atom, in ENVELOPE FORM. The brief's words:「원자 봉투 그대로」.

    Nothing is renamed, summarised or prettified. `derivation` and `molecule_ref` ride
    along because they are what the gate judged the atom BY - an operator looking at a
    preview needs to see which declared rule claimed the atom, and that field is exactly
    where a rule the config did not declare would be refused.
    """
    source_event_id = atom.source_event_id
    source_event_state = atom.source_event_state
    if source_event_id is None and source_event_state is None:
        from .envelope import source_event_identity
        source_event_id, source_event_state = source_event_identity(
            atom.source_who, atom.occurred_at,
            molecule_ref=atom.molecule_ref,
            source_raw_ref=atom.source_raw_ref)
    return {
        "source_event_id": str(source_event_id),
        "source_event_state": source_event_state,
        "subject_type": atom.subject_type,
        "subject_keys": atom.subject_keys,
        "predicate": atom.predicate,
        "object_kind": atom.object_kind,
        "object_payload": atom.object_payload,
        "occurred_at": _iso(atom.occurred_at),
        "source_who": atom.source_who,
        "source_translator_ver": atom.source_translator_ver,
        "source_raw_ref": atom.source_raw_ref,
        "supersedes": atom.supersedes,
        "derivation": atom.derivation,
        "molecule_ref": atom.molecule_ref,
    }


def _existing_registrations(store, connection, subjects, notes):
    """Registers the ledger already holds. A missing ledger is a NOTE, not a failure.

    A fresh box has no `ledger_events` table until the first real run creates it, and a
    preview that died there would be unusable exactly when it is most useful - before
    anything has ever been translated.
    """
    if not subjects:
        return set()
    try:
        return store.existing_registrations(connection, subjects)
    except Exception as exc:
        connection.rollback()
        begin_read_only(connection)
        notes.append(
            "원장 테이블을 아직 읽을 수 없어 기존 등록을 대조하지 못했습니다 — 미리보기의 "
            "register 원자 수는 실제 실행보다 많을 수 있습니다.")
        logger.info("[DryRun] existing_registrations unavailable: %s", exc)
        return set()


def preview(engine, cfg, source, rows: int = DEFAULT_ROWS) -> dict:
    """Translate the head of `source` under `cfg` and return what WOULD be written."""
    from . import config as ledger_config
    from . import gate
    from .store import LedgerStore

    rows = max(1, min(int(rows or DEFAULT_ROWS), MAX_ROWS))
    source_cfg = ledger_config.source_config(cfg, source)
    if source_cfg is None:
        raise DryRunUnavailable(
            f"'{source}'에 대한 선언이 없습니다.",
            f"no declaration for source {source!r}")
    kind = source_cfg.get("kind", ledger_config.SOURCE_KIND_LINEAGE)

    store = LedgerStore(engine)
    connection = store.connection()
    try:
        read_only = begin_read_only(connection)
        if not read_only:
            # Refuse rather than proceed: everything below drives the real writers'
            # code paths, and the only thing standing between a preview and a write is
            # this setting having taken.
            raise DryRunUnavailable(
                "읽기 전용 트랜잭션을 열지 못해 드라이런을 중단했습니다 — 쓰기 0을 "
                "보장할 수 없는 미리보기는 실행하지 않습니다.",
                "could not open a READ ONLY transaction")

        notes = []
        with gate.captured() as captured:
            if kind == ledger_config.SOURCE_KIND_OBSERVATION:
                out = _preview_observation(store, connection, cfg, source, source_cfg,
                                           rows, notes)
            elif kind == ledger_config.SOURCE_KIND_TRANSFER:
                out = _preview_transfer(store, connection, cfg, source, source_cfg,
                                        rows, notes)
            elif kind == ledger_config.SOURCE_KIND_DECLARED:
                out = _preview_declared(store, connection, cfg, source, source_cfg,
                                        rows, notes)
            else:
                out = _preview_lineage(store, connection, cfg, source, source_cfg,
                                       rows, notes)

        out["kind"] = kind
        out["source"] = source
        out["writes"] = 0
        out["read_only_enforced"] = True
        out["notes"] = notes
        out["refusals"] = [
            {"reason": sample["reason"], "detail": sample["detail"],
             "source_rows": sample["rows"], "built_atoms_discarded": sample["atoms"]}
            for sample in captured.get("samples") or []]
        out["refusals_by_reason"] = {
            reason: count for (src, reason), count in
            (captured.get("refusals") or {}).items() if src == source}
        rendered = out.pop("_atoms", [])
        out["truncated"] = len(rendered) > MAX_ATOMS_RENDERED
        out["atoms_rendered"] = rendered[:MAX_ATOMS_RENDERED]
        return out
    finally:
        # Rollback rather than commit, though the transaction is read-only and there is
        # nothing to roll back: one exit path, and it is the one that cannot commit.
        try:
            connection.rollback()
        finally:
            connection.close()


def _finish(translator_ver, rows_read, molecules, refused, incomplete,
            atoms, registers_suppressed):
    return {
        "translator_ver": translator_ver,
        "rows_read": rows_read,
        "molecules": molecules,
        "molecules_refused": refused,
        "molecules_incomplete": incomplete,
        "atoms": len(atoms),
        "atoms_by_predicate": _by_predicate(atoms),
        "registers_suppressed": registers_suppressed,
        "_atoms": [envelope_of(atom) for atom in atoms],
    }


def _by_predicate(atoms):
    out = {}
    for atom in atoms:
        out[atom.predicate] = out.get(atom.predicate, 0) + 1
    return dict(sorted(out.items()))


def _screen(gate, source, translator, molecule, atoms, declared, declared_subjects,
            source_rows):
    """The gate, called exactly as the drivers call it. Returns `(kept, refused)`."""
    from .backfill import _forget_registers
    try:
        kept, _report = gate.screen_molecule(
            source, atoms, declared, declared_subjects,
            molecule_ref=molecule.ref, source_rows=source_rows)
        return kept, False
    except gate.MoleculeRefused:
        _forget_registers(translator, atoms)
        return [], True


# ------------------------------------------------------------------ lineage preview
def _preview_lineage(store, connection, cfg, source, source_cfg, rows, notes):
    from . import config as ledger_config
    from . import gate
    from .backfill import fetch_page, fetch_group, walk_group_pages, _forget_registers
    from .chain_mapper import (
        LedgerMapperContext,
        LedgerMapperError,
        LedgerMapperRefused,
        configured_mapper,
        deterministic_source_event_context,
        mapper_execution_version,
        run_registered_mapper,
    )
    from .envelope import canonical_keys
    from .ledger_frame import atoms_from_ledger_frame
    from mappers.ledger_lot_event_mapper import group_lot_event_frames

    translator_ver = ledger_config.translator_version(cfg, source)
    mapper_descriptor = configured_mapper(source_cfg)
    selected_profile = ledger_config.selected_profile(cfg, source)
    if mapper_descriptor is None:
        from .lot_event_translator import LotEventTranslator, group_molecules
    profile_id = ((source_cfg.get("chain_mapper") or {}).get("profile_id")
                  if selected_profile is not None else None)
    execution_ver = mapper_execution_version(
        translator_ver, mapper_descriptor,
        profile_id=profile_id, profile=selected_profile)
    mapper_context = LedgerMapperContext()
    if selected_profile is not None:
        from .profile_lookup_adapters import default_profile_lookup_adapters
        mapper_context = LedgerMapperContext(
            lookups=default_profile_lookup_adapters(store.engine))
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)

    columns = dict(source_cfg["columns"])
    columns["event_time_column"] = source_cfg["occurred_at_column"]

    pages = walk_group_pages(
        lambda position: fetch_page(connection, source, columns, position, rows),
        lambda event_time: fetch_group(connection, source, columns, event_time),
        "event_time", None, rows)
    complete = []
    for page, _next_after, _last in pages:
        complete = page
        break                      # ONE page - a preview, not a sweep

    translator = (None if mapper_descriptor is not None else
                  LotEventTranslator(source_cfg, translator_ver, declared, who=source))
    molecules = (group_lot_event_frames(complete)
                 if mapper_descriptor is not None else group_molecules(complete))

    subjects = set()
    for molecule in molecules:
        source_rows = (molecule.to_dict(orient="records")
                       if mapper_descriptor is not None else molecule.rows)
        lots = {row["lot"] for row in source_rows}
        if mapper_descriptor is not None:
            lots.update(row["parent_lot"] for row in source_rows)
            lots.update(row["child_lot"] for row in source_rows)
        else:
            lots.update({molecule.parent, molecule.child})
        for lot in lots:
            if lot:
                subjects.add(("Lot", canonical_keys({"lot": lot})))
        for row in source_rows:
            for wafer in str(row["wafers"] or "").split(
                    source_cfg.get("list_separator", ":")):
                if wafer.strip():
                    subjects.add(("Wafer", canonical_keys({"wafer": wafer.strip()})))
    known = _existing_registrations(store, connection, subjects, notes)
    mapper_registered = set(known)
    if mapper_descriptor is None:
        translator.registered |= known

    kept_all, refused, incomplete = [], 0, 0
    for molecule in molecules:
        atoms, report, was_refused = None, None, False
        source_rows = (molecule.to_dict(orient="records")
                       if mapper_descriptor is not None else molecule.rows)
        try:
            with gate.building_molecule(source):
                if mapper_descriptor is not None:
                    input_frame = molecule
                    source_event = deterministic_source_event_context(
                        source, source_rows, identity_fields=("row_identity",))
                    mapper_rule = {
                        "source": source,
                        "source_config": source_cfg,
                        "translator_version": translator_ver,
                        "declared_derivations": declared,
                        "registered_entities": tuple(mapper_registered),
                        "source_event": source_event,
                    }
                    if selected_profile is not None:
                        mapper_rule.update({
                            "profile_id": profile_id,
                            "profile": selected_profile,
                        })
                    mapped = run_registered_mapper(
                        mapper_descriptor.mapper_id,
                        mapper_descriptor.version,
                        input_frame,
                        context=mapper_context,
                        rule=mapper_rule,
                    )
                    report = dict(mapped.attrs.get("mapper_report") or {})
                    atoms = atoms_from_ledger_frame(mapped)
                else:
                    atoms, report = translator.translate(molecule)
                was_refused = atoms is None
                if not was_refused:
                    if mapper_descriptor is not None:
                        gate_derivations = declared
                        gate_subject_types = declared_subjects
                        if selected_profile is not None:
                            contract = mapped.attrs.get("gate_contract")
                            if not isinstance(contract, Mapping):
                                raise LedgerMapperError(
                                    "mapper_gate_contract_missing",
                                    "ledger_frame.attrs.gate_contract",
                                    "canonical Profile mapper must declare its gate contract")
                            gate_derivations = frozenset(
                                contract.get("declared_derivations") or ())
                            gate_subject_types = frozenset(
                                contract.get("declared_subject_types") or ())
                            if atoms and (
                                    not gate_derivations or not gate_subject_types):
                                raise LedgerMapperError(
                                    "mapper_gate_contract_invalid",
                                    "ledger_frame.attrs.gate_contract",
                                    "canonical Profile gate contract must name derivations and subjects")
                        kept, _screen_report = gate.screen_molecule(
                            source, atoms, gate_derivations, gate_subject_types,
                            molecule_ref=(report or {}).get("molecule"),
                            source_rows=len(source_rows))
                        was_refused = False
                    else:
                        kept, was_refused = _screen(
                            gate, source, translator, molecule, atoms, declared,
                            declared_subjects, len(molecule.rows))
                    kept_all.extend(kept)
                    if mapper_descriptor is not None:
                        for atom in kept:
                            if atom.predicate == "register":
                                mapper_registered.add((
                                    atom.subject_type,
                                    canonical_keys(atom.subject_keys),
                                ))
        except LedgerMapperRefused as refusal:
            was_refused = True
            reason = (refusal.code if refusal.code in gate.REFUSAL_REASONS
                      else gate.REFUSE_ATOMICITY)
            gate.refuse(source, reason, refusal.message, rows=len(source_rows))
        except gate.MoleculeRefused:
            was_refused = True
            if mapper_descriptor is None:
                _forget_registers(translator, atoms)
        if was_refused:
            refused += 1
        elif report and report.get("incomplete"):
            incomplete += 1
    return _finish(execution_ver, len(complete), len(molecules), refused,
                   incomplete, kept_all, len(known))


# -------------------------------------------------------------- observation preview
def _preview_observation(store, connection, cfg, source, source_cfg, rows, notes):
    from . import config as ledger_config
    from . import gate
    from .backfill import (fetch_observation_page, fetch_runs, _forget_registers)
    from .envelope import canonical_keys
    from .observation_translator import ObservationMolecule, ObservationTranslator

    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)

    declared_classes = ()
    if (source_cfg.get("columns") or {}).get("class"):
        try:
            import finding_kinds
            declared_classes = finding_kinds.classes(source_cfg.get("finding_kind"))
        except Exception as exc:
            notes.append(
                f"class 컬럼을 선언했지만 종류 레지스트리를 읽지 못했습니다 — 발화된 "
                f"class는 전부 거절됩니다 ({exc.__class__.__name__}).")

    source_rows = fetch_observation_page(connection, source, source_cfg, None, rows)
    runs = fetch_runs(connection, source_cfg,
                      {r["run_key"] for r in source_rows if r.get("run_key")})
    subjects = {("Wafer", canonical_keys({"wafer": str(r["wafer"]).strip()}))
                for r in source_rows if str(r.get("wafer") or "").strip()}
    known = _existing_registrations(store, connection, subjects, notes)

    translator = ObservationTranslator(source, source_cfg, translator_ver, declared,
                                       declared_classes=declared_classes)
    translator.registered |= known

    kept_all, refused = [], 0
    for row in source_rows:
        molecule = ObservationMolecule(source, row)
        atoms, was_refused = None, False
        try:
            with gate.building_molecule(source):
                atoms, _report = translator.translate(molecule, runs)
                was_refused = atoms is None
                if not was_refused:
                    kept, was_refused = _screen(gate, source, translator, molecule,
                                                atoms, declared, declared_subjects, 1)
                    kept_all.extend(kept)
        except gate.MoleculeRefused:
            was_refused = True
            _forget_registers(translator, atoms)
        if was_refused:
            refused += 1
    return _finish(translator_ver, len(source_rows), len(source_rows),
                   refused, 0, kept_all, len(known))


# ----------------------------------------------------------------- declared preview
def _preview_declared(store, connection, cfg, source, source_cfg, rows, notes):
    """🔴 THE PREVIEW THAT MATTERS MOST, because this kind has no Python class reviewing
    its output. For the other three grammars a reader can go and read the translator; for
    this one the declaration IS the translator, so seeing the atoms is the only way to know
    what was declared. This is the screen the round exists to make honest."""
    from . import config as ledger_config
    from . import gate
    from .backfill import fetch_declared_page, _forget_registers, _plain
    from .declared_translator import DeclaredMolecule, DeclaredTranslator
    from .envelope import canonical_keys

    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)

    source_rows = fetch_declared_page(connection, source, source_cfg, None, rows)
    translator = DeclaredTranslator(source, source_cfg, translator_ver, declared)

    subjects = set()
    for row in source_rows:
        for rule in (source_cfg.get("emit") or []):
            subject = rule.get("subject") or {}
            if subject.get("type") not in translator.register_types:
                continue
            try:
                keys = {k: _plain(v, row) for k, v in (subject.get("keys") or {}).items()}
            except KeyError:
                continue
            if all(str(v or "").strip() for v in keys.values()):
                subjects.add((subject["type"], canonical_keys(keys)))
    known = _existing_registrations(store, connection, subjects, notes)
    translator.registered |= known

    kept_all, refused = [], 0
    for row in source_rows:
        molecule = DeclaredMolecule(source, row)
        atoms, was_refused = None, False
        try:
            with gate.building_molecule(source):
                atoms, _report = translator.translate(molecule)
                was_refused = atoms is None
                if not was_refused:
                    kept, was_refused = _screen(gate, source, translator, molecule,
                                                atoms, declared, declared_subjects, 1)
                    kept_all.extend(kept)
        except gate.MoleculeRefused:
            was_refused = True
            _forget_registers(translator, atoms)
        if was_refused:
            refused += 1

    if translator.rows_matching_nothing:
        # 🔴 The silent outcome, made loud. A declaration whose `when` clauses match no row
        # produces zero atoms and NO refusal - it looks exactly like a source with nothing
        # to say. On a preview of 20 rows that is the single most likely mistake, so it is
        # a sentence rather than a number the operator has to notice.
        notes.append(
            f"읽은 {len(source_rows)}행 중 {translator.rows_matching_nothing}행은 어떤 "
            f"emit 규칙에도 걸리지 않아 원자를 만들지 않았습니다 — 거절이 아니라 "
            f"«해당 없음»입니다. 전부 그렇다면 `when` 조건을 다시 보세요.")

    out = _finish(translator_ver, len(source_rows), len(source_rows), refused, 0,
                  kept_all, len(known))
    out["rows_matching_nothing"] = translator.rows_matching_nothing
    return out


# ----------------------------------------------------------------- transfer preview
def _preview_transfer(store, connection, cfg, source, source_cfg, rows, notes):
    from . import config as ledger_config
    from . import gate
    from .backfill import (fetch_transfer_page, fetch_transfer_group, fetch_containers,
                           walk_group_pages, _group_transfer_rows, _forget_registers)
    from .envelope import canonical_keys
    from .transfer_translator import TransferTranslator

    translator_ver = ledger_config.translator_version(cfg, source)
    declared = ledger_config.declared_derivations(cfg, source)
    declared_subjects = ledger_config.declared_subject_types(cfg, source)

    pages = walk_group_pages(
        lambda position: fetch_transfer_page(connection, source, source_cfg, position,
                                             rows),
        lambda group_key: fetch_transfer_group(connection, source, source_cfg,
                                               group_key),
        "group_key", None, rows)
    complete = []
    for page, _next_after, _last in pages:
        complete = page
        break

    molecules = _group_transfer_rows(source, complete)
    containers = fetch_containers(connection, source_cfg,
                                  {m.group_key for m in molecules})
    subjects = {("Wafer", canonical_keys({"wafer": str(r["wafer"]).strip()}))
                for r in complete if str(r.get("wafer") or "").strip()}
    known = _existing_registrations(store, connection, subjects, notes)

    translator = TransferTranslator(source, source_cfg, translator_ver, declared)
    translator.registered |= known

    kept_all, refused, incomplete = [], 0, 0
    for molecule in molecules:
        atoms, report, was_refused = None, None, False
        try:
            with gate.building_molecule(source):
                atoms, report = translator.translate(molecule, containers)
                was_refused = atoms is None
                if not was_refused:
                    kept, was_refused = _screen(gate, source, translator, molecule,
                                                atoms, declared, declared_subjects,
                                                len(molecule.rows))
                    kept_all.extend(kept)
        except gate.MoleculeRefused:
            was_refused = True
            _forget_registers(translator, atoms)
        if was_refused:
            refused += 1
        elif report and report.get("incomplete"):
            incomplete += 1
    return _finish(translator_ver, len(complete), len(molecules), refused,
                   incomplete, kept_all, len(known))
