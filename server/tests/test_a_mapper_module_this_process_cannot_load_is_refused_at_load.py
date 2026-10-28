# -*- coding: utf-8 -*-
"""Lead 10-28: a rule naming mapper_module + mapper_function the process cannot load stood - the grammar asked only
that both were written - and failed every group of its table until the chain switched it off, while the list said
it ran (measured on sqlite: «rule 'x' names m.f and it could not be loaded (ModuleNotFoundError …)» per group). The
loader now asks `_loadable_mapper` (all three grammar callers hand it in) and refuses it as unresolvable_mapper,
widened - the refusal seat, the list's detail and the replay say the import error. A module imports once per
process; one that would not is asked again at the next load, so a file put there since is found; one module's
failure is its own rule's alone."""
import json
import sys

from chain import ingestion_worker as worker
from test_the_rule_list_says_what_runs_and_what_is_only_written import DST, SRC, fixture_declared  # noqa: F401

LOADS = "zz_mapper_module_loads"


def _rule(name, module):
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": DST,
            "trigger_columns": ["job"], "mapper_module": module, "mapper_function": "f"}


def _load(tmp_path, monkeypatch, *rules):
    chain_file = tmp_path / "rules.json"
    chain_file.write_text(json.dumps({"rules": list(rules)}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    import paths
    monkeypatch.setattr(paths, "config_path", lambda name: str(chain_file))
    worker.forget_loaded_chain_rules()
    return [r.get("name") for r in worker.loaded_chain_rules()], worker.refused_chain_rules()


def _module(folder, name, body):
    (folder / ("%s.py" % name)).write_text(body, encoding="utf-8")


def test_a_module_not_there_is_refused_then_found_once_put_there(declared, tmp_path, monkeypatch):
    folder = tmp_path / "mods"
    folder.mkdir()
    monkeypatch.syspath_prepend(str(folder))
    monkeypatch.delitem(sys.modules, "zz_late_mod", raising=False)
    loaded, refused = _load(tmp_path, monkeypatch, _rule("zz_late", "zz_late_mod"))
    assert "zz_late" not in loaded
    assert refused["zz_late"].startswith(
        "unresolvable_mapper rules[0].mapper_module: names no mapper this process can run: zz_late_mod.f could not be "
        "loaded (ModuleNotFoundError: No module named 'zz_late_mod'"), refused["zz_late"]
    _module(folder, "zz_late_mod", "def f(db, payload, rule=None):\n    return {'updates': []}\n")
    loaded, refused = _load(tmp_path, monkeypatch, _rule("zz_late", "zz_late_mod"))
    assert "zz_late" in loaded and "zz_late" not in refused, "the file put there since is found at the next load"
    monkeypatch.delitem(sys.modules, "zz_late_mod", raising=False)


def test_a_module_imports_once_and_one_failure_is_its_own(declared, tmp_path, monkeypatch):
    folder = tmp_path / "mods"
    folder.mkdir()
    monkeypatch.syspath_prepend(str(folder))
    _module(folder, "zz_once_mod", "import sys\nsetattr(sys, %r, getattr(sys, %r, 0) + 1)\n"
                                   "def f(db, payload, rule=None):\n    return {'updates': []}\n" % (LOADS, LOADS))
    _module(folder, "zz_broken_mod", "raise RuntimeError('this module breaks on import')\n")
    _module(folder, "zz_nofn_mod", "def g():\n    pass\n")
    for name in ("zz_once_mod", "zz_broken_mod", "zz_nofn_mod"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, LOADS, 0, raising=False)
    rules = (_rule("zz_once", "zz_once_mod"), _rule("zz_broken", "zz_broken_mod"), _rule("zz_nofn", "zz_nofn_mod"))
    for _ in range(2):
        loaded, refused = _load(tmp_path, monkeypatch, *rules)
        assert "zz_once" in loaded, "one module's failure is its own rule's alone"
        assert "RuntimeError: this module breaks on import" in refused["zz_broken"]
        assert refused["zz_nofn"].endswith("could not be loaded (zz_nofn_mod has no f)")
    assert getattr(sys, LOADS) == 1, "imported once per process, however often the rules load"
    for name in ("zz_once_mod", "zz_broken_mod", "zz_nofn_mod"):
        monkeypatch.delitem(sys.modules, name, raising=False)
