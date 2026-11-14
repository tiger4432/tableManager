"""The three entries the operator runs from a .bat - apply_release, maintenance, the launcher - on a cp949 console
(PYTHONIOENCODING=cp949, strict): «», the em dash and Korean reach the console, a character cp949 lacks as «?», and the
exit code is the entry's own - never a UnicodeEncodeError (ops 11-14: apply_release's refusal ended in a traceback)."""
import os
import subprocess
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(SERVER_DIR)
#: what a fake holder makes describe_port_conflict say - every kind of character the console meets
FAKE_HOLDER = ["FAKE «holder» — 한글", "FAKE cause"]
SAID = ["FAKE ?holder? ? 한글", "FAKE cause"]


def _run(args, tmp_path, **env):
    done = subprocess.run([sys.executable, *args], cwd=str(tmp_path), capture_output=True, timeout=120,
                          env=dict(os.environ, PYTHONIOENCODING="cp949", ASSY_DATA_ROOT=str(tmp_path), **env))
    out = (done.stdout + done.stderr).decode("cp949", "replace")
    assert "UnicodeEncodeError" not in out and "Traceback" not in out, out
    return done.returncode, [line.replace(chr(27) + "[0m", "") for line in out.splitlines()]


def _with_a_fake_holder(tmp_path, program, *argv):
    child = tmp_path / "with_a_fake_holder.py"
    child.write_text("\n".join([
        "import os, runpy, sys",
        "sys.path.insert(0, %r)" % SERVER_DIR,
        "from runtime import process_supervisor",
        "process_supervisor.describe_port_conflict = lambda *a, **k: chr(10).join(%r)" % FAKE_HOLDER,
        "sys.argv = [%r, *%r]" % (program, list(argv)),
        "runpy.run_path(sys.argv[0], run_name='__main__')"]), encoding="utf-8")
    return [str(child)]


def test_apply_releases_refusal(tmp_path):
    copy = tmp_path / "설치—«copy»"                      # not a git copy: the refusal names the folder
    (copy / "release").mkdir(parents=True)
    (copy / "release" / "x.bundle").write_text("", encoding="utf-8")
    code, lines = _run(["-c", "import sys; sys.path.insert(0, sys.argv[1]); from runtime import release_apply; "
                              "sys.exit(release_apply.main(root=sys.argv[2]))", SERVER_DIR, str(copy)], tmp_path)
    assert code == 1, lines
    assert len(lines) == 1 and lines[0].startswith(
        "[Release] not applied: %s is not a git copy (" % os.path.join(str(tmp_path), "설치??copy?")), lines


def test_the_maintenance_pages_refusal(tmp_path):
    code, lines = _run(_with_a_fake_holder(tmp_path, os.path.join(SERVER_DIR, "runtime", "maintenance_page.py")),
                       tmp_path, ASSY_API_HOST="127.0.0.1", ASSY_API_PORT="8080")
    assert code == 1 and lines == SAID + ["Nothing served."], lines


def test_the_launchers_refusal(tmp_path):
    code, lines = _run(_with_a_fake_holder(tmp_path, os.path.join(ROOT, "run_decoupled_app.py"), "--server-only",
                                           "--preflight-only"), tmp_path, ASSY_API_HOST="127.0.0.1", ASSY_API_PORT="8080")
    assert code == 1, lines
    assert [line for line in lines if line.endswith(tuple("   " + s for s in SAID))] != [], lines
    assert all(any(line.endswith("   " + s) for line in lines) for s in SAID), lines
