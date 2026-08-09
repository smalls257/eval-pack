"""Rebuild a minimal ephemeral git repo from a committed fixture, deterministically. Stdlib."""
import contextlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


@contextlib.contextmanager
def load_fixture(fixture_dir):
    fixture_dir = Path(fixture_dir)
    base = fixture_dir / "base"
    patch = fixture_dir / "delivered.patch"
    if not (base.is_dir() and patch.is_file()):
        yield (fixture_dir, None, None)
        return
    tmp = Path(tempfile.mkdtemp(prefix="lens-fixture-"))
    try:
        _git(tmp, "init", "-q")
        _git(tmp, "config", "user.email", "eval@lens")
        _git(tmp, "config", "user.name", "lens-eval")
        for item in base.iterdir():
            dest = tmp / item.name
            shutil.copytree(item, dest) if item.is_dir() else shutil.copy2(item, dest)
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "base")
        diff_base = subprocess.run(["git", "-C", str(tmp), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout.strip()
        _git(tmp, "apply", "--recount", str(patch))
        yield (fixture_dir, tmp, diff_base)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
