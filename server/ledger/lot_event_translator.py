"""`lot_event` -> lineage atoms. The first translator, and the shape the next ones copy.

WHY `lot_event` IS THE SEED (design §10 step 1)
------------------------------------------------
It is ALREADY an event table. No state-to-event inference is needed, and `event_time`
gives `occurred_at` directly rather than through a reconstruction that could be wrong.

WHAT ONE SOURCE EVENT ACTUALLY LOOKS LIKE - and why it is not one row
---------------------------------------------------------------------
`table_config.json`'s own comment on `lot_event` states it, and the fixture generator
(`server/trace_fixture/world.py:_lineage`) does it: **one split or merge writes TWO
rows**. The parent's row carries `child_lot` with `parent_lot` blank; the child's row
carries `parent_lot` with `child_lot` blank. There is no event id on the source, so the
pair is matched by `(event_type, event_time, parent, child)` - all four, because two
different lots can move at the same instant.

That pair is the MOLECULE and therefore the transaction unit. A translator that treated
each row as an event would emit `derived_from` twice for one split and could never pair
slots at all, because pairing needs both sides.

WHAT THE TWO ROWS SAY - measured, not assumed
----------------------------------------------
Read off the generator, and confirmed against the 43 rows in the isolated database:

  * **split** - both rows are POST-event membership snapshots. The moved wafers are on
    the child's row and have already left the parent's, so **no wafer is uttered on both
    sides**. Measured overlap across all 14 split molecules: 0, every time.
  * **merge** - the source lot's row is a PRE-move snapshot and the destination's row is
    POST-move, so the moved wafers ARE on both. Measured overlap: 13, 0, 3, 5 (the 0 is
    a merge where the destination had no free slots, so nothing actually moved - the
    translator emitting nothing there is correct, not a miss).

🔴 THE ONE JUDGEMENT CALL, AND WHERE IT LIVES
----------------------------------------------
Because a split utters no shared wafer, `slot_map` for a split can only come from a
CONVENTION: "a split keeps slot numbers", which is the product owner's own worked
example (quoted in `world.py:_lineage`). Atomicity check ③ asks whether the atom records
the utterance rather than the conclusion, so this translator refuses to hold that
convention itself. It is declared in `ledger_config.json` per event type, the declaration
is hashed into `source_translator_ver` (so every atom says which convention made it), and
`source_raw_ref` names the source rows so the atoms can be re-derived if the convention
is ever found false. Setting `slot_pairing` to `shared_wafer` takes the zero-inference
position and yields no `slot_map` for splits at all.

A REFUSAL IS NEVER PARTIAL - ruling R-2026-08-13-H
---------------------------------------------------
Every refusal below goes through `gate.refuse` inside `gate.building_molecule`, which
raises `MoleculeRefused` and unwinds the whole molecule. No helper returns a "refused"
sentinel any more, because a sentinel is only as good as the call site that reads it and
one of them read `... or []`: the gate counted an `atomicity_violation`, the log said the
row produced nothing, and three atoms of that same molecule landed. Per-fragment survival
is what `incomplete` is for - a true but incomplete utterance - and it is not what
`refuse` means.

AN INCOMPLETE MOLECULE IS NOT A REFUSAL
----------------------------------------
The isolated database contains a real instance: someone retyped `child_lot` in the grid,
so one merge's two rows no longer name the same pair and each is now a molecule of one.
Both halves still utter true claims and destroying them would destroy evidence. They are
translated, and counted as `incomplete` - which is the number that explains a lineage
chain with a hole in it, and is exactly what §3-2's "끊긴 자리가 이유와 함께" needs.
"""
from __future__ import annotations

import json
import logging

from . import gate, vocabulary
from .config import DEFAULT_OCCURRED_AT_FORMAT
from .envelope import Atom, canonical_keys, entity_ref
from .store import parse_occurred_at

logger = logging.getLogger("Ledger.LotEvent")

SOURCE = "lot_event"


