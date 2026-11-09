"""Owner 11-09 «페이싱 깃 트래킹 빼»: the pacing table ships as config/sample/pacing.json.sample and an operator's
config/pacing.json holds only the cells they changed, read over it - a pace or a job by name, any other key alone - so
a job a release adds reaches a deployment whose own file predates it (lead 11-09 ㄱ · ㄴ)."""
import json

import paths
import pacing
import system_catalog


def _own(monkeypatch, tmp_path, cells):
    own = tmp_path / "pacing.json"
    if cells is not None:
        own.write_text(json.dumps(cells), encoding="utf-8")
    monkeypatch.setattr(pacing, "PACING_PATH", own)


def test_the_table_ships_as_a_sample_and_the_operators_file_is_a_config():
    assert pacing.SHIPPED_PATH.exists() and str(pacing.SHIPPED_PATH) == paths.config_sample_path("pacing.json")
    assert str(pacing.PACING_PATH) == paths.config_path("pacing.json")
    shipped = json.loads(pacing.SHIPPED_PATH.read_text(encoding="utf-8"))
    assert shipped["jobs"][system_catalog.RUNTIME_JOB] == "background", "canary: the job this file's next test needs"


def test_no_file_of_the_operators_reads_the_shipped_table(monkeypatch, tmp_path):
    _own(monkeypatch, tmp_path, None)
    assert pacing.read_table() == json.loads(pacing.SHIPPED_PATH.read_text(encoding="utf-8"))


def test_an_old_file_with_old_jobs_only_still_runs_a_job_a_release_added_at_its_shipped_pace(monkeypatch, tmp_path):
    _own(monkeypatch, tmp_path, {"jobs": {"chain_followup": "slow"}})
    assert pacing.job_pace("chain_followup") == pacing.resolve("slow") == (5, 1.0)
    assert pacing.job_pace(system_catalog.RUNTIME_JOB) == (1, 60.0), "background, from the shipped table"


def test_the_operators_pace_replaces_that_pace_and_a_key_replaces_that_key(monkeypatch, tmp_path):
    _own(monkeypatch, tmp_path, {"paces": {"slow": {"units_per_cycle": 2, "rest_seconds": 4}}, "page_seconds": 2})
    assert pacing.resolve("slow") == (2, 4.0)
    assert pacing.resolve("trickle") == (1, 3.0) and set(pacing.load_paces()) >= {"fast", "slow", "trickle", "background"}
    assert pacing.page_seconds() == 2.0
