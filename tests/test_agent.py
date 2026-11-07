"""Check the agent loop without sending requests to OpenAI."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from examples import legacy_agent as customer_support_agent
from agent_runtime.tools.tools import SearchPoliciesTool, OrderLookupTool, RefundOrderTool
from agent_runtime.tools.policy_hooks import CurrentPoliciesHook


def tool_call(name, arguments, call_id):
    return {
        "type": "function_call", "name": name,
        "arguments": json.dumps(arguments), "call_id": call_id
    }


def model_response(items, text="", status="completed"):
    if text:
        items = items + [{
            "type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]
        }]
    return SimpleNamespace(
        output=[SimpleNamespace(**item) for item in items],
        output_text=text, status=status,
        model_dump=lambda **kwargs: {"output": items, "status": status}
    )


class FakeClient:
    def __init__(self, responses):
        self.responses_to_return = iter(responses)
        self.requests = []
        self.responses = self

    def with_options(self, **kwargs):
        return self

    def create(self, **request):
        # Save a snapshot, since the conversation grows after each request.
        self.requests.append(json.loads(json.dumps(request)))
        return next(self.responses_to_return)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        directory = Path(self.folder.name)
        self.policies_dir = directory / "policies"
        self.policies_dir.mkdir()
        (self.policies_dir / "policy_refund.txt").write_text(
            "Refunds allowed within 14 days.", encoding="utf-8"
        )
        self.orders_path = directory / "orders.json"
        self.orders_path.write_text(json.dumps([{
            "order_id": "1001", "username": "user001",
            "refund_status": False, "refund_date": None
        }]), encoding="utf-8")
        self.search = SearchPoliciesTool(str(self.policies_dir))
        self.lookup = OrderLookupTool(str(self.orders_path))
        self.refund = RefundOrderTool(str(self.orders_path), "2026-08-10")

    def run_agent(self, client, conversation):
        with contextlib.redirect_stdout(io.StringIO()):
            return customer_support_agent.run_agent(
                client, "gpt-6-luna", "Test instructions", conversation,
                self.search, self.lookup, self.refund
            )

    def test_complete_loop_returns_results_and_preserves_context(self):
        client = FakeClient([
            model_response([tool_call("search_policies", {"policy_names": ["policy_refund.txt"]}, "p1")]),
            model_response([tool_call("order_lookup", {"order_id": None, "username": "user001"}, "o1")]),
            model_response([tool_call("refund_order", {"order_id": "1001"}, "r1")]),
            model_response([], "Your simulated refund is recorded.")
        ])
        conversation = [{"role": "user", "content": "Refund user001's order."}]
        answer = self.run_agent(client, conversation)
        self.assertEqual(answer, "Your simulated refund is recorded.")
        self.assertTrue(json.loads(self.orders_path.read_text())[0]["refund_status"])
        results = [item for item in conversation if item.get("type") == "function_call_output"]
        self.assertEqual([item["call_id"] for item in results], ["p1", "o1", "r1"])
        self.assertIn("policies", json.loads(results[0]["output"]))
        self.assertEqual(json.loads(results[1]["output"])["order"]["order_id"], "1001")
        self.assertEqual(len(client.requests[0]["tools"]), 3)
        self.assertEqual(client.requests[0]["instructions"], "Test instructions")
        self.assertFalse(client.requests[0]["store"])
        # The next request includes both the model call and its tool result.
        self.assertEqual(client.requests[1]["input"][-1]["call_id"], "p1")

    def test_follow_up_keeps_previous_customer_and_agent_messages(self):
        client = FakeClient([
            model_response([], "What is your order ID or username?"),
            model_response([], "Thank you for providing your ID.")
        ])
        conversation = [{"role": "user", "content": "I need a refund."}]
        self.run_agent(client, conversation)
        conversation.append({"role": "user", "content": "1001"})
        self.run_agent(client, conversation)
        self.assertEqual(len(client.requests[1]["input"]), 3)
        self.assertEqual(client.requests[1]["input"][0]["content"], "I need a refund.")
        self.assertEqual(client.requests[1]["input"][-1]["content"], "1001")

    def test_only_current_policy_text_is_sent_back_to_model(self):
        (self.policies_dir / "policy_refund.txt").write_text(
            "EFFECTIVE DATE: 2023-01-01\nOUTDATED POLICY", encoding="utf-8"
        )
        version = self.policies_dir / "v2"
        version.mkdir()
        (version / "policy_refund.txt").write_text(
            "EFFECTIVE DATE: 2026-01-01\nCURRENT POLICY", encoding="utf-8"
        )
        self.search.post_hooks = [CurrentPoliciesHook("2026-08-10")]
        client = FakeClient([
            model_response([tool_call("search_policies", {"policy_names": ["policy_refund.txt"]}, "p1")]),
            model_response([], "Policy retrieved.")
        ])
        self.run_agent(client, [{"role": "user", "content": "What is the refund policy?"}])
        payload = client.requests[1]["input"][-1]["output"]
        self.assertIn("CURRENT POLICY", payload)
        self.assertNotIn("OUTDATED POLICY", payload)
        self.assertEqual(len(json.loads(payload)["policies"]), 1)

    def test_model_receives_reason_schema_and_post_hook_result(self):
        def replace_output(output):
            return {"checked_order_id": output["order"]["order_id"]}

        self.lookup = OrderLookupTool(
            str(self.orders_path), include_reason=True, post_hooks=[replace_output]
        )
        reason = {
            "current_objective": "Find the customer's order.",
            "why_selected_this_tool": "Read its current status.",
            "why_using_these_input_arguments": "Customer supplied 1001."
        }
        client = FakeClient([
            model_response([tool_call("order_lookup", {"order_id": "1001", "username": None, "reason": reason}, "o1")]),
            model_response([], "Order found.")
        ])
        conversation = [{"role": "user", "content": "Find order 1001."}]
        self.assertEqual(self.run_agent(client, conversation), "Order found.")
        schema = client.requests[0]["tools"][1]["parameters"]
        self.assertIn("reason", schema["required"])
        result = client.requests[1]["input"][-1]
        self.assertEqual(result["call_id"], "o1")
        self.assertEqual(json.loads(result["output"]), {"checked_order_id": "1001"})

    def test_unknown_tool_and_malformed_arguments_return_errors_to_model(self):
        malformed = tool_call("order_lookup", {}, "bad-json")
        malformed["arguments"] = "not JSON"
        client = FakeClient([
            model_response([tool_call("unknown", {}, "unknown1")]),
            model_response([malformed]),
            model_response([], "I could not look up that order.")
        ])
        conversation = [{"role": "user", "content": "Find my order."}]
        self.run_agent(client, conversation)
        results = [item for item in conversation if item.get("type") == "function_call_output"]
        self.assertEqual(len(results), 2)
        for item in results:
            self.assertIn("error", json.loads(item["output"]))

    def test_repeated_calls_end_with_tools_disabled(self):
        responses = []
        for number in range(9):
            responses.append(model_response([tool_call("order_lookup", {"order_id": "missing", "username": None}, str(number))]))
        responses.append(model_response([], "I could not find your order."))
        client = FakeClient(responses)
        self.run_agent(client, [{"role": "user", "content": "Find my order."}])
        self.assertEqual(len(client.requests), 10)
        self.assertEqual(client.requests[-1]["tool_choice"], "none")

    def test_username_lookup_returns_all_matches_and_does_not_guess(self):
        orders = json.loads(self.orders_path.read_text())
        orders.append({"order_id": "1002", "username": "user001"})
        self.orders_path.write_text(json.dumps(orders), encoding="utf-8")
        result = self.lookup.lookup_order('{"order_id": null, "username": "user001"}')
        self.assertEqual(len(result["orders"]), 2)
        self.assertIn("specify", result["message"])
        mismatch = self.lookup.lookup_order('{"order_id": "1001", "username": "other"}')
        self.assertIn("error", mismatch)


if __name__ == "__main__":
    unittest.main()