class Molecule:
    """One source event: its key, its rows, and where it sits in the cursor's order."""

    __slots__ = ("event_type", "event_time", "parent", "child", "ambiguous", "rows")

    def __init__(self, event_type, event_time, parent, child, ambiguous=None):
        self.event_type = event_type
        self.event_time = event_time
        self.parent = parent
        self.child = child
        #: The row identity, when this "molecule" is really one row that named BOTH
        #: sides of the pair. Such a row cannot be grouped at all - there is no way to
        #: know which pair it belongs to - so it is isolated here and refused in
        #: `translate`. Isolating it rather than picking a side is the whole point: a
        #: silent pick would attach 25 wafers to a lineage the source never asserted.
        self.ambiguous = ambiguous
        self.rows = []

    @property
    def ref(self) -> str:
        """The non-semantic correlation marker (design §3's excluded list).

        It never becomes a column and no consumer may read it. It exists so the gate can
        decide all-or-nothing and so a refusal in the log can be traced back to one
        source event by hand.
        """
        return json.dumps([self.event_type, self.event_time, self.parent, self.child,
                           self.ambiguous],
                          ensure_ascii=False, separators=(",", ":"))

    @property
    def is_complete(self) -> bool:
        """A lineage event should have both sides. `track_in` legitimately has one."""
        if not (self.parent and self.child):
            return True
        return len(self.rows) >= 2

    def parent_row(self):
        """The row whose OWN lot is the parent - i.e. the one carrying `child_lot`."""
        for row in self.rows:
            if row["lot"] == self.parent:
                return row
        return None

    def child_row(self):
        for row in self.rows:
            if row["lot"] == self.child:
                return row
        return None


def molecule_key(row):
    """`(event_type, event_time, parent, child, ambiguous)` for one source row.

    A row names ONE side of the pair and the key derives the other from it, which is what
    makes the two rows of an event land on the same key. A row naming neither side (a
    `track_in`) keys on itself with no parent, so it is a molecule of one by construction
    rather than by exception.

    🔴 A row that names BOTH gets its own key, carrying its row identity so it cannot
    join anyone else's molecule. The isolated live database contains one: a hand edit in
    the grid put a value in `child_lot` on a row that already had `parent_lot`, and the
    row now asserts two different lineages at once. Reading `parent_lot` first and
    ignoring the other field - which is what any "check parent, else check child" order
    does - would silently attach that row's 25 wafers to one of the two and never
    mention the other. The gate refuses it instead, by name.
    """
    lot = (row["lot"] or "").strip()
    parent = (row["parent_lot"] or "").strip()
    child = (row["child_lot"] or "").strip()
    if parent and child:
        return (row["event_type"], row["event_time"], parent, child,
                str(row["row_identity"]))
    if parent:
        return (row["event_type"], row["event_time"], parent, lot, None)
    if child:
        return (row["event_type"], row["event_time"], lot, child, None)
    return (row["event_type"], row["event_time"], None, lot, None)


def group_molecules(rows):
    """Source rows (already in cursor order) -> molecules, order preserved."""
    molecules = {}
    order = []
    for row in rows:
        key = molecule_key(row)
        molecule = molecules.get(key)
        if molecule is None:
            molecule = Molecule(*key)
            molecules[key] = molecule
            order.append(key)
        molecule.rows.append(row)
    return [molecules[key] for key in order]


def _split_list(text, separator):
    if text is None:
        return []
    text = str(text)
    if text == "":
        return []
    return text.split(separator)


