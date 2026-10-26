"""Regression checks for the explicit, personal-origin push boundary."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools" / "push-origin-with-operator-approval"
APPROVAL = "PUSH DEEPHARNESS-RSI TO ORIGIN"


class PushBoundaryTests(unittest.TestCase):
    def run_guard(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(GUARD), *args],
            cwd=ROOT,
            input="",
            text=True,
            capture_output=True,
            check=False,
        )

    def test_push_attempt_without_approval_is_refused(self) -> None:
        result = self.run_guard()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit operator approval phrase", result.stderr)

    def test_approval_phrase_alone_cannot_push_noninteractively(self) -> None:
        result = self.run_guard(APPROVAL)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interactive operator confirmation", result.stderr)
        self.assertNotIn("Everything up-to-date", result.stdout)

    def test_guard_allowlists_only_the_personal_origin(self) -> None:
        script = GUARD.read_text(encoding="utf-8")

        self.assertIn("/linuxdata/Github/DeepHarness-RSI", script)
        self.assertIn("https://github.com/furrepanther/DeepHarness-RSI.git", script)
        self.assertIn("git push origin", script)
        self.assertNotIn("git push upstream", script)


if __name__ == "__main__":
    unittest.main()
