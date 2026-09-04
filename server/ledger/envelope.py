"""The 7-field envelope of `CANONICAL_LEDGER_DESIGN.md` §3, as one Python object.

The physical table flattens the envelope plus source-event correlation into thirteen
columns; `Atom` is the shape a
translator produces and the gate judges, so the flattening happens in exactly one place
(`to_row`) instead of at every emitter.

WHAT THIS FILE IS CAREFUL ABOUT
-------------------------------
**Type preservation.** §3's `object` row names the audit that found integer `0` and
string `"0"` rendered identically, and NULL indistinguishable from empty. `object_payload`
is handed to psycopg2 as `Json`, which serialises through `json.dumps` - so `0` stays a
JSON number and `"0"` stays a JSON string, and jsonb preserves the difference on the way
back. `assert_type_preserving` exists so a test can prove that rather than assume it, and
`freeze_payload` refuses the two shapes that quietly destroy it (a payload that has
already been rendered to a string, and a non-finite float, which `json.dumps` writes as
the token `NaN` - valid JavaScript, invalid JSON, rejected by PostgreSQL's jsonb).

**`recorded_at` is absent on purpose.** It lives inside the uuid7 `id` (§3). Adding the
column back would make two answers to one question.

**The correlation marker is still non-semantic.** §3's excluded list says a raw
batch/transaction marker is not ontology evidence.  `molecule_ref` therefore still
never becomes a column and no resolver may rank from it.  The evidence graph does need
to answer the narrower structural question "which claim atoms landed as one source
utterance?", so the writer derives an opaque UUID from source + marker + occurrence.
Only that UUID and its derivation state are stored; the raw marker cannot leak.
"""
from __future__ import annotations

import dataclasses
import json
import math
import uuid as _uuid
from datetime import datetime, timezone

from . import uuid7 as _uuid7


# A repository-owned UUID namespace.  Changing it would give the same source event a
# second identity on replay, so the literal is a storage contract, not decoration.
SOURCE_EVENT_NAMESPACE = _uuid.UUID("4128796d-e92b-5c44-b64e-f8bb6d43ab91")
SOURCE_EVENT_STATES = ("source_molecule", "source_record", "legacy_atom")


class PayloadNotPreservable(ValueError):
    """A payload that cannot survive the round trip with its types intact."""


def freeze_payload(payload):
    """Return `payload` unchanged, or raise `PayloadNotPreservable`.

    Deliberately NOT a coercion. A function that "fixes" a bad payload is how a string
    `"0"` becomes an integer `0` (or the reverse) with nobody able to say which the
    source actually said. The ledger's answer to a payload it cannot preserve is to
    refuse it at the door, which is the same answer it gives to undeclared vocabulary.
    """
    if payload is None:
        return None

    def walk(node, path):
        if node is None or isinstance(node, (bool, int, str)):
            return
        if isinstance(node, float):
            if math.isnan(node) or math.isinf(node):
                raise PayloadNotPreservable(
                    f"payload{path} is {node!r}; json.dumps writes NaN/Infinity as bare "
                    f"tokens that PostgreSQL's jsonb rejects")
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if not isinstance(key, str):
                    raise PayloadNotPreservable(
                        f"payload{path} has a non-string key {key!r}; JSON would coerce "
                        f"it and the original type would be unrecoverable")
                walk(value, f"{path}[{key!r}]")
            return
        if isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
            return
        raise PayloadNotPreservable(
            f"payload{path} is of type {type(node).__name__}, which has no JSON "
            f"spelling that survives a round trip")

    walk(payload, "")
    return payload


