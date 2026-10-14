#!/usr/bin/env python3
"""R25c measurement (D-SINK-19 round 15, D-SRC-32): the helper over a symlink at each folder ensure_private_dir makes.
measure.py HELPER  -- runs the helper as a subprocess (timeout 30) and prints one line per case."""
import json, os, stat, subprocess, sys, tempfile, shutil
HELPER = os.path.abspath(sys.argv[1])
def run(args, env_extra=None):
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ["W"], "LANG": "C.UTF-8"}
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, "-B", "-I", HELPER] + args, capture_output=True, text=True, timeout=30, env=env)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
    except ValueError:
        out = {"raw": p.stdout[:80]}
    code = (out.get("error") or {}).get("code")
    msg = (out.get("error") or {}).get("message", "")
    tb = "Traceback" in p.stderr
    return "rc=%d ok=%s code=%s found=%s tb=%s msg=%r" % (p.returncode, out.get("ok"), code, out.get("found"), tb, msg[:110])
def mode(p):
    try: return "%o" % stat.S_IMODE(os.stat(p).st_mode)
    except OSError as e: return "none(%s)" % e.strerror
def kind(p):
    try:
        st = os.lstat(p)
        return "link" if stat.S_ISLNK(st.st_mode) else "dir" if stat.S_ISDIR(st.st_mode) else "file" if stat.S_ISREG(st.st_mode) else "other"
    except OSError: return "nothing"
STATE = '{"version":2,"cacheLayout":2,"favorites":["a"],"recents":[],"sources":[],"savedSearches":[],"hiddenGroups":[],"activeKey":""}\n'
def case(label, setup, args, look):
    w = tempfile.mkdtemp(prefix="r25c-", dir=os.environ.get("SCR"))
    os.environ["W"] = w
    try:
        setup(w)
        before = look(w)
        res = run([a.replace("@", w) for a in args])
        print("%-58s %s\n%60s before=%s after=%s" % (label, res, "", before, look(w)))
    finally:
        for root, dirs, files in os.walk(w):
            for d in dirs:
                try: os.chmod(os.path.join(root, d), 0o700)
                except OSError: pass
        shutil.rmtree(w, ignore_errors=True)
def st_link_dir(w):
    os.mkdir(w + "/dot", 0o755); os.chmod(w + "/dot", 0o755)
    open(w + "/dot/state.json", "w").write(STATE); os.chmod(w + "/dot/state.json", 0o600)
    os.symlink(w + "/dot", w + "/st")
def st_link_dir_empty(w):
    os.mkdir(w + "/dot", 0o755); os.chmod(w + "/dot", 0o755); os.symlink(w + "/dot", w + "/st")
def st_dangle(w): os.symlink(w + "/gone", w + "/st")
def st_link_file(w):
    open(w + "/afile", "w").write("x"); os.symlink(w + "/afile", w + "/st")
def st_link_ro(w):
    os.mkdir(w + "/dot", 0o755); open(w + "/dot/state.json", "w").write(STATE); os.chmod(w + "/dot/state.json", 0o600)
    os.chmod(w + "/dot", 0o500); os.symlink(w + "/dot", w + "/st")
def file_link_ro(w):
    os.mkdir(w + "/st", 0o700); os.mkdir(w + "/ro", 0o700)
    open(w + "/ro/state.json", "w").write(STATE); os.chmod(w + "/ro/state.json", 0o600); os.chmod(w + "/ro", 0o500)
    os.symlink(w + "/ro/state.json", w + "/st/state.json")
lk = lambda w: "st:%s dot:%s/%s" % (kind(w + "/st"), kind(w + "/dot"), mode(w + "/dot"))
print("== state folder")
for verb in (["show"], ["source", "list"], ["init"], ["favorite", "add", "b"]):
    case("folder link -> dir (0755) " + " ".join(verb), st_link_dir, ["state", "--state-dir", "@/st"] + verb, lk)
case("folder link -> EMPTY dir (0755) init", st_link_dir_empty, ["state", "--state-dir", "@/st", "init"], lambda w: lk(w) + " file:%s/%s" % (kind(w + "/dot/state.json"), mode(w + "/dot/state.json")))
for verb in (["show"], ["source", "list"], ["init"], ["favorite", "add", "b"], ["clear-recents"]):
    case("folder link DANGLING " + " ".join(verb), st_dangle, ["state", "--state-dir", "@/st"] + verb, lambda w: "st:%s gone:%s" % (kind(w + "/st"), kind(w + "/gone")))
for verb in (["show"], ["init"], ["favorite", "add", "b"]):
    case("folder link -> FILE " + " ".join(verb), st_link_file, ["state", "--state-dir", "@/st"] + verb, lambda w: "st:%s" % kind(w + "/st"))
case("folder link -> dir 0500 favorite add", st_link_ro, ["state", "--state-dir", "@/st", "favorite", "add", "b"], lk)
case("FILE link into a 0500 folder favorite add (D-SRC-34)", file_link_ro, ["state", "--state-dir", "@/st", "favorite", "add", "b"], lambda w: "ro:%s" % mode(w + "/ro"))
print("== cache folder (ensure_private_dir callers)")
case("cache dir link -> dir 0755: cache migrate", st_link_dir_empty, ["cache", "--cache-dir", "@/st", "migrate"], lk)
case("cache dir DANGLING: cache migrate", st_dangle, ["cache", "--cache-dir", "@/st", "migrate"], lambda w: "st:%s gone:%s" % (kind(w + "/st"), kind(w + "/gone")))
case("cache dir DANGLING: cache prune", st_dangle, ["cache", "--cache-dir", "@/st", "prune"], lambda w: "st:%s gone:%s" % (kind(w + "/st"), kind(w + "/gone")))
case("cache dir DANGLING: failed mark", st_dangle, ["failed", "--cache-dir", "@/st", "mark", "--id", "t:x"], lambda w: "st:%s gone:%s" % (kind(w + "/st"), kind(w + "/gone")))
case("cache dir link -> dir 0755: failed mark", st_link_dir_empty, ["failed", "--cache-dir", "@/st", "mark", "--id", "t:x"], lk)
def sources_dangle(w):
    os.mkdir(w + "/c", 0o700); os.symlink(w + "/gone", w + "/c/sources")
case("cache sources/ DANGLING: cache migrate", sources_dangle, ["cache", "--cache-dir", "@/c", "migrate"], lambda w: "sources:%s gone:%s" % (kind(w + "/c/sources"), kind(w + "/gone")))
print("== runtime socket folder")
case("runtime dir DANGLING: player stop", st_dangle, ["player", "stop", "--socket", "@/st/mpv.sock"], lambda w: "st:%s gone:%s" % (kind(w + "/st"), kind(w + "/gone")))
case("runtime dir link -> dir 0755: player stop", st_link_dir_empty, ["player", "stop", "--socket", "@/st/mpv.sock"], lk)
