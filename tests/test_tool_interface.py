"""Check reason validation and sequential hooks without API requests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from agent_runtime.tools.tool_utils import Tool, ToolReasoning
from agent_runtime.tools.tools import OrderLookupTool, RefundOrderTool, SearchPoliciesTool


REASON = {
    "current_objective": "Find the customer's order.",
    "why_selected_this_tool": "An order lookup provides its current status.",
    "why_using_these_input_arguments": "The customer supplied order ID 1001."
}


class ToolInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.path = self.directory / "orders.json"
        self.path.write_text(json.dumps([{
            "order_id": "1001", "username": "user001",
            "refund_status": False, "refund_date": None
        }]), encoding="utf-8")

    def test_reason_is_added_without_changing_other_instances(self):
        plain = OrderLookupTool(str(self.path))
        explained = OrderLookupTool(str(self.path), include_reason=True)
        self.assertIsInstance(explained, Tool)
        self.assertNotIn("reason", plain.to_json_schema()["parameters"]["properties"])
        schema = explained.to_json_schema()["parameters"]
        self.assertIn("reason", schema["required"])
        self.assertEqual(set(schema["$defs"]["ToolReasoning"]["properties"]), set(REASON))
        self.assertFalse(schema["$defs"]["ToolReasoning"]["additionalProperties"])

    def test_reason_reference_has_no_unsupported_sibling_keywords(self):
        tools = [
            SearchPoliciesTool(str(self.directory), include_reason=True),
            OrderLookupTool(str(self.path), include_reason=True),
            RefundOrderTool(str(self.path), "2026-08-10", include_reason=True)
        ]
        for tool in tools:
            schema = tool.to_json_schema()["parameters"]
            self.assertEqual(schema["properties"]["reason"], {"$ref": "#/$defs/ToolReasoning"})
            self.assertIn("reason", schema["required"])

    def test_reason_is_validated_and_separated_from_operation_arguments(self):
        tool = OrderLookupTool(str(self.path), include_reason=True)
        operation = Mock(return_value={"order": {"order_id": "1001"}})
        tool.execute = operation
        result = tool.lookup_order(json.dumps({"order_id": "1001", "username": None, "reason": REASON}))
        self.assertEqual(result["order"]["order_id"], "1001")
        operation.assert_called_once_with({"order_id": "1001", "username": None})
        self.assertIsInstance(tool.last_reason, ToolReasoning)

    def test_invalid_reason_never_runs_refund_or_hooks(self):
        hook = Mock()
        tool = RefundOrderTool(str(self.path), "2026-08-10", include_reason=True, post_hooks=[hook])
        before = self.path.read_bytes()
        for arguments in [
            {"order_id": "1001"},
            {"order_id": "1001", "reason": {"current_objective": "Refund"}},
            {"order_id": "1001", "reason": dict(REASON, current_objective=123)}
        ]:
            self.assertIn("error", tool(json.dumps(arguments)))
        hook.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_post_hooks_run_in_sequence_after_the_operation(self):
        observed = []

        def first(output):
            observed.append("first")
            self.assertEqual(output["order"]["order_id"], "1001")
            return {"first_hook_result": output["order"]["username"]}

        def second(output):
            observed.append("second")
            self.assertEqual(output, {"first_hook_result": "user001"})
            return {"final": output["first_hook_result"]}

        tool = OrderLookupTool(str(self.path), post_hooks=[first, second])
        self.assertEqual(tool('{"order_id": "1001"}'), {"final": "user001"})
        self.assertEqual(observed, ["first", "second"])
        self.assertNotIn("post_hooks", json.dumps(tool.to_json_schema()))
        self.assertNotIn("first_hook_result", json.dumps(tool.to_json_schema()))

    def test_invalid_types_and_extra_fields_are_rejected(self):
        tool = RefundOrderTool(str(self.path), "2026-08-10")
        before = self.path.read_bytes()
        for arguments in ['not JSON', '[]', '{"order_id": 1001}', '{"order_id": "1001", "extra": true}']:
            self.assertIn("error", tool(arguments))
        self.assertEqual(self.path.read_bytes(), before)

    def test_hooks_are_not_shared_between_tools(self):
        hooks = [lambda output: {"changed": True}]
        first = OrderLookupTool(str(self.path), post_hooks=hooks)
        second = OrderLookupTool(str(self.path))
        hooks.clear()
        self.assertEqual(len(first.post_hooks), 1)
        self.assertEqual(second.post_hooks, [])

    def test_readable_methods_still_apply_hooks_and_keep_operations(self):
        directory = self.directory / "policies"
        directory.mkdir()
        (directory / "example.txt").write_text("Policy content", encoding="utf-8")
        hook = Mock(side_effect=lambda output: dict(output, checked=True))
        search = SearchPoliciesTool(str(directory), post_hooks=[hook])
        result = search.read_policies('{"policy_names": ["example.txt"]}')
        self.assertEqual(result["policies"][0]["text"], "Policy content")
        self.assertTrue(result["checked"])
        refund = RefundOrderTool(str(self.path), "2026-08-10")
        self.assertTrue(refund.refund_order('{"order_id": "1001"}')["order"]["refund_status"])
        before = self.path.read_bytes()
        self.assertIn("error", refund('{"order_id": "1001"}'))
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
