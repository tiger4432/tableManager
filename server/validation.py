# -*- coding: utf-8 -*-
"""One refusal language for declaration files — 판정 300.

🔴 THIS IS A MOVE, NOT A NEW VALIDATOR. Every piece below was `ledger/setup_bundle.py`'s and
is here verbatim apart from losing its leading underscore and gaining two injected values.
S-188 ⓑ has to refuse unknown cells in `chain_rules.json`, and the alternatives were both
bad: import a PRIVATE class out of the ledger's setup module and have chain-rule refusals
arrive as `LedgerSetupValidationError`, or write a second validator — which 판정 300 forbids,
because two refusal languages drift and then the same mistake gets two different messages.

⚠️ TWO THINGS ARE INJECTED RATHER THAN MOVED, and both were ledger knowledge sitting inside
a general mechanism:

  * `error_cls` — the exception `finish()` returns. `LedgerSetupValidationError` stays in
    `setup_bundle` as a SUBCLASS of the neutral one, so its sixteen callers keep catching
    what they caught and `except DeclarationValidationError` also sees it.
  * `retired_help` — `exact()` read `_RETIRED_FIELD_HELP` directly, a map of the LEDGER's
    retired authoring paths. A shared module cannot hold that, and a chain rule's retired
    paths are a different set, so the caller supplies it.

Behaviour is unchanged: same codes, same paths, same messages, same ordering.
"""
from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


class DeclarationValidationError(ValueError):
    """One stable validation issue with its exact authoring path."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


#: How many declared names a refusal lists before it says 「+N more」.
CANDIDATE_LIMIT = 8

#: 🔴 [판정 481 ③ · 300] ONE SENTENCE FOR A RETIRED READ-TIME JOIN, because TWO
#: validators refuse it. 판정 446 changed what an ABSENT `materialize` means - from a
#: default to 「read-time join」, which is retired - and two seats now have to say so: the
#: chain-side join loader (`chain/join_refusal`, which binds it beside its refusal CODE) and
#: the ledger bundle validator (`ledger/setup_bundle`).
#:
#: It lives HERE for the reason 판정 300 already settled when the refusal language moved out
#: of `setup_bundle`: that module is held to stdlib-only imports, so a sentence it shares
#: with a domain module cannot live in the domain module. The same ruling, the same seat.
#:
#: ⛔ The words matter as much as the sharing. 「field is required」 would send an operator
#: to add a key; the truth is that a capability was RETIRED and the join has to move. 판정
#: 474 is that hazard by name - one judgement spelled two ways points at opposite repairs.
READ_TIME_RETIRED_DETAIL = (
    "'materialize' is false, which declared a READ-TIME join: the column was "
    "computed on the way out and never stored. That mechanism is retired. Declare "
    "the join in chain_rules.json instead - `derive: {kind: \"join\"}` with `on` "
    "and `take` - which writes the value into the table, or set 'materialize': "
    "true here with a 'max_rewrite_rows' ceiling to keep it as a write join."
)


def path_of(base: str, child: str) -> str:
    return f"{base}.{child}" if base else child


def allowed_note(required: Sequence[str], optional: Sequence[str]) -> str:
    """What this object DOES take, appended to a refusal that says a field is not allowed.

    🔴 THE VALIDATOR IS HOLDING THE ANSWER AT THE MOMENT IT REFUSES.  `exact()` already has
    the required and optional tuples in hand; it just was not saying them.  Measured
    2026-08-19: an author hit `unknown_field` at `...emit.object.payload` and a human sitting
    beside them had to translate it into "object takes kind / entity / value / qualifiers".
    That translation is free -- it is two tuples one stack frame away.
    """
    names = [f"{name} (required)" for name in required] + list(optional)
    if not names:
        return "; no fields are allowed here"
    return "; allowed here: " + ", ".join(str(name) for name in names)


def did_you_mean(wanted: Any, declared: Iterable[Any], label: str) -> str:
    """The half of an `unknown_*` refusal that says WHICH mistake this is.

    "unknown pack 'dt-job@1'" does not separate **you misspelled it** from **you have not
    written it yet**, and those two need opposite next actions -- fix a character, or go
    author a declaration.  Measured 2026-08-19: an author had a mapper emitting into a pack
    that did not exist yet and read the refusal as a typo.

    So the message answers the question it raised: nothing declared at all, a near miss to
    correct, or the declared names to choose from.
    """
    names = sorted({str(name) for name in declared})
    if not names:
        return f"; no {label} are declared yet"
    close = difflib.get_close_matches(str(wanted), names, n=3, cutoff=0.6)
    if close:
        return "; did you mean " + " or ".join(repr(name) for name in close) + "?"
    listed = ", ".join(repr(name) for name in names[:CANDIDATE_LIMIT])
    if len(names) > CANDIDATE_LIMIT:
        listed += f", +{len(names) - CANDIDATE_LIMIT} more"
    return f"; declared {label}: {listed}"


class Problems:
    def __init__(self, *, error_cls=DeclarationValidationError, retired_help=None,
                 forbidden_keys=frozenset()):
        #: Injected, not imported — see this module's docstring.
        self._error_cls = error_cls
        self._retired_help = retired_help or {}
        #: 🔴 THE LEDGER'S POLICY, NOT THIS MODULE'S, AND THE MOST IMPORTANT OF THE THREE.
        #: The ledger forbids `module`, `function`, `python`, `sql`, `expression`… in a
        #: declaration because 「원장 선언은 국소적·무계산」 — there is no escape hatch into
        #: code. A CHAIN rule's whole job is to name code (`mapper_module`,
        #: `mapper_function`), so a shared validator that carried this set would refuse the
        #: very cells S-188 is organising. Empty by default: a caller that wants the
        #: prohibition asks for it.
        self._forbidden_keys = frozenset(forbidden_keys)
        self.items: list = []

    def add(self, code: str, path: str, message: str) -> None:
        self.items.append(self._error_cls(code, path, message))

    def exact(self, value: Any, path: str, *, required: Sequence[str],
              optional: Sequence[str] = (), ignored: Sequence[str] = ()) -> bool:
        """Refuse every field this object does not take -- except the ones it USED to.

        🔴 `ignored` IS ACCEPT-AND-DISCARD, AND IT IS NOT `retired_help`.  That map
        only rewords an `unknown_field`; the refusal still happens, so a config
        holding the name still fails to load.  That is right for `tables`, whose contents
        moved to another file and must be deleted by hand.  It is wrong for a field that
        retired because it had ONE legal value: nothing has to move, nothing has to be
        decided, and refusing stops an operator mid-sentence over a word that no longer
        means anything.  So these names are read and dropped, in silence.

        🔴 NARROW BY CONSTRUCTION.  This is a per-call-site tuple, never a global
        tolerance: `unknown_field` is how a typo is caught everywhere else, and one
        forgiving validator would take that away from every object at once.
        """
        if not isinstance(value, Mapping):
            self.add("invalid_type", path, "must be an object")
            return False
        allowed = set(required) | set(optional) | set(ignored)
        for name in sorted(set(value) - allowed, key=str):
            key_path = path_of(path, str(name))
            code = ("unsafe_declaration"
                    if str(name).lower() in self._forbidden_keys
                    else "unknown_field")
            self.add(code, key_path, self._retired_help.get(
                key_path, "field is not allowed" + allowed_note(required, optional)))
        for name in required:
            if name not in value:
                self.add("missing_field", path_of(path, name), "field is required")
        return True

    def finish(self) -> tuple:
        return tuple(sorted(
            self.items, key=lambda issue: (issue.path, issue.code, issue.message)))
