"""Release bundles put in <install>/release/ are applied by themselves (owner 11-10 «release 폴더에 받은 번들 넣어주면
알아서 반영하게 해줘 · 버전들 찾아서»): the company cannot pull, so each release is an incremental git bundle whose head
ref is «release». Two entries call `apply_releases` and nothing else - the launcher before it starts its children
(`start`), and apply_release.bat at the install root (`main`).

The order is the bundles' own: a bundle whose release head is already in HEAD is done; one whose prerequisite
commits are all in HEAD is verified, fetched and merged --ff-only; then the folder is looked at again until nothing
moves. Applied bundles go to release/applied/. Tracked files changed here: nothing is touched. A bundle that waits
for a commit nobody brought, or one git cannot read, is said and left where it is.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # server/, run as a file

FOLDER = "release"
APPLIED = "applied"
HEAD_REF = "refs/heads/release"
#: Set on the launcher run again after a release moved HEAD - it does not look again.
AGAIN = "ASSY_RELEASE_RELAUNCHED"


def _git(root, *args):
    run = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return run.returncode, (run.stdout or "").strip(), (run.stderr or run.stdout or "").strip()


def _short(sha):
    return sha[:9] if sha else "?"


def bundle_header(path):
    """(prerequisite commits, {ref: commit}) of a git bundle file (v2 or v3); ValueError when it is not one."""
    with open(path, "rb") as f:
        first = f.readline()
        if first not in (b"# v2 git bundle\n", b"# v3 git bundle\n"):
            raise ValueError("not a git bundle")
        needs, heads = [], {}
        for raw in f:
            if raw == b"\n":
                return needs, heads
            line = raw.rstrip(b"\n").decode("utf-8", "replace")
            if line.startswith("@"):                    # a v3 capability
                continue
            if line.startswith("-"):
                needs.append(line[1:].split(" ", 1)[0])
            else:
                sha, _, ref = line.partition(" ")
                heads[ref] = sha
    raise ValueError("its header has no end")


def _in_head(root, sha):
    return _git(root, "merge-base", "--is-ancestor", sha, "HEAD")[0] == 0


def _move(folder, name):
    os.makedirs(os.path.join(folder, APPLIED), exist_ok=True)
    target = os.path.join(folder, APPLIED, name)
    if os.path.exists(target):
        os.remove(target)
    shutil.move(os.path.join(folder, name), target)


def apply_releases(root, say=print):
    """Apply every bundle in <root>/release/ that can be applied, in the order their commits need -> {before, after,
    applied: [file], left: [file], stopped: sentence or None}. Each step is one line through `say`."""
    folder = os.path.join(root, FOLDER)
    names = sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))) \
        if os.path.isdir(folder) else []
    out = {"before": None, "after": None, "applied": [], "left": list(names), "stopped": None}
    if not names:
        say("[Release] nothing to apply - %s" % ("no release folder" if not os.path.isdir(folder)
                                                  else "the release folder is empty"))
        return out

    def stop(sentence):
        out["stopped"], out["left"] = sentence, list(names)
        say("[Release] %s" % sentence)
        return out

    try:
        code, head, err = _git(root, "rev-parse", "HEAD")
    except OSError as exc:
        return stop("not applied: git did not run (%s) - install git or apply by hand as the release note says" % exc)
    if code:
        return stop("not applied: %s is not a git copy (%s)" % (root, err.splitlines()[0] if err else code))
    out["before"] = out["after"] = head
    files = _git(root, "diff", "--name-only", "HEAD")[1].splitlines()
    if files:
        return stop("not applied: %d tracked file(s) changed in this copy (%s%s) - nothing was changed; put them "
                    "back with «git checkout -- <file>» or send the list to the lead, then start again"
                    % (len(files), ", ".join(files[:5]), ", ..." if len(files) > 5 else ""))

    unread, waiting = {}, {}
    moved = True
    while moved:
        moved = False
        for name in [n for n in names if n not in unread]:
            path = os.path.join(folder, name)
            try:
                needs, heads = bundle_header(path)
            except (OSError, ValueError) as exc:
                unread[name] = str(exc)
                continue
            release = heads.get(HEAD_REF)
            if not release:
                unread[name] = "it has no %s" % HEAD_REF
                continue
            if _in_head(root, release):
                _move(folder, name)
                names.remove(name)
                say("[Release] %s: already in (%s)" % (name, _short(release)))
                continue
            missing = [sha for sha in needs if not _in_head(root, sha)]
            if missing:
                waiting[name] = missing
                continue
            waiting.pop(name, None)
            code, _, err = _git(root, "bundle", "verify", path)
            if code == 0:                               # verify reads the prerequisites only; fetch reads the pack
                code, _, err = _git(root, "fetch", "--quiet", path, "release")
            if code:
                unread[name] = err.splitlines()[-1] if err else "git could not read it"
                continue
            # files the release brings that sit here outside git - git would refuse the merge in its own language
            brought = _git(root, "diff", "--name-only", "--diff-filter=A", "HEAD", "FETCH_HEAD")[1].splitlines()
            in_way = _git(root, "ls-files", "--others", "--exclude-standard", "--", *brought)[1].splitlines() \
                if brought else []
            if in_way:
                return stop("%s not applied: %d file(s) here outside git are files it brings (%s%s) - move or delete "
                            "them and start again; this copy stays at %s" % (
                                name, len(in_way), ", ".join(in_way[:5]), ", ..." if len(in_way) > 5 else "",
                                _short(out["after"])))
            code, _, err = _git(root, "merge", "--ff-only", "--quiet", "FETCH_HEAD")
            if code:
                return stop("%s not applied: %s - this copy stays at %s; send this line to the lead" % (
                    name, err.splitlines()[-1] if err else "git failed", _short(out["after"])))
            now = _git(root, "rev-parse", "HEAD")[1]
            say("[Release] %s: %s -> %s (back: git reset --hard %s)" % (name, _short(out["after"]), _short(now),
                                                                         _short(out["after"])))
            out["after"] = now
            _move(folder, name)
            names.remove(name)
            out["applied"].append(name)
            moved = True
    for name, why in unread.items():
        say("[Release] %s left in the release folder: git cannot read it (%s) - get the file again" % (name, why))
    for name in names:
        if name in waiting:
            say("[Release] %s waits for %s, which no bundle here brings - put the release before it in the release "
                "folder" % (name, ", ".join(_short(sha) for sha in waiting[name])))
    out["left"] = names
    if names:
        out["stopped"] = "%d bundle(s) left in the release folder" % len(names)
    return out


#: The job the run again lives in - held for as long as this process lives.
_JOB = []


def _tie_to_this_process(child):
    """Put `child` in a job closed when this process ends, however it ends (its window closed, a kill): the job takes
    down the child and every process the child started - the supervisor's children too, each in its own console - so
    one launcher's servers never outlive it (lead 11-10: two on one port). Windows only; elsewhere nothing."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000                # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) \
            or not kernel.AssignProcessToJobObject(job, int(child._handle)):
        raise ctypes.WinError(ctypes.get_last_error())
    _JOB.append(job)


