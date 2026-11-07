"""Check policy selection by effective date, independently for each filename."""

import json
import tempfile
import unittest
from pathlib import Path

from agent_runtime.tools.policy_hooks import CurrentPoliciesHook
from agent_runtime.tools.tools import SearchPoliciesTool


POLICY_NAMES = [
    "policy_already_refunded.txt",
    "policy_refund.txt",
    "policy_event_date_restriction.txt",
    "policy_refund_processing_time.txt"
]


class PolicyHookTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)

    def write_policy(self, path, date, text):
        file = self.directory / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("EFFECTIVE DATE: " + date + "\n" + text, encoding="utf-8")

    def retrieve(self, names, current_date="2026-08-10"):
        tool = SearchPoliciesTool(
            str(self.directory), post_hooks=[CurrentPoliciesHook(current_date)]
        )
        return tool.read_policies(json.dumps({"policy_names": names}))

    def test_project_policies_select_expected_versions(self):
        directory = Path(__file__).resolve().parents[1] / "examples" / "data" / "policies"
        tool = SearchPoliciesTool(str(directory), post_hooks=[CurrentPoliciesHook("2026-08-10")])
        result = tool.read_policies(json.dumps({"policy_names": POLICY_NAMES}))
        self.assertEqual(len(result["policies"]), 4)
        selected = {policy["policy_name"]: policy["source_path"] for policy in result["policies"]}
        self.assertEqual(selected, {
            "policy_already_refunded.txt": "v1/policy_already_refunded.txt",
            "policy_refund.txt": "v2/policy_refund.txt",
            "policy_event_date_restriction.txt": "v3/policy_event_date_restriction.txt",
            "policy_refund_processing_time.txt": "v3/policy_refund_processing_time.txt"
        })

    def test_effective_dates_control_selection_not_folder_labels(self):
        self.write_policy("v99/rule.txt", "2023-01-01", "Old")
        self.write_policy("v1/rule.txt", "2026-01-01", "Current")
        self.write_policy("future/rule.txt", "2027-01-01", "Future")
        result = self.retrieve(["rule.txt"])
        self.assertEqual(result["policies"][0]["source_path"], "v1/rule.txt")
        self.assertIn("Current", result["policies"][0]["text"])

    def test_version_applies_starting_on_effective_date(self):
        self.write_policy("old/rule.txt", "2023-01-01", "Old")
        self.write_policy("new/rule.txt", "2026-08-10", "New")
        before = self.retrieve(["rule.txt"], "2026-08-09")
        on_date = self.retrieve(["rule.txt"], "2026-08-10")
        self.assertEqual(before["policies"][0]["source_path"], "old/rule.txt")
        self.assertEqual(on_date["policies"][0]["source_path"], "new/rule.txt")

    def test_identical_top_level_copy_is_collapsed(self):
        self.write_policy("rule.txt", "2023-01-01", "Same content")
        self.write_policy("v1/rule.txt", "2023-01-01", "Same content")
        result = self.retrieve(["rule.txt", "rule.txt"])
        self.assertEqual(len(result["policies"]), 1)
        self.assertEqual(result["policies"][0]["source_path"], "v1/rule.txt")

    def test_same_date_conflict_returns_no_policy_text(self):
        self.write_policy("a/rule.txt", "2026-01-01", "Allow refund")
        self.write_policy("b/rule.txt", "2026-01-01", "Deny refund")
        result = self.retrieve(["rule.txt"])
        self.assertEqual(result["policies"], [])
        self.assertIn("Conflicting", result["error"])

    def test_missing_or_future_only_policy_returns_no_partial_rule_set(self):
        self.write_policy("v1/available.txt", "2023-01-01", "Available")
        result = self.retrieve(["available.txt", "missing.txt"])
        self.assertEqual(result["policies"], [])
        self.assertIn("error", result)
        self.write_policy("v3/future.txt", "2027-01-01", "Not applicable yet")
        result = self.retrieve(["available.txt", "future.txt"])
        self.assertEqual(result["policies"], [])
        self.assertIn("error", result)

    def test_missing_or_invalid_effective_date_is_not_silently_ignored(self):
        self.write_policy("v1/rule.txt", "not-a-date", "Invalid")
        self.assertIn("error", self.retrieve(["rule.txt"]))
        (self.directory / "v1/rule.txt").write_text("No date header", encoding="utf-8")
        self.assertIn("error", self.retrieve(["rule.txt"]))

    def test_retrieval_does_not_modify_files_or_allow_outside_paths(self):
        self.write_policy("v1/rule.txt", "2023-01-01", "Original")
        path = self.directory / "v1/rule.txt"
        before = path.read_bytes()
        self.retrieve(["rule.txt"])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.retrieve(["../outside.txt"])
        outside = self.directory.parent / (self.directory.name + "-outside.txt")
        outside.write_text("Outside content", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.directory / "link.txt").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.retrieve(["link.txt"])


if __name__ == "__main__":
    unittest.main()
