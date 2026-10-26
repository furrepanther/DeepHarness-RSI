"""Regression checks for the pinned, research-only evidence set."""

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "RESEARCH-MANIFEST.json"
REPORT_ROOT = ROOT / "docs" / "research"
EXPECTED_REPORTS = {
    "deer-flow-bounded.md",
    "deepseek-harness.md",
    "ruflo.md",
    "open-code-review.md",
    "deepagents.md",
    "openai-agents-python-bounded.md",
    "agentmemory-static.md",
    "yuxi-static.md",
}
SUPPORTING_EVIDENCE = {
    "20261026-upstream-head-refresh.md",
    "20261026-agent-research-dispatch.md",
}
DISPATCH_REPORT = "20261026-agent-research-dispatch.md"
MAX_REPORT_BYTES = 64_000
SECRET_MARKERS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|PRIVATE) KEY-----"),
)


class ResearchEvidenceTests(unittest.TestCase):
    def load_manifest(self) -> dict:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_is_research_only_and_maps_all_requested_repositories(self) -> None:
        manifest = self.load_manifest()

        self.assertEqual(manifest["schema"], "deepharness-rsi-research-manifest-v1")
        self.assertTrue(manifest["research_only"])
        self.assertFalse(manifest["runtime_promotion"])
        self.assertEqual(len(manifest["entries"]), 8)
        self.assertEqual(
            {entry["requested"] for entry in manifest["entries"]},
            {
                "bytedance/deer-flow",
                "deepseek/agent-harness",
                "ruvnet/ruflo",
                "alibaba/open-code-review",
                "langchain-ai/deepagents",
                "openai/openai-agents-python",
                "rohitg00/agentmemory",
                "xerrors/Yuxi",
            },
        )
        deepseek = next(entry for entry in manifest["entries"] if entry["requested"] == "deepseek/agent-harness")
        self.assertEqual(deepseek["verified_repository"], "deepseek-ai/deepseek-harness")
        self.assertTrue((ROOT / manifest["online_head_refresh"]).is_file())

    def test_reports_exist_are_bounded_secret_free_and_have_stable_digests(self) -> None:
        actual_reports = {path.name for path in REPORT_ROOT.glob("*.md") if path.name != "README.md"}
        self.assertEqual(actual_reports, EXPECTED_REPORTS | SUPPORTING_EVIDENCE)

        for name in sorted(EXPECTED_REPORTS | SUPPORTING_EVIDENCE):
            path = REPORT_ROOT / name
            raw = path.read_bytes()
            self.assertGreater(len(raw), 0, name)
            self.assertLessEqual(len(raw), MAX_REPORT_BYTES, name)
            text = raw.decode("utf-8")
            for marker in SECRET_MARKERS:
                self.assertIsNone(marker.search(text), name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(text.encode("utf-8")).hexdigest(), name)

    def test_dispatch_record_has_explicit_privacy_and_size_guards(self) -> None:
        path = REPORT_ROOT / DISPATCH_REPORT
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        self.assertGreater(len(raw), 0)
        self.assertLessEqual(len(raw), MAX_REPORT_BYTES)
        normalized = " ".join(text.split()).lower()
        self.assertIn("/linuxdata/github/deepharness-rsi", normalized)
        self.assertIn("only authoring location", normalized)
        self.assertIn("working backup-of-record", normalized)
        self.assertNotIn("AGENT_MAIL_REGISTRATION_TOKEN", text)
        for marker in SECRET_MARKERS:
            self.assertIsNone(marker.search(text))

    def test_dispatch_record_enforces_authority_and_read_only_research(self) -> None:
        text = " ".join((REPORT_ROOT / DISPATCH_REPORT).read_text(encoding="utf-8").split()).lower()
        required_contracts = (
            "/linuxdata/Github/DeepHarness-RSI",
            "only authoring location",
            "working backup-of-record",
            "read-only research inputs",
            "No candidate checkout may be repaired, restored, staged, or pushed",
            "committed Git objects only",
            "dirty worktrees are not repaired or silently treated as clean",
            "No origin push is authorized",
        )
        for contract in required_contracts:
            self.assertIn(contract.lower(), text, contract)

    def test_dispatch_record_preserves_operator_gated_execution_boundaries(self) -> None:
        text = " ".join((REPORT_ROOT / DISPATCH_REPORT).read_text(encoding="utf-8").split()).lower()
        required_boundaries = (
            "pushes from the parent repository's personal `origin` remain operator-gated",
            "no cleanup or destructive recovery is allowed",
            "before any implementation or promotion decision",
        )
        for boundary in required_boundaries:
            self.assertIn(boundary, text, boundary)


if __name__ == "__main__":
    unittest.main()
