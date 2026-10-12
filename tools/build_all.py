"""build_all.py - build the head of every branch of the public Rx firmware repos that has no build yet.

For each branch: shallow clone, PlatformIO build of the default environment with prefix maps (no local
path goes into the image), then tools/make_manifest.py adds the build to <out> (index.json and
<repo>/<branch>/<commit>/). Keeps the newest KEEP builds of each branch. A failed build is reported and
skipped; it does not stop the other branches.

Usage: python tools/build_all.py <out folder>     (GITHUB_TOKEN in the environment raises the API limit)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPOS = ["rctestflight/Trail_Tracer_Mower", "rctestflight/Trail-Tracer"]
KEEP = 10
SKIP_BRANCH = r"^(gh-pages|site)$"                    # page branches, not firmware
HERE = Path(__file__).resolve().parent


def api(path):
    req = urllib.request.Request("https://api.github.com/" + path, headers={"Accept": "application/vnd.github+json"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def slug(branch):
    return re.sub(r"[^A-Za-z0-9._-]", "-", branch)


def default_env(ini):
    m = re.search(r"^default_envs\s*=\s*([^\s,]+)", ini, re.M)
    return m.group(1) if m else re.search(r"^\[env:([^\]]+)\]", ini, re.M).group(1)


def build(repo, branch, sha, out, work):
    src = work / f"{repo.split('/')[-1]}-{slug(branch)}-{sha[:12]}"         # a new folder for each build
    subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", branch, f"https://github.com/{repo}.git", str(src)], check=True)
    head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if head != sha:
        raise RuntimeError(f"head moved: {head[:12]}, not {sha[:12]}")
    env = default_env((src / "platformio.ini").read_text(encoding="utf-8"))
    pio_home = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio")).as_posix()
    s = src.as_posix()
    flags = f"-ffile-prefix-map={s}=. -fmacro-prefix-map={s}=. -ffile-prefix-map={pio_home}=pio -fmacro-prefix-map={pio_home}=pio"
    subprocess.run(["pio", "run", "-e", env, "-d", str(src)], check=True, env=dict(os.environ, PLATFORMIO_BUILD_FLAGS=flags))
    bdir = src / ".pio" / "build" / env
    fw = (bdir / "firmware.bin").read_bytes()
    rover = b"rover-firmware" in fw
    cmd = [sys.executable, str(HERE / "make_manifest.py"), "esp32", "--files", str(bdir), "--repo", repo, "--branch", branch,
           "--commit", sha, "--subject", "", "--out", str(out)]
    if rover:
        main_cpp = (src / "src" / "main.cpp").read_text(encoding="utf-8", errors="replace")
        versions = [v for v in re.findall(r'#define ROVER_FW_VERSION "([^"]+)"', main_cpp) if v.encode() in fw]
        if not versions:
            raise RuntimeError("no ROVER_FW_VERSION of src/main.cpp is in firmware.bin")
        cmd += ["--version", versions[0]]
    else:
        cmd += ["--family", "main", "--table", "main", "--version", f"{branch} {sha[:7]}"]
    subprocess.run(cmd, check=True)
    # STM32 update files in the branch (encrypted and signed): one build per .commit_header with its
    # .bin.encrypted beside it. Plain STM32 images are never taken.
    for hdr in sorted(src.rglob("*.commit_header")):
        img = hdr.with_name(hdr.name[:-len(".commit_header")] + ".bin.encrypted")
        if ".git" in hdr.parts or not img.exists():
            continue
        subprocess.run([sys.executable, str(HERE / "make_manifest.py"), "stm32", "--header", str(hdr), "--image", str(img),
                        "--repo", repo, "--branch", branch, "--commit", sha, "--subject", "", "--out", str(out)], check=True)


def prune(out):
    """Keep the newest KEEP builds of each repo and branch: older folders and index entries go."""
    idx_path = out / "index.json"
    if not idx_path.exists():
        return
    idx = json.loads(idx_path.read_text())
    seen, keep = {}, []
    for b in sorted(idx["builds"], key=lambda b: b["built_utc"], reverse=True):
        k = (b["repo"], b["branch"], b["chip"])
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= KEEP:
            keep.append(b)
        else:
            shutil.rmtree(out / Path(b["manifest"]).parent, ignore_errors=True)
            print(f"pruned {b['repo']} {b['branch']} {b['commit'][:7]}")
    idx["builds"] = keep
    idx_path.write_text(json.dumps(idx, indent=2) + "\n")


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    failed = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        for repo in REPOS:
            for br in api(f"repos/{repo}/branches?per_page=100"):
                name, sha = br["name"], br["commit"]["sha"]
                if re.search(SKIP_BRANCH, name):
                    continue
                if (out / repo.split("/")[-1] / slug(name) / sha[:12]).exists():
                    continue
                print(f"== {repo} {name} {sha[:12]}", flush=True)
                try:
                    build(repo, name, sha, out, work)
                except Exception as ex:                        # one branch that does not build stops nothing else
                    failed.append(f"{repo} {name} {sha[:12]}: {ex}")
                    print(f"   failed: {ex}", flush=True)
    prune(out)
    # releases.json: the tagged commits of the repos; the page shows those as releases, the other branch
    # heads as development branches (behind a switch).
    rel = {}
    for repo in REPOS:
        for tag in api(f"repos/{repo}/tags?per_page=100"):
            rel.setdefault(tag["commit"]["sha"], tag["name"])
    (out / "releases.json").write_text(json.dumps({"commits": rel}, indent=2) + "\n")
    for f in failed:
        print("FAILED " + f)


if __name__ == "__main__":
    main()
