"""The skeleton and the validator name the same fields -- counted, in both directions.

🔴 WHY THIS EXISTS. The skeleton (`config/ontology/ledger_skeleton.json`) is a SECOND
statement of a contract whose first author is `setup_bundle.py`. Two authors of one
contract drift in silence, and that is not hypothetical here: the screen's previous
hand-written shape offered `emit.object` as `kind` and `value` while the validator had
allowed `entity` and `qualifiers` all along. `lot-lineage@1` uses both, in three of its
four claims, so the owner's own live pack could not be expressed through the form -- and
nothing anywhere was red about it.

🔴 AND WHY IT IS A COUNT, NOT A SPOT CHECK. The skeleton was drafted by trimming the live
config, which is the fast way to draft it and the wrong way to finish it: the live config
uses no `virtual_joins`, no `allow_null`, no `allowed_values`, no `list_separator`, so a
skeleton that matches it perfectly is still blind to every optional field nobody has
happened to use. Only a count over the validator's OWN tuples sees those.

🔴 THE PAIRING IS DECLARED HERE; THE FIELD NAMES ARE NOT. `ANCHORS` says which skeleton
node each validator call site is about. It carries no field names -- those are read out of
the validator's syntax tree -- so this test cannot agree with a skeleton that is wrong. A
call site with no anchor is an error rather than a skip: a new rule in the validator must
be placed, not silently ignored.

Run: pytest server/tests/test_ledger_skeleton.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

from ledger import setup_bundle
from ledger.config_authoring import closed_lists, skeleton


# (function that calls `problems.exact`, the source text of the path it was given)
#   -> the skeleton node that describes the same object.
# `*` is a map member. `def:<name>` is an entry in the skeleton's `defs`.
ANCHORS = {
    ("validate_bundle_errors", "'bundle'"): "",
    ("_root_document_errors", "'ledger_config'"): "",
    ("_validate_virtual_joins", "path"): "virtual_joins.*",
    ("_validate_virtual_joins", "ppath"): "virtual_joins.*.join_key.*",
    ("_validate_vocabulary", "path"): "vocabulary.*",
    ("_validate_vocabulary", "f'{path}.object'"): "vocabulary.*.object",
    ("_validate_vocabulary", "qpath"): "vocabulary.*.object.qualifiers",
    ("_validate_entities", "path"): "entities.*",
    # The preparer and the mapper moved inside the driver on 2026-08-20 and the profile
    # moved beside them the same evening; each validator function kept its rules and lost
    # its section, so only the anchor moved.
    ("_validate_preparation", "path"): "sources.*.driver.preparation",
    ("_validate_mapper", "path"): "sources.*.driver.mapper",
    ("_validate_mapper", "f'{path}.unit'"): "sources.*.driver.mapper.unit",
    ("_validate_packs", "path"): "packs.*",
    ("_validate_packs", "cpath"): "packs.*.claims.*",
    ("_validate_packs", "rpath"): "packs.*.claims.*.roles.*",
    ("_validate_emission", "path"): "packs.*.claims.*.emit",
    ("_validate_emission", "f'{path}.object'"): "packs.*.claims.*.emit.object",
    ("_validate_profile", "path"): "sources.*.profile",
    ("_validate_profile", "mpath"): "sources.*.profile.mappings.*",
    ("_validate_binding", "path"): "def:binding",
    ("_validate_sources", "path"): "sources.*",
    ("_validate_sources", "f'{path}.driver'"): "sources.*.driver",
    ("_validate_sources", "f'{path}.driver.occurred_at'"):
        "sources.*.driver.occurred_at",
    ("_validate_sources", "f'{path}.driver.cursor'"): "sources.*.driver.cursor",
    ("_validate_registration_probe", "item_path"):
        "sources.*.driver.registration_probe.*",
}


# --------------------------------------------------------------- the validator's side

def _name_names(node, scope):
    """Every literal string a bare name stands for -- a local tuple, or a module constant."""
    assigned: set[str] = set()
    for statement in ast.walk(scope) if scope is not None else ():
        if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == node.id
                for target in statement.targets):
            try:
                assigned |= {str(value) for value in ast.literal_eval(statement.value)}
            except (ValueError, TypeError, SyntaxError):
                pass
    if assigned:
        return assigned
    constant = getattr(setup_bundle, node.id, None)
    if isinstance(constant, (tuple, list, set, frozenset)):
        return {str(value) for value in constant}
    return set()


def _tuple_names(node, scope):
    """The field names an `exact()` argument stands for, however it is spelled.

    🔴 READING ONLY LITERALS UNDER-REPORTS THE VALIDATOR, AND AN UNDER-REPORTING READER
    ACCUSES THE OTHER SIDE. Three of the 25 call sites do not hand over a literal:
    `validate_bundle_errors` splices module constants, `_validate_binding` builds its
    tuples per binding kind into a local, and its `optional=` is
    `tuple(name for name in allowed if name not in required)` -- a call wrapping a
    comprehension. The first draft of this reader understood the first two and missed the
    third, and the miss surfaced as the SKELETON having invented `suggestion_reason`.

    So the fallback is generic: whatever the expression is, every name inside it is
    resolved and unioned. That over-reports rather than under-reports, which fails in the
    safe direction -- the skeleton is asked to carry a field, never quietly excused one.
    """
    try:
        return {str(value) for value in ast.literal_eval(node)}
    except (ValueError, TypeError, SyntaxError):
        pass
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for element in node.elts:
            if isinstance(element, ast.Starred):
                names |= _tuple_names(element.value, scope)
            else:
                try:
                    names.add(str(ast.literal_eval(element)))
                except (ValueError, TypeError, SyntaxError):
                    pass
        return names
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names |= _name_names(child, scope)
    return names


def validator_fields() -> dict[str, set[str]]:
    """Every field name the validator states, keyed by the skeleton node it belongs to."""
    tree = ast.parse(Path(setup_bundle.__file__).read_text(encoding="utf-8"))
    scope_of: dict[int, ast.AST] = {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(function):
                scope_of.setdefault(id(child), function)

    named: dict[str, set[str]] = {}
    unplaced: list[tuple[str, str]] = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        function = call.func
        attribute = function.attr if isinstance(function, ast.Attribute) else ""
        if attribute != "exact":
            continue
        scope = scope_of.get(id(call))
        keywords = {kw.arg: kw.value for kw in call.keywords}
        path_argument = call.args[1] if len(call.args) > 1 else keywords.get("path")
        site = (scope.name if scope else "<module>", ast.unparse(path_argument))
        if site not in ANCHORS:
            unplaced.append(site)
            continue
        names = set()
        for key in ("required", "optional"):
            if key in keywords:
                names |= _tuple_names(keywords[key], scope)
        named.setdefault(ANCHORS[site], set()).update(names)
    assert not unplaced, (
        "the validator states field names at a site the skeleton has not been placed "
        f"against: {unplaced}. Add it to ANCHORS and to the skeleton.")
    return named


# ---------------------------------------------------------------- the skeleton's side

def skeleton_fields() -> dict[str, set[str]]:
    """Every field name the skeleton declares, keyed by the same anchors."""
    document = skeleton()
    found: dict[str, set[str]] = {}

    def walk(node, anchor):
        if not isinstance(node, dict):
            return
        if "use" in node:
            return                      # the def is walked once, on its own
        kind = node.get("kind")
        if kind == "record":
            found.setdefault(anchor, set()).update(
                str(field["key"]) for field in node.get("fields", []))
            for field in node.get("fields", []):
                child = f"{anchor}.{field['key']}" if anchor else str(field["key"])
                walk(field.get("node"), child)
        elif kind == "map":
            walk(node.get("of"), f"{anchor}.*" if anchor else "*")

    walk(document["root"], "")
    for name, node in (document.get("defs") or {}).items():
        walk(node, f"def:{name}")
    return found


# ------------------------------------------------------------------------ the counts

def test_skeleton_and_validator_name_the_same_fields():
    validator = validator_fields()
    described = skeleton_fields()

    missing = sorted(
        f"{anchor or '<root>'}.{name}"
        for anchor, names in validator.items()
        for name in names - described.get(anchor, set()))
    invented = sorted(
        f"{anchor or '<root>'}.{name}"
        for anchor, names in described.items()
        if anchor in validator
        for name in names - validator[anchor])
    unreached = sorted(anchor for anchor in described if anchor not in validator)

    print(f"\nfields the validator names, that the skeleton does not carry: {len(missing)}")
    print(f"fields the skeleton carries, that the validator never names  : {len(invented)}")
    assert not missing, missing
    assert not invented, invented
    # A record the validator never speaks about is the same defect wearing the other hat:
    # the form would offer an object nothing checks.
    assert not unreached, unreached


def test_every_choice_names_a_list_the_server_publishes():
    """`choice` names a key of `closed_lists()`; no closed list is copied into the file.

    Rule 3 of the spec, and the standing rule in `closed_lists()`'s own docstring. A
    `choice` naming a key that does not exist renders as an empty dropbox -- a control
    that refuses every value, which is worse than a text box.
    """
    published = closed_lists()
    document = skeleton()
    named: list[str] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("hint") == "choice":
            named.append(str(node.get("list")))
        for key in ("fields", "of", "node", "root"):
            value = node.get(key)
            if isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                walk(value)

    walk(document["root"])
    for node in (document.get("defs") or {}).values():
        walk(node)
    assert named, "no choice fields found -- the walker stopped short"
    unknown = sorted({name for name in named if name not in published})
    assert not unknown, unknown

    # 🔴 AND THE VALUES STAY ON THE SERVER. Naming ONE value is how a `when` gate works
    # (`entity_ref` gates `emit.object.entity`), and forbidding that would forbid the gate.
    # Copying a list means an ARRAY of its members sitting in the document, so that is
    # what is forbidden: no JSON array anywhere in the skeleton may hold a member of any
    # list the server publishes.
    members = {
        value for values in published.values() if isinstance(values, list)
        for value in values if isinstance(value, str)
    }
    copied: list[str] = []

    def arrays(node, where):
        if isinstance(node, list):
            for value in node:
                if isinstance(value, str) and value in members:
                    copied.append(f"{where}: {value}")
            for index, value in enumerate(node):
                arrays(value, f"{where}[{index}]")
        elif isinstance(node, dict):
            for key, value in node.items():
                arrays(value, f"{where}.{key}")

    arrays(document, "skeleton")
    assert not copied, f"a closed list is copied into the skeleton: {copied}"
