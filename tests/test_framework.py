"""Verify dynamic configuration and execution without paid model requests."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.core.config import AgentDefinition, AgentRequest, AgentSession, ModelSettings
from agent_runtime.core.registry import PluginRegistry
from agent_runtime.core.runner import AgentRunner
from agent_runtime.core.service import AgentService
from agent_runtime.core.store import LocalAgentStore
from agent_runtime.plugins import build_registry
from agent_runtime.tools.tool_utils import Tool, ToolInput
from test_agent import FakeClient, model_response, tool_call


ROOT = Path(__file__).resolve().parents[1]


class EchoInput(ToolInput):
    text: str


class EchoTool(Tool):
    def __init__(self, prefix="", include_reason=False, post_hooks=None):
        super().__init__("echo", "Echo supplied text.", EchoInput, include_reason, post_hooks)
        self.prefix = prefix

    def execute(self, arguments):
        return {"text": self.prefix + arguments["text"]}


class MemoryStore:
    """Example database/service adapter: resolved definitions need no local files."""
    def load(self, agent_id, overrides=None):
        return AgentDefinition(
            agent_id=agent_id, goal="Echo text", model="test-model",
            system_prompt="Use the echo tool.",
            tools=[{"plugin": "example.echo", "settings": {"prefix": "OK: "}}]
        )


class FrameworkTests(unittest.TestCase):
    def customer_bindings(self):
        # Test locations belong in test setup, never in the runtime catalog.
        return {
            "context": {"current_date": "2026-08-10"},
            "data_sources": {
                "orders_path": str(ROOT / "examples/data/customer_orders.json"),
                "policies_dir": str(ROOT / "examples/data/policies")
            }
        }

    def test_local_metadata_loads_prompt_skill_and_data_bindings(self):
        store = LocalAgentStore(ROOT)
        unbound = store.load("customer_support")
        self.assertEqual(unbound.data_sources, {})
        self.assertEqual(unbound.context, {})
        with self.assertRaisesRegex(ValueError, "Missing runtime binding"):
            build_registry().build_tools(unbound)
        definition = store.load("customer_support", self.customer_bindings())
        self.assertEqual(definition.context["current_date"], "2026-08-10")
        self.assertEqual(len(definition.skills), 1)
        self.assertIn("Retrieve all applicable", definition.skills[0])
        tools = build_registry().build_tools(definition)
        self.assertEqual(set(tools), {"search_policies", "order_lookup", "refund_order"})
        self.assertEqual(len(tools["search_policies"].post_hooks), 1)
        self.assertTrue(Path(tools["order_lookup"].orders_path).is_absolute())

    def test_model_goal_skills_context_and_business_facts_can_be_overridden(self):
        client = FakeClient([model_response([], "Done.")])
        service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
        result = service.run(AgentRequest(
            agent_id="writing_assistant", query="Rewrite this.", overrides={
                "model": "another-model", "goal": "Make a short summary.",
                "system_prompt": "You summarize text.",
                "skills": ["Keep exactly one sentence."],
                "business_data": {"product": "Example"},
                "context": {"language": "English"},
                "model_settings": {"reasoning_effort": None}
            }
        ))
        request = client.requests[0]
        self.assertEqual(result.model, "another-model")
        self.assertIn("Make a short summary.", request["instructions"])
        self.assertIn("Keep exactly one sentence.", request["instructions"])
        self.assertIn('"product": "Example"', request["instructions"])
        self.assertIn('"language": "English"', request["instructions"])
        self.assertNotIn("reasoning", request)
        self.assertNotIn("tools", request)

    def test_registry_dispatches_a_non_ticketing_tool_with_an_external_store(self):
        registry = PluginRegistry()
        registry.register_tool("example.echo", EchoTool)
        client = FakeClient([
            model_response([tool_call("echo", {"text": "hello"}, "echo1")]),
            model_response([], "OK: hello")
        ])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = AgentService(MemoryStore(), registry, client).run({
                "agent_id": "external_agent", "query": "Echo hello."
            })
        self.assertEqual(result.response, "OK: hello")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual([tool["name"] for tool in client.requests[0]["tools"]], ["echo"])
        payload = client.requests[1]["input"][-1]
        self.assertEqual(json.loads(payload["output"]), {"text": "OK: hello"})

    def test_disabled_tool_never_executes(self):
        definition = LocalAgentStore(ROOT).load("customer_support", {**self.customer_bindings(), "tools": [
            {"plugin": "ticketing.order_lookup", "settings": {"orders_path": "${orders_path}"}}
        ]})
        tools = build_registry().build_tools(definition)
        runner = AgentRunner(FakeClient([]))
        result = runner.execute_tool(tools, "refund_order", '{"order_id":"1001"}')
        self.assertIn("disabled", result["error"])
        self.assertEqual(set(tools), {"order_lookup"})

    def test_unknown_plugin_or_binding_fails_before_model_call(self):
        for spec in [
            {"plugin": "not.registered"},
            {"plugin": "ticketing.order_lookup", "settings": {"orders_path": "${missing}"}}
        ]:
            client = FakeClient([])
            service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
            with self.assertRaises(ValueError):
                service.run({"agent_id": "customer_support", "query": "Hello", "overrides": {"tools": [spec]}})
            self.assertEqual(client.requests, [])

    def test_business_data_source_override_reaches_tool_without_exposing_path_to_model(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder, "orders.json")
            file.write_text('[{"order_id":"special","username":"demo"}]', encoding="utf-8")
            bindings = self.customer_bindings()
            bindings["data_sources"]["orders_path"] = str(file)
            definition = LocalAgentStore(ROOT).load("customer_support", bindings)
            tools = build_registry().build_tools(definition)
            self.assertEqual(tools["order_lookup"]('{"order_id":"special"}')["order"]["username"], "demo")
            self.assertNotIn(str(file), json.dumps(tools["order_lookup"].to_json_schema()))

    def test_sessions_keep_context_but_cannot_be_shared_across_agents(self):
        client = FakeClient([model_response([], "First answer."), model_response([], "Second answer.")])
        service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
        session = AgentSession(agent_id="writing_assistant")
        service.run({"agent_id": "writing_assistant", "query": "First"}, session)
        service.run({"agent_id": "writing_assistant", "query": "Second"}, session)
        self.assertEqual(client.requests[1]["input"][0]["content"], "First")
        with self.assertRaises(ValueError):
            service.run({"agent_id": "customer_support", "query": "Hello"}, session)
        with self.assertRaises(ValueError):
            service.run({"agent_id": "writing_assistant", "query": "Hello", "overrides": {"model": "different"}}, session)

    def test_debug_is_opt_in(self):
        client = FakeClient([model_response([], "Hello")])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            AgentService(LocalAgentStore(ROOT), build_registry(), client).run({
                "agent_id": "writing_assistant", "query": "Hello", "debug": True
            })
        self.assertIn("[MODEL INPUT]", output.getvalue())
        self.assertIn("[MODEL OUTPUT]", output.getvalue())

    def test_agent_id_and_unknown_configuration_fields_are_validated(self):
        store = LocalAgentStore(ROOT)
        with self.assertRaises(ValueError):
            store.load("../customer_support")
        with self.assertRaises(ValueError):
            store.load("customer_support", {"unexpected_setting": True})

    def test_default_cli_has_only_customer_conversation_and_no_import_side_effects(self):
        from agent_runtime import cli as main
        client = FakeClient([model_response([], "A concise answer.")])
        service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
        output = io.StringIO()
        with patch.object(main, "create_service", return_value=service), contextlib.redirect_stdout(output):
            code = main.main(["--agent", "writing_assistant", "--query", "Rewrite hello"])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "A concise answer.\n")

    def test_maximum_step_limit_does_not_execute_a_late_tool_call(self):
        tool = EchoTool()
        client = FakeClient([model_response([tool_call("echo", {"text": "hello"}, "late")])])
        conversation = [{"role": "user", "content": "Hello"}]
        with patch.object(tool, "execute", side_effect=AssertionError("Must not run")):
            answer, status = AgentRunner(client).run("test", "Test", {"echo": tool}, conversation, ModelSettings(max_requests=1))
        self.assertEqual(status, "failed")
        self.assertEqual(conversation[-2]["call_id"], "late")
        self.assertIn("step limit", answer)

    def test_request_file_limits_tools_and_prints_only_the_answer(self):
        from agent_runtime import cli as main
        client = FakeClient([model_response([], "The order status is available.")])
        service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
        output = io.StringIO()
        with patch.object(main, "create_service", return_value=service), contextlib.redirect_stdout(output):
            code = main.main(["--request", str(ROOT / "examples/request.json")])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "The order status is available.\n")
        self.assertEqual(
            {tool["name"] for tool in client.requests[0]["tools"]},
            {"order_lookup", "search_policies"}
        )

    def test_interactive_chat_reaches_input_and_keeps_follow_up_context(self):
        from agent_runtime import cli as main
        client = FakeClient([model_response([], "First answer"), model_response([], "Second answer")])
        service = AgentService(LocalAgentStore(ROOT), build_registry(), client)
        output = io.StringIO()
        with patch.object(main, "create_service", return_value=service), patch("builtins.input", side_effect=["First", "Second", "quit"]), contextlib.redirect_stdout(output):
            code = main.main(["--agent", "writing_assistant"])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "Agent: First answer\nAgent: Second answer\n")
        self.assertEqual(client.requests[1]["input"][0]["content"], "First")


    def test_cli_requires_explicit_agent_id_before_creating_service(self):
        from agent_runtime import cli
        for arguments in [[], ["--query", "Hello"], ["--agent", ""], ["--agent", "   "]]:
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with patch.object(cli, "create_service") as create, contextlib.redirect_stdout(output):
                    code = cli.main(arguments)
                self.assertEqual(code, 1)
                self.assertIn("Agent ID is required", output.getvalue())
                create.assert_not_called()

    def test_invalid_request_file_agent_id_never_creates_service(self):
        from agent_runtime import cli
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "request.json")
            for payload in [{"query": "Hello"}, {"agent_id": "", "query": "Hello"}, {"agent_id": "   ", "query": "Hello"}]:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with patch.object(cli, "create_service") as create, contextlib.redirect_stdout(io.StringIO()):
                        code = cli.main(["--request", str(path)])
                    self.assertEqual(code, 1)
                    create.assert_not_called()

    def test_service_rejects_missing_or_blank_agent_before_store_or_model(self):
        client = FakeClient([])
        store = LocalAgentStore(ROOT)
        service = AgentService(store, build_registry(), client)
        with patch.object(store, "load") as load:
            for payload in [{"query": "Hello"}, {"agent_id": "", "query": "Hello"}, {"agent_id": "   ", "query": "Hello"}]:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    service.run(payload)
            load.assert_not_called()
        self.assertEqual(client.requests, [])


    def test_demo_uses_one_dataset_and_validation_does_not_reset_records(self):
        from examples.validate_data import validate_data
        directory = ROOT / "examples/data"
        orders = directory / "customer_orders.json"
        self.assertEqual(list(directory.rglob("customer_orders.json")), [orders])
        self.assertFalse((directory / "original").exists())
        self.assertFalse((directory / "working").exists())
        before = orders.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            validate_data()
        self.assertEqual(orders.read_bytes(), before)
        payload = json.loads((ROOT / "examples/request.json").read_text())
        definition = LocalAgentStore(ROOT).load(payload["agent_id"], payload["overrides"])
        self.assertEqual(definition.data_sources["orders_path"], str(orders.resolve()))
        self.assertEqual(definition.data_sources["policies_dir"], str((directory / "policies").resolve()))


if __name__ == "__main__":
    unittest.main()