def _launch(command, env):
    child = subprocess.Popen(command, env=env)
    try:
        _tie_to_this_process(child)
    except OSError as exc:
        child.kill()
        raise OSError("the launcher could not be tied to this window (%s)" % exc) from exc
    return child


def start(root, argv, say):
    """The launcher's entry, before anything else is loaded: apply; when HEAD moved, run the launcher again - the
    whole of it from the new code - wait for it and give its exit code. None: go on in this process."""
    if os.environ.get(AGAIN):
        return None
    try:
        out = apply_releases(root, say)
    except Exception as exc:                            # a release step never keeps the launcher from starting
        from error_said import told
        say("[Release] the release step failed: %s - starting on the code as it is" % told(exc))
        return None
    if out["after"] == out["before"]:
        return None
    say("[Release] starting again on %s" % _short(out["after"]))
    try:
        child = _launch([sys.executable, *argv], dict(os.environ, **{AGAIN: "1"}))
    except OSError as exc:                              # its children still start from the new code on disk
        say("[Release] %s - going on in this process; the launcher's own changes run from the next start" % exc)
        return None
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:                       # the console's Ctrl+C reaches the child too
            continue


def main(root=None, say=print):
    """apply_release.bat: the same function, its lines on the console; exit 1 when a bundle was left."""
    from utils.logger import make_stdout_safe
    make_stdout_safe()
    root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = apply_releases(root, say)
    if out["applied"]:
        say("[Release] restart the launcher to run %s" % _short(out["after"]))
    return 1 if out["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
