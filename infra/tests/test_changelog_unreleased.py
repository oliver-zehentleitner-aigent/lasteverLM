import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "changelog_unreleased.py")

BASE = """# Changelog

## [Unreleased]

### Fixed

- an open fix

## [0.2.0] - 2026-10-14

### Added

- a released line

## [0.1.0] - 2026-10-13

- the first release
"""


class ChangelogUnreleasedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        os.makedirs(os.path.join(self.repo, "svc"))
        self.write("svc/CHANGELOG.md", BASE)
        self.write("README.md", "readme\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True
        ).stdout

    def write(self, path: str, text: str) -> None:
        with open(os.path.join(self.repo, path), "w") as f:
            f.write(text)

    def change(self, text: str, path: str = "svc/CHANGELOG.md") -> None:
        self.write(path, text)
        self.git("commit", "-q", "-am", "change")

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, SCRIPT, self.base], cwd=self.repo, capture_output=True, text=True
        )

    def test_line_added_under_unreleased_passes(self):
        self.change(BASE.replace("- an open fix\n", "- an open fix\n- another fix\n"))
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_new_subsection_under_unreleased_passes(self):
        self.change(
            BASE.replace("## [Unreleased]\n\n", "## [Unreleased]\n\n### Added\n\n- new\n\n")
        )
        self.assertEqual(self.run_check().returncode, 0)

    def test_line_added_under_a_released_section_fails_and_names_it(self):
        self.change(BASE.replace("- a released line\n", "- a released line\n- landed here\n"))
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("svc/CHANGELOG.md:14: added line is under [0.2.0]", r.stderr)
        self.assertIn("landed here", r.stderr)

    def test_line_removed_from_a_released_section_fails(self):
        self.change(BASE.replace("- the first release\n", ""))
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("removed line is under [0.1.0]", r.stderr)

    def test_line_moved_out_of_a_released_section_fails_on_the_removal(self):
        moved = BASE.replace("- a released line\n", "").replace(
            "- an open fix\n", "- an open fix\n- a released line\n"
        )
        self.change(moved)
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("removed line is under [0.2.0]", r.stderr)
        self.assertNotIn("added line", r.stderr)

    def test_header_change_fails(self):
        self.change(BASE.replace("# Changelog\n", "# Changelog\n\nintro\n"))
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("above the first section", r.stderr)

    def test_other_files_are_ignored(self):
        self.change("changed\n", path="README.md")
        self.assertEqual(self.run_check().returncode, 0)

    def test_root_changelog_is_checked_too(self):
        self.write("CHANGELOG.md", BASE)
        self.git("add", "CHANGELOG.md")
        self.git("commit", "-q", "-m", "root changelog")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.change(
            BASE.replace("- the first release\n", "- the first release\n- late\n"), "CHANGELOG.md"
        )
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("CHANGELOG.md:", r.stderr)
        self.assertIn("[0.1.0]", r.stderr)

    def test_unknown_base_is_a_git_failure(self):
        r = subprocess.run(
            [sys.executable, SCRIPT, "no-such-ref"], cwd=self.repo, capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