class LotEventTranslator:
    """Stateless per call except for the registration memo, which is a run-scoped cache.

    `registered` is seeded from the ledger once per batch by the caller
    (`store.existing_registrations`) and then grown as the run emits registers, so a lot
    that appears in fifty molecules is registered once without fifty lookups.
    """

    def __init__(self, source_cfg, translator_ver, declared_derivations, who=SOURCE):
        self.cfg = source_cfg
        self.translator_ver = translator_ver
        self.declared = declared_derivations
        self.who = who
        self.separator = source_cfg.get("list_separator", ":")
        self.time_column = source_cfg["occurred_at_column"]
        self.time_format = source_cfg.get("occurred_at_format",
                                          DEFAULT_OCCURRED_AT_FORMAT)
        self.timezone_name = source_cfg["occurred_at_timezone"]
        # No `self.subject_type`. Each atom below names its own type as a literal, because
        # the code owns the FACT of the atom; what the config owns is the allowed RANGE
        # (`subject_types`), and `gate` is where that is enforced. The field used to be
        # read into here and used nowhere - ruling R-2026-08-13-D.
        self.register_types = frozenset(source_cfg.get("register_entity_types") or ())
        self.registered = set()
        #: The memos this molecule added, so a refusal can take them back. A refused
        #: molecule that leaves its lots memoised is the same defect one move later: the
        #: register atom was never written, and the NEXT molecule mentioning that lot
        #: finds the memo, emits no register, and the entity is never registered at all.
        #: A list rather than a snapshot of `registered` - the memo holds one entry per
        #: distinct entity in the whole run and copying it per molecule is what makes a
        #: ten-million row backfill quadratic.
        self._registered_here = []
        self.blank_wafer_positions = 0

    # ------------------------------------------------------------------- atom makers
    def _atom(self, molecule, predicate, subject_type, subject_keys, occurred_at,
              raw_rows, derivation, object_kind=None, object_payload=None):
        return Atom(
            subject_type=subject_type,
            subject_keys=subject_keys,
            predicate=predicate,
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=self.who,
            # 🔴 `<source>/<cfg version>/rules:<hash>#<derivation>` - the RULE that made
            # THIS atom, not merely the rule set the run was configured with. No column
            # is added for it (the slice's contract is eleven columns and adding a
            # twelfth is a ruling, not an implementation detail), and the field's own
            # meaning already covers it: "which translator produced this claim".
            #
            # What it buys is the thing the `slot_preserving` judgement most needs -
            # the convention becomes queryable:
            #     WHERE source_translator_ver LIKE '%#slot_preserving'
            # separates the atoms that rest on a declared convention from the ones that
            # rest on something the source uttered outright. Without it that distinction
            # is only recoverable by going back through `raw_ref` to the source row and
            # re-deriving its event type.
            source_translator_ver=f"{self.translator_ver}#{derivation}",
            source_raw_ref=raw_ref(raw_rows),
            molecule_ref=molecule.ref,
            derivation=derivation,
        )

    def _register(self, molecule, entity_type, keys, occurred_at, rows):
        """A `register` atom on first sight, or `None` if this entity already has one.

        `Die` is absent from `register_entity_types` on purpose - it is a COMPOSED entity
        (§5 rule 3) and registering it would mean one atom per die.
        """
        if entity_type not in self.register_types:
            return None
        if not vocabulary.requires_register(entity_type):
            return None
        memo = (entity_type, canonical_keys(keys))
        if memo in self.registered:
            return None
        self.registered.add(memo)
        self._registered_here.append(memo)
        return self._atom(molecule, "register", entity_type, keys, occurred_at, rows,
                          "first_sight")

    # ---------------------------------------------------------------------- the work
    def translate(self, molecule):
        """One molecule -> `(atoms, report)`. Atoms are NOT yet screened by the gate.

        Returns `(None, report)` when the molecule was refused ANYWHERE below - at the
        door (an undeclared `event_type`, an unparseable time, a missing identity) or
        part way through building its atoms (an unequal positional pairing found while
        making a `slot_map`). The gate has already counted it by then; the caller only
        has to not write anything.

        🔴 THE ONE-WAY DOOR IS HERE, and it is a `try` rather than a convention (ruling
        R-2026-08-13-H). Inside `gate.building_molecule` every `gate.refuse` raises, so a
        refusal in any helper - including one written next year - unwinds past every
        `atoms.append` and lands on this handler with nothing accumulated. There is no
        expression a future author can write in `_build` that swallows it, which is the
        difference between this fix and returning `[]` from `_slot_map`.
        """
        report = {"molecule": molecule.ref, "refused": False, "reason": None,
                  "atoms": 0, "incomplete": not molecule.is_complete}
        self._registered_here = []
        try:
            with gate.building_molecule(SOURCE):
                atoms = self._build(molecule)
        except gate.MoleculeRefused as refusal:
            self._forget_this_molecules_registers()
            report.update(refused=True, reason=refusal.reason)
            return None, report

        # The molecule stands, so its memos stand with it. Emptied here rather than left
        # lying around so the list only ever describes a molecule IN FLIGHT - a stale one
        # would let a later call give back registers that were written.
        self._registered_here = []

        report["atoms"] = len(atoms)
        # `incomplete` is REPORTED here and COUNTED by the caller. The caller is the only
        # place that knows whether the gate went on to refuse this molecule, and a
        # molecule that never landed must not appear in both buckets - adding the two
        # would then exceed the number of source events.
        return atoms, report

    def _forget_this_molecules_registers(self):
        """Give back the memos of a molecule that landed nothing.

        Nothing was written, so a lot left marked "already registered" by a REFUSED
        molecule is registered nowhere: the next molecule that mentions it finds the memo
        and emits no register either. That is the half-refusal one move on - the molecule
        stored no atom and still left a mark that changes what later molecules write.
        `backfill._forget_registers` does the same job for the refusals the gate makes
        after `translate` has already returned.
        """
        for memo in self._registered_here:
            self.registered.discard(memo)
        self._registered_here = []

    def _build(self, molecule):
        """The atoms of one molecule, or a raised `gate.MoleculeRefused`.

        Never returns a refusal. Every exit is either a list of atoms or an unwind, which
        is what makes `translate`'s handler the ONLY place a refusal can be turned back
        into a value - and why the checks below simply refuse and carry on reading as if
        the refusal ended the function, because it does.

        The precondition is checked rather than assumed: run outside the scope, every
        `gate.refuse` here would merely COUNT and execution would continue past a check
        that was supposed to stop it. That is the swallow again, one level up.
        """
        if not gate.molecule_is_open():
            raise RuntimeError(
                "_build must run inside gate.building_molecule() - outside it a refusal "
                "counts without aborting, which is the defect ruling R-2026-08-13-H "
                "removed. Call translate().")

        if molecule.ambiguous:
            row = molecule.rows[0] if molecule.rows else {}
            gate.refuse(SOURCE, gate.REFUSE_AMBIGUOUS_PAIR,
                        f"row {molecule.ambiguous!r} fills BOTH "
                        f"{self.cfg['columns']['parent_lot']}="
                        f"{row.get('parent_lot')!r} and "
                        f"{self.cfg['columns']['child_lot']}="
                        f"{row.get('child_lot')!r}. One row may name one side of a pair; "
                        f"naming both asserts two lineages and nothing in the row says "
                        f"which event it belongs to. Picking one would attach this row's "
                        f"wafers to a lineage the source never asserted, so nothing is "
                        f"written for it.",
                        rows=len(molecule.rows))

        rule = (self.cfg.get("vocabulary") or {}).get(molecule.event_type)
        if rule is None:
            gate.refuse(SOURCE, gate.REFUSE_UNDECLARED_VOCABULARY,
                        f"event_type={molecule.event_type!r} is not declared for this "
                        f"source (declared: "
                        f"{', '.join(sorted(self.cfg.get('vocabulary') or {}))}); "
                        f"{len(molecule.rows)} source row(s) at "
                        f"{molecule.event_time} produced nothing",
                        rows=len(molecule.rows))

        occurred_at = parse_occurred_at(molecule.event_time, self.time_format,
                                        self.timezone_name)
        if occurred_at is None:
            gate.refuse(SOURCE, gate.REFUSE_MISSING_OCCURRED_AT,
                        f"{self.time_column}={molecule.event_time!r} does not parse as "
                        f"{self.time_format!r}; arrival time is NOT substituted "
                        f"(design §10 risk 1)",
                        rows=len(molecule.rows))

        atoms = []
        lineage = rule.get("lineage", "none")
        pairing = rule.get("slot_pairing", "none")

        # --- identity of the lots this molecule talks about -----------------------
        lots = [lot for lot in ({row["lot"] for row in molecule.rows}
                                | {molecule.parent, molecule.child}) if lot]
        if not lots:
            gate.refuse(SOURCE, gate.REFUSE_NO_IDENTITY,
                        f"no lot value on any of the {len(molecule.rows)} row(s) of "
                        f"molecule {molecule.ref}",
                        rows=len(molecule.rows))

        for lot in sorted(lots):
            atom = self._register(molecule, "Lot", {"lot": lot}, occurred_at,
                                  molecule.rows)
            if atom:
                atoms.append(atom)

        # --- has_wafer, straight off each row's positional pairs -------------------
        if rule.get("emit_has_wafer", True):
            for row in molecule.rows:
                for slot, wafer in self._positional_pairs(row):
                    if not wafer:
                        # 🔴 A blank wafer_id makes no atom. The brief says so and the
                        # reason is the design's own rule: an atom is a claim, and
                        # "there is a wafer here, I do not know which" is not one. The
                        # SLOT is not lost - the source row still carries it and
                        # `raw_ref` points at that row.
                        self.blank_wafer_positions += 1
                        continue
                    register = self._register(molecule, "Wafer", {"wafer": wafer},
                                              occurred_at, [row])
                    if register:
                        atoms.append(register)
                    atoms.append(self._atom(
                        molecule, "has_wafer", "Lot", {"lot": row["lot"]}, occurred_at,
                        [row], "positional_row", "entity_ref",
                        entity_ref("Wafer", {"wafer": wafer}, slot=slot)))

        # --- derived_from, uttered by the row's own parent/child field -------------
        if lineage == "parent_child" and molecule.parent and molecule.child:
            atoms.append(self._atom(
                molecule, "derived_from", "Lot", {"lot": molecule.child}, occurred_at,
                molecule.rows, "pair_field", "entity_ref",
                entity_ref("Lot", {"lot": molecule.parent})))

        # --- slot_map, by the DECLARED strategy ------------------------------------
        # 🔴 NO `or []` HERE, AND NOTHING FOR ONE TO GUARD ANY MORE. `_slot_map` returns
        # a list or raises; the swallowed `None` this line used to merge is the defect
        # ruling R-2026-08-13-H names.
        if pairing != "none" and molecule.parent and molecule.child:
            atoms.extend(self._slot_map(molecule, pairing, occurred_at))

        return atoms

    def _positional_pairs(self, row):
        """`[(slot, wafer)]` for one row. Refuses the MOLECULE on an unequal pair.

        The length check is not defensive tidiness. `world.py` asserts it in the
        GENERATOR with the reason spelled out: an unequal length "does not raise anywhere
        downstream, it silently reattributes wafers to the wrong slots and every
        reconstruction built on it is wrong in a way that still looks well-formed". That
        is an atomicity violation in the design's sense - the molecule would land looking
        complete and be false - so the whole molecule is refused.
        """
        slots = _split_list(row["slots"], self.separator)
        wafers = _split_list(row["wafers"], self.separator)
        if len(slots) != len(wafers):
            gate.refuse(SOURCE, gate.REFUSE_ATOMICITY,
                        f"row {row['row_identity']!r}: {self.cfg['columns']['slots']} has "
                        f"{len(slots)} entries but "
                        f"{self.cfg['columns']['wafers']} has {len(wafers)}; a positional "
                        f"pairing across unequal lists reattributes wafers to the wrong "
                        f"slots and still looks well formed", rows=1)
        return [(s.strip(), w.strip()) for s, w in zip(slots, wafers)]

    def _slot_map(self, molecule, strategy, occurred_at):
        """`[atom]`, possibly empty. A refusal here unwinds the molecule, it is not
        returned - see `translate`, and ruling R-2026-08-13-H for what returning it cost.

        `[]` and a refusal are DIFFERENT ANSWERS and always were: `[]` means the source
        said nothing to map (a split under `shared_wafer`, a molecule with no child row),
        and that is a fact the lag and incomplete counters can show. The old `None` third
        answer is gone, which is why no caller can confuse the two any more.
        """
        parent_row = molecule.parent_row()
        child_row = molecule.child_row()

        if strategy == "slot_preserving":
            # DECLARED CONVENTION (see module docstring). Every (slot, wafer) on the
            # child's row becomes from == to. Uses only the child's row, so it works on
            # a split, where the parent's row no longer mentions the moved wafers.
            if child_row is None:
                return []
            pairs = self._positional_pairs(child_row)
            return [
                self._atom(molecule, "slot_map", "Lot", {"lot": molecule.parent},
                           occurred_at, [child_row], "slot_preserving", "entity_ref",
                           entity_ref("Lot", {"lot": molecule.child},
                                      **{"from": slot, "to": slot, "wafer": wafer}))
                for slot, wafer in pairs if wafer and slot
            ]

        if strategy == "shared_wafer":
            # ZERO INFERENCE. A pair exists only where the SAME wafer is uttered on both
            # rows, with its slot on each side. Yields nothing when the source is silent,
            # and being silent is a fact the lag/incomplete counters can show.
            if parent_row is None or child_row is None:
                return []
            parent_pairs = self._positional_pairs(parent_row)
            child_pairs = self._positional_pairs(child_row)
            parent_at = {w: s for s, w in parent_pairs if w}
            atoms = []
            for slot, wafer in child_pairs:
                if not wafer or wafer not in parent_at:
                    continue
                atoms.append(self._atom(
                    molecule, "slot_map", "Lot", {"lot": molecule.parent}, occurred_at,
                    [parent_row, child_row], "shared_wafer", "entity_ref",
                    entity_ref("Lot", {"lot": molecule.child},
                               **{"from": parent_at[wafer], "to": slot, "wafer": wafer})))
            return atoms

        return []


def raw_ref(rows) -> str:
    """`lot_event:["<row id>", ...]` - the ONLY route back to re-translation (§3).

    A JSON array rather than a delimiter-joined string, and that is not style. The source
    row identity here is `business_key_val`, which is itself
    `lot|event_type|event_time` - it already contains the obvious delimiter. Joining on
    one more would produce a string nobody can split back apart, which is the same
    failure the design's `subject` row is built to prevent, one field over. Sorted, so
    the value is identical on every run and the unique index recognises a re-translation.
    """
    identities = sorted({str(row["row_identity"]) for row in rows})
    return SOURCE + ":" + json.dumps(identities, ensure_ascii=False,
                                     separators=(",", ":"))
