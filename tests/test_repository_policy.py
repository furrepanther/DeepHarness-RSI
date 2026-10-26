"""Regression checks for the DeepHarness-RSI authoring and push boundary."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryPolicyTests(unittest.TestCase):
    def test_canonical_authoring_checkout_is_explicit(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        provenance = (ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")

        for document in (readme, provenance):
            self.assertIn("/linuxdata/Github/DeepHarness-RSI", document)

        self.assertIn("not alternate authoring locations", readme)
        self.assertIn("alternate authoring", provenance)

    def test_origin_push_requires_explicit_operator_authority(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        provenance = (ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")

        self.assertIn("direct request or approval", readme)
        self.assertIn("must never push automatically", readme)
        self.assertIn("explicitly requests or approves", provenance)
        self.assertIn("never authorize an automatic", provenance)


if __name__ == "__main__":
    unittest.main()
