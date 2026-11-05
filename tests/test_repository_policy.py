"""Regression checks for the DeepHarness-RSI authoring and push boundary."""

import hashlib
import json
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

    def test_portable_review_runtime_bundle_is_tracked_and_complete(self) -> None:
        bundle = ROOT / "runtime_bundle"
        manifest = json.loads(
            (bundle / "review_runtime_bundle_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(manifest["artifacts"])
        for artifact in manifest["artifacts"]:
            path = bundle / artifact["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"], path
            )
        config = json.loads(
            (bundle / "next-tasks" / "qwen3_checker_agentic_reviewers_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("/local-agent/v1", config["router_contract"])
        client_source = bundle / "lib" / "common_mcp_client.py"
        compile(client_source.read_text(encoding="utf-8"), str(client_source), "exec")


if __name__ == "__main__":
    unittest.main()
