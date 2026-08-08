import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lens_versions  # noqa: E402


class TestLensVersions(unittest.TestCase):
    def test_every_lens_md_is_locked_and_hash_matches(self):
        lock = lens_versions.load_lock()
        for md in sorted(lens_versions.LENS_DIR.glob("*.md")):
            skill = md.stem
            self.assertIn(skill, lock,
                          "{}: no entry in lens-versions.json — add {{version, sha256}}".format(skill))
            self.assertEqual(
                lock[skill].get("sha256"), lens_versions.hash_file(md),
                "{0}.md changed but its sha256 in lens-versions.json was not re-locked. "
                "Bump {0}'s version and update its sha256.".format(skill))

    def test_no_orphan_lock_entries(self):
        for skill in lens_versions.load_lock():
            self.assertTrue((lens_versions.LENS_DIR / (skill + ".md")).is_file(),
                            "{}: lock entry has no agents/lenses/{}.md".format(skill, skill))

    def test_every_entry_has_version_string_and_sha256(self):
        for skill, meta in lens_versions.load_lock().items():
            self.assertIsInstance(meta.get("version"), str, "{}: version must be a string".format(skill))
            self.assertRegex(meta.get("sha256", ""), r"^[0-9a-f]{64}$",
                             "{}: sha256 must be a 64-hex digest".format(skill))