def assert_type_preserving(before, after):
    """Raise unless `after` is `before` with every scalar's TYPE intact. Returns count.

    `==` is not enough and that is the whole point: in Python `0 == False` and
    `1.0 == 1`, so an equality assertion passes on exactly the confusion this is meant
    to catch. The count is returned for the same reason `uuid7.assert_monotonic` returns
    one - a walk over an empty structure must not be able to report success.
    """
    checked = 0

    def walk(a, b, path):
        nonlocal checked
        if type(a) is not type(b):
            raise AssertionError(
                f"payload{path}: type changed across the round trip - "
                f"{type(a).__name__}({a!r}) became {type(b).__name__}({b!r})")
        if isinstance(a, dict):
            if set(a) != set(b):
                raise AssertionError(f"payload{path}: keys changed {sorted(a)} -> {sorted(b)}")
            for key in a:
                walk(a[key], b[key], f"{path}[{key!r}]")
            return
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):
                raise AssertionError(f"payload{path}: length {len(a)} -> {len(b)}")
            for index, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{index}]")
            return
        if a != b:
            raise AssertionError(f"payload{path}: value changed {a!r} -> {b!r}")
        checked += 1

    walk(before, after, "")
    return checked


def canonical_keys(keys) -> str:
    """A structured identity rendered to ONE deterministic string, for memo keys only.

    🔴 Never for storage. `subject_keys` goes to the database as jsonb and stays
    structured there - flattening an identity into a string is the incident design §3
    names, and the whole reason that column is jsonb. This exists because a Python `set`
    needs a hashable member and a dict is not one; the value never leaves the process.
    """
    return json.dumps(keys or {}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def entity_ref(entity_type, keys, **qualifiers):
    """An `entity_ref` object payload: `{type, keys{...}[, qualifiers{...}]}`.

    `keys` stays a nested object rather than being folded into the top level so a reader
    (and the signature check) can always tell IDENTITY from QUALIFIER. `has_wafer`'s
    `slot` is a qualifier: the wafer is the object, the slot is what is being said about
    where it sits. Flattening them would make `{"wafer": ..., "slot": ...}` and the next
    person would reasonably read `slot` as part of the wafer's identity.
    """
    payload = {"type": entity_type, "keys": dict(keys)}
    if qualifiers:
        payload["qualifiers"] = dict(qualifiers)
    return payload


def source_event_identity(source_who, occurred_at, *, molecule_ref=None,
                          source_raw_ref=None):
    """Return the stable `(uuid, state)` for one source utterance.

    A molecule marker is strongest because all atoms inside the gate share it.  A
    single-row producer may legitimately have no molecule marker; then its mandatory
    raw-row reference is the event boundary.  `occurred_at` is included because a
    source is allowed to reuse a transaction key over time and one source event cannot
    occur at two world instants.

    This function does *not* claim that two sources describe the same physical event.
    Cross-source equivalence belongs in ontology claims, never in this storage key.
    """
    who = str(source_who or "").strip()
    if not who:
        raise ValueError("source event identity requires source_who")
    if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
        raise ValueError("source event identity requires timezone-aware occurred_at")
    instant = occurred_at.astimezone(timezone.utc).isoformat()
    marker = str(molecule_ref or "").strip()
    if marker:
        state, reference = "source_molecule", marker
    else:
        reference = str(source_raw_ref or "").strip()
        if not reference:
            raise ValueError("source event identity requires molecule_ref or source_raw_ref")
        state = "source_record"
    canonical = json.dumps([who, state, reference, instant], ensure_ascii=False,
                           separators=(",", ":"))
    return _uuid.uuid5(SOURCE_EVENT_NAMESPACE, canonical), state


@dataclasses.dataclass
class Atom:
    """One claim. The envelope's seven fields, plus the derivation the gate checks.

    `molecule_ref` and `derivation` are NOT envelope fields and never become columns:
      * `molecule_ref` is the non-semantic correlation marker (§3's excluded list). It
        tells the gate which atoms must land together and is then discarded.
      * `derivation` names the DECLARED rule that produced this atom. Atomicity check ③
        ("did you record the utterance rather than the conclusion") has no mechanical
        form unless an atom can be asked where it came from, and this is that form: the
        gate refuses an atom whose derivation is not one the config declared.
    """
    subject_type: str
    subject_keys: dict
    predicate: str
    object_kind: str = None
    object_payload: dict = None
    occurred_at: datetime = None
    # NULL means `occurred_at` is world time, as it has been for every atom written
    # before this column existed. A value names what the time actually is when the
    # source table carries no world time - the atom says so itself, because atoms
    # outlive the declaration that produced them.
    occurred_at_basis: str = None
    source_who: str = None
    source_translator_ver: str = None
    source_raw_ref: str = None
    supersedes: str = None
    molecule_ref: str = None
    derivation: str = None
    id: _uuid.UUID = None
    source_event_id: _uuid.UUID = None
    source_event_state: str = None

    def ensure_id(self):
        """Stamp the watermark. Called once, by the writer, immediately before insert.

        Not in `__post_init__` on purpose: an id minted at construction time would be
        ordered by when the translator BUILT the atom, and a molecule that is refused
        would burn ids. Ids are minted in the order rows are actually written, which is
        the order a watermark scan will read them back in.
        """
        if self.id is None:
            self.id = _uuid7.uuid7()
        return self.id

    def ensure_source_event_identity(self):
        """Stamp the source-utterance identity without exposing `molecule_ref`.

        Explicit values are accepted for controlled import/replay paths but must be a
        complete valid pair.  Ordinary translators leave both blank and get the stable
        UUID derived by :func:`source_event_identity`.
        """
        if self.source_event_id is None and self.source_event_state is None:
            self.source_event_id, self.source_event_state = source_event_identity(
                self.source_who, self.occurred_at, molecule_ref=self.molecule_ref,
                source_raw_ref=self.source_raw_ref)
        if self.source_event_id is None or self.source_event_state not in SOURCE_EVENT_STATES:
            raise ValueError("source_event_id/state must be a complete valid pair")
        if not isinstance(self.source_event_id, _uuid.UUID):
            self.source_event_id = _uuid.UUID(str(self.source_event_id))
        return self.source_event_id

    def identity(self) -> tuple:
        """What makes two atoms THE SAME CLAIM - the tuple `uq_ledger_atom` compares.

        🔴 This is a Python-side MIRROR of `schema.DEDUPE_COLUMNS`, not the key itself.
        The unique index compares the stored columns directly, in PostgreSQL, so nothing
        here has to agree byte-for-byte with anything there - which is the point.
        A hashed key would have had to: `json.dumps(separators=(",",":"))` and jsonb's
        own `::text` render the same value differently, and a key that disagrees fails
        SILENTLY, because every row simply looks new. `schema.py` records that reasoning
        at the index.

        Used by the translator to suppress a duplicate WITHIN one molecule (cheaper than
        making the database reject it) and by tests to count distinct claims. If a column
        is added to `schema.DEDUPE_COLUMNS`, `test_ledger_l1_unit.py` fails until this
        tuple grows with it.
        """
        return (
            self.occurred_at,
            self.predicate,
            self.subject_type,
            json.dumps(self.subject_keys or {}, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False),
            json.dumps(self.object_payload if self.object_payload is not None else {},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            self.source_translator_ver,
            self.source_raw_ref,
        )

    def describe(self) -> str:
        """One line, for the operator's log. Never for a consumer to parse."""
        subject = ",".join(f"{k}={v}" for k, v in sorted((self.subject_keys or {}).items()))
        target = ""
        if isinstance(self.object_payload, dict):
            keys = self.object_payload.get("keys") or {}
            quals = self.object_payload.get("qualifiers") or {}
            target = " -> " + ",".join(f"{k}={v}" for k, v in sorted(keys.items()))
            if quals:
                target += "{" + ",".join(f"{k}={v}" for k, v in sorted(quals.items())) + "}"
        return f"({self.subject_type} {subject}) {self.predicate}{target}"


#: Column order for the physical insert. One tuple, used by the writer AND by the
#: migration's column list, so a column added to one and not the other is a syntax
#: error rather than a silently shifted value.
ROW_COLUMNS = (
    "id", "subject_type", "subject_keys", "predicate", "object_kind",
    "object_payload", "occurred_at", "source_who", "source_translator_ver",
    "source_raw_ref", "supersedes", "source_event_id", "source_event_state",
    "occurred_at_basis",
)


#: The envelope's own refusals, as codes. 🔴 THEY EXIST SO A SCREEN CAN POINT AT A BOX.
#: These six are the ones an operator meets most often - they are checked per ATOM - and
#: until now they were the only refusals in this system with no code and no address, while
#: the three validators around them all answer `(code, path, message)`. A screen could
#: render the sentence and nothing else, so "which field do I fix" had no answer.
#:
#: ⚠️ THEY ARE ALSO WHAT THE GATE BRANCHES ON. It used to decide the refusal reason by
#: searching the MESSAGE for "raw_ref" and "occurred_at", so rewording a sentence would
#: silently change which refusal an atom got - and the payload arm matched three different
#: phrases from another module's exception text.
ENVELOPE_OCCURRED_AT_MISSING = "occurred_at_missing"
ENVELOPE_OCCURRED_AT_NAIVE = "occurred_at_naive"
ENVELOPE_SOURCE_WHO_EMPTY = "source_who_empty"
ENVELOPE_TRANSLATOR_VER_EMPTY = "source_translator_ver_empty"
ENVELOPE_RAW_REF_EMPTY = "source_raw_ref_empty"
ENVELOPE_PAYLOAD_NOT_PRESERVABLE = "payload_not_preservable"


def check_envelope(atom: Atom):
    """Violations of the envelope's own rules, independent of what the atom SAYS.

    Questions about the saying ("is this predicate declared, does it accept this subject
    type") belong to the DECLARATION - they used to live in `vocabulary.check_signature`,
    which retired with that file on 2026-08-27. This function asks the questions the
    ENVELOPE asks of every atom regardless of what it says: is there a world time, is
    there a source, is there a route back to the raw utterance.

    🔴 EACH VIOLATION IS `(code, path, message)`, the same shape the three validators
    around this one already use. The sentences are unchanged; what is new is that they
    now carry WHERE - `atom.occurred_at`, `atom.source.raw_ref` - so a screen can put the
    refusal on a field instead of printing a paragraph.
    """
    violations = []

    def refuse(code, path, message):
        violations.append({"code": code, "path": path, "message": message})

    if not isinstance(atom.occurred_at, datetime):
        refuse(ENVELOPE_OCCURRED_AT_MISSING, "atom.occurred_at",
               "occurred_at is missing or is not a datetime - the world time must come "
               "from the source's declared time column, never from arrival")
    elif atom.occurred_at.tzinfo is None:
        refuse(ENVELOPE_OCCURRED_AT_NAIVE, "atom.occurred_at",
               "occurred_at is naive; the source's timezone must be declared in "
               "ledger_config.json so the value is anchored rather than guessed")
    if not (atom.source_who or "").strip():
        refuse(ENVELOPE_SOURCE_WHO_EMPTY, "atom.source.who",
               "source.who is empty (ICD 206: provenance is mandatory)")
    if not (atom.source_translator_ver or "").strip():
        refuse(ENVELOPE_TRANSLATOR_VER_EMPTY, "atom.source.translator_ver",
               "source.translator_ver is empty - without it a re-translation "
               "cannot tell which rules produced this atom")
    if not (atom.source_raw_ref or "").strip():
        refuse(ENVELOPE_RAW_REF_EMPTY, "atom.source.raw_ref",
               "source.raw_ref is empty - atomicity check 4 (can it be "
               "re-uttered?) fails, because nothing points back at the source row")
    try:
        freeze_payload(atom.object_payload)
    except PayloadNotPreservable as exc:
        refuse(ENVELOPE_PAYLOAD_NOT_PRESERVABLE, "atom.object_payload", str(exc))
    return violations
