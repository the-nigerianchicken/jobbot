"""Where his things are.

The code is generic and can be public. Everything about him - what he is
looking for, who he follows, his facts, his answers, his resumes and jobbot's
own state - lives somewhere else, and every path to it comes from here.

    JOBBOT_PRIVATE     the private checkout (sets all of the below at once)
    JOBBOT_DATA        jobbot's state            (default <private>/data)
    JOBBOT_OUT         written resumes           (default <private>/resumes)
    JOBBOT_PIPELINE    profile.yaml and rules    (default <private>/pipeline)
    JOBBOT_CRITERIA    what counts as a match    (default <private>/criteria.yaml)
    JOBBOT_ANSWERS     how forms get answered    (default <private>/answers.yaml)
    JOBBOT_TARGETS     the companies he follows  (default <private>/targets.txt)

With none of them set, everything sits in this checkout, exactly as before.
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("JOBBOT_ROOT") or Path(__file__).resolve().parent.parent)
PRIVATE = Path(os.environ.get("JOBBOT_PRIVATE") or ROOT)


def _at(var, *fallback):
    return Path(os.environ[var]) if os.environ.get(var) else PRIVATE.joinpath(*fallback)


DATA = _at("JOBBOT_DATA", "data")
OUT = _at("JOBBOT_OUT", "resumes")
PIPELINE = _at("JOBBOT_PIPELINE", "pipeline")
CRITERIA = _at("JOBBOT_CRITERIA", "criteria.yaml")
ANSWERS = _at("JOBBOT_ANSWERS", "answers.yaml")
# targets.txt sat inside the package while the code and his list shared a repo.
TARGETS = (Path(os.environ["JOBBOT_TARGETS"]) if os.environ.get("JOBBOT_TARGETS")
           else (PRIVATE / "targets.txt" if (PRIVATE / "targets.txt").exists()
                 else ROOT / "jobbot" / "targets.txt"))


def at(name):
    """A path given on a command line, resolved against his things.

    The workflows say data/queue.json and pipeline/profile.yaml, because that is
    where those lived when the code and his things shared a repo. They do not
    any more, and a path that still assumes they do fails at the point of use:
    a sweep crashed writing data/queue.json, and every resume run failed reading
    pipeline/profile.yaml four hours later (both 2026-09-24).
    """
    p = Path(name)
    if p.is_absolute():
        return p
    parts = p.parts
    root = {"data": DATA, "pipeline": PIPELINE, "resumes": OUT}.get(parts[0] if parts else "")
    return root.joinpath(*parts[1:]) if root else p


def inside(path):
    """A path as git needs it: relative to the checkout it will be committed in."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PRIVATE.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)
