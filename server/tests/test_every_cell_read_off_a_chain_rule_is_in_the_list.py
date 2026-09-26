# -*- coding: utf-8 -*-
"""총괄 fe020274d. A name the product reads off a chain rule's TOP LEVEL is in `routing_keys()`.

The list is what `flat_param_cells` measures against, so a name the product reads there but the
list lacks is warned about as 「a mapper argument - move it under 'params'」 - and moving it
would break the rule (`key` is read by `chain.synthesis`, the two write permissions by
`dt_map_derivation`). Measured on the box 2026-09-26: those three were warned on five rules.

🔴 WHICH DICT IS A CHAIN RULE IS ASKED OF THE CODE, NOT OF A VARIABLE NAME. Three grammars call
their dict `rule` (`test_a_chain_rules_top_level_cells_have_one_list` says why), so counting
`rule.get(...)` counts forty-odd names that are not chain cells. Instead:
  - a dict read for a cell only a chain rule carries is a chain rule, in that function;
  - so is each item of the list `load_chain_rules()` returns, wherever that list is looped;
  - a function handed such a dict (or that list) takes it too, at that parameter - followed
    across modules until nothing new is found. That is how `dt_map_derivation` is reached (the
    worker hands it its rule) and `chain.synthesis` (it loops the loader's list).
"""
import ast
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

import chain_bindings                                                # noqa: E402
from test_a_chain_rules_top_level_cells_have_one_list import (      # noqa: E402
    BELONGING_TO_ANOTHER_GRAMMAR)

#: Cells only a chain rule carries - the seed of the census.
CHAIN_ONLY = ("trigger_columns", "mapper_module", "mapper_function", "is_batch",
              "allow_chain_trigger")

#: The owner's mapper files and the collector scripts are not product code; a mapper reads its
#: arguments through `params`, which is a different dict.
SKIPPED_DIRS = {"tests", "mappers", "ingestion_workspace", "__pycache__", ".tmp", "node_modules"}


def _literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _reads(func):
    """(variable, cell, line) for `x.get("c")`, `x["c"]` (load) and `"c" in x` in one function."""
    out = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "pop", "setdefault")
                and isinstance(node.func.value, ast.Name) and node.args and _literal(node.args[0])):
            out.append((node.func.value.id, _literal(node.args[0]), node.lineno))
        elif (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
              and isinstance(node.value, ast.Name) and _literal(node.slice)):
            out.append((node.value.id, _literal(node.slice), node.lineno))
        elif (isinstance(node, ast.Compare) and len(node.ops) == 1
              and isinstance(node.ops[0], (ast.In, ast.NotIn)) and _literal(node.left)
              and isinstance(node.comparators[0], ast.Name)):
            out.append((node.comparators[0].id, _literal(node.left), node.lineno))
    return out


def _functions():
    out = []
    for root, dirs, names in os.walk(server_dir):
        dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS]
        for name in names:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                try:
                    tree = ast.parse(handle.read())
                except SyntaxError:
                    continue
            rel = os.path.relpath(path, server_dir).replace(os.sep, "/")
            out += [(rel, f) for f in ast.walk(tree)
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return out


#: The one function whose result is «the chain rules» - its items are chain rules.
LOADER = "load_chain_rules"


def _callee(call):
    return (call.func.attr if isinstance(call.func, ast.Attribute)
            else call.func.id if isinstance(call.func, ast.Name) else None)


def _is_the_list(node, names=()):
    """The loader's list itself: its call, a name holding it, or `<that> or <default>` - not an
    expression that merely CONTAINS the call (a comprehension over it builds other dicts)."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return _is_the_list(node.values[0], names)
    return ((isinstance(node, ast.Call) and _callee(node) == LOADER)
            or (isinstance(node, ast.Name) and node.id in names))


def census():
    """{cell: {"file:line", ...}} for every name read off a chain rule, and the functions seen."""
    functions = _functions()
    by_name = {}
    for rel, func in functions:
        by_name.setdefault(func.name, []).append((rel, func))
    # (rel, func name, lineno) -> names holding a chain rule / holding the loader's list
    held, lists = {}, {}
    for rel, func in functions:
        key = (rel, func.name, func.lineno)
        seed = {var for var, cell, _ in _reads(func) if cell in CHAIN_ONLY}
        if seed:
            held[key] = seed
        listed = {t.id for n in ast.walk(func) if isinstance(n, ast.Assign) and _is_the_list(n.value)
                  for t in n.targets if isinstance(t, ast.Name)}
        if listed:
            lists[key] = listed

    def hand_on(bag, key, name):
        if name not in bag.setdefault(key, set()):
            bag[key].add(name)
            return True
        return False

    changed = True
    while changed:
        changed = False
        for rel, func in functions:
            key = (rel, func.name, func.lineno)
            mine, my_lists = held.get(key, set()), lists.get(key, set())
            for node in ast.walk(func):
                # an item of the loader's list is a chain rule
                loops = ([(node.target, node.iter)] if isinstance(node, ast.For)
                         else [(g.target, g.iter) for g in node.generators]
                         if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                                              ast.DictComp)) else [])
                for target, source in loops:
                    if isinstance(target, ast.Name) and _is_the_list(source, my_lists):
                        changed |= hand_on(held, key, target.id)
                if not isinstance(node, ast.Call):
                    continue
                for position, arg in enumerate(node.args):
                    bag = (held if isinstance(arg, ast.Name) and arg.id in mine
                           else lists if _is_the_list(arg, my_lists) else None)
                    if bag is None:
                        continue
                    for target_rel, target in by_name.get(_callee(node), ()):
                        params = [a.arg for a in target.args.args]
                        if params and params[0] in ("self", "cls"):
                            params = params[1:]
                        if position < len(params):
                            changed |= hand_on(bag, (target_rel, target.name, target.lineno),
                                               params[position])
    found = {}
    for rel, func in functions:
        mine = held.get((rel, func.name, func.lineno))
        if not mine:
            continue
        for var, cell, line in _reads(func):
            if var in mine and not cell.startswith(chain_bindings.COMMENT_PREFIX):
                found.setdefault(cell, set()).add("%s:%d" % (rel, line))
    return found, len(held)


def test_every_cell_the_product_reads_off_a_chain_rule_is_in_the_list():
    found, holders = census()
    # Canaries: a census that finds nothing is a broken census, not a clean product.
    assert "trigger_table" in found, "the census found no chain rule at all"
    assert any(site.startswith("dt_map_derivation.py") for sites in found.values()
               for site in sites), "the census did not follow the rule into dt_map_derivation"
    listed = set(chain_bindings.routing_keys())
    other = set(BELONGING_TO_ANOTHER_GRAMMAR)
    missing = {cell: sorted(sites) for cell, sites in found.items()
               if cell not in listed and cell not in other}
    assert not missing, (
        "read off a chain rule's top level but not in chain_bindings.routing_keys() - the "
        "flat-cell warning tells the operator to move these under 'params': %s (functions "
        "holding a chain rule: %d)" % (missing, holders))
