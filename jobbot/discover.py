"""Board discovery.

The community aggregator lists are no longer a date source or a primary feed -
they are used to learn which ATS boards exist. Every URL in them names an org
slug we can then poll directly, which is how we see a posting before the
aggregator indexes it.
"""
import json, re, subprocess, tempfile, os

PATTERNS = [
    ("greenhouse", re.compile(r"(?:job-)?boards\.greenhouse\.io/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)")),
    ("lever",      re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)")),
    ("ashby",      re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_%.\s-]+?)/")),
    # Workday orgs are tenant|host|site, all three needed to reach the board.
    ("workday",    re.compile(r"https?://([a-z0-9-]+)\.(wd\d+\.myworkdayjobs\.com)/"
                              r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)/job/")),
]

LISTS = [
    "https://github.com/SimplifyJobs/Summer2027-Internships.git",
    "https://github.com/vanshb03/Summer2027-Internships.git",
]


def from_listings(paths):
    """Extract (source, org) pairs from one or more listings.json files."""
    found = set()
    for path in paths:
        try:
            rows = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            url = row.get("url", "") or ""
            for source, pat in PATTERNS:
                m = pat.search(url)
                if m:
                    org = ("|".join(g.strip() for g in m.groups()) if source == "workday"
                           else m.group(1).strip().rstrip("/"))
                    if source == "ashby":
                        from urllib.parse import unquote
                        org = unquote(org).strip()
                    if org and org.lower() not in {"embed", "jobs"}:
                        found.add((source, org))
                    break
    return found


def clone_lists(workdir=None):
    """Shallow-clone the aggregator lists and return their listings.json paths."""
    workdir = workdir or tempfile.mkdtemp(prefix="jobbot-lists-")
    paths = []
    for repo in LISTS:
        name = repo.rstrip("/").split("/")[-1].replace(".git", "")
        dest = os.path.join(workdir, name)
        try:
            if not os.path.isdir(dest):
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--filter=blob:none",
                     "--no-checkout", repo, dest],
                    check=True, capture_output=True, timeout=180)
            subprocess.run(["git", "checkout", "HEAD", "--", ".github/scripts/listings.json"],
                           cwd=dest, check=True, capture_output=True, timeout=120)
            paths.append(os.path.join(dest, ".github/scripts/listings.json"))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return paths


def merge_into_registry(reg, pairs, targets=()):
    known = {(b["source"], b["org"]) for b in reg.get("boards", [])}
    added = 0
    tl = {t.lower() for t in targets}
    for source, org in sorted(pairs):
        if (source, org) in known:
            continue
        reg.setdefault("boards", []).append({
            "source": source, "org": org,
            "target": any(t in org.lower() for t in tl),
        })
        added += 1
    return added
