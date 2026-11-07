"""Verify external bindings and an artifact free of local/demo resources."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from agent_runtime.core.store import LocalAgentStore
from agent_runtime.plugins import build_registry
from scripts.build_runtime import build_runtime


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_agent_catalog_has_no_sample_bindings_or_practice_date(self):
        metadata = json.loads((ROOT / "agents/customer_support/agent.json").read_text())
        self.assertNotIn("data_sources", metadata)
        self.assertNotIn("context", metadata)
        definition = LocalAgentStore(ROOT).load("customer_support")
        with self.assertRaisesRegex(ValueError, "AGENT_RUNTIME_CONFIG"):
            build_registry().build_tools(definition)

    def test_external_settings_resolve_against_deployment_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder).resolve()
            runtime = folder / "runtime.json"
            runtime.write_text(json.dumps({"customer_support": {
                "data_sources": {"orders_path": "records/orders.json", "policies_dir": "policies"},
                "context": {"current_date": "2026-11-06"},
                "model": "deployment-model"
            }}), encoding="utf-8")
            store = LocalAgentStore(ROOT, runtime)
            definition = store.load("customer_support")
            self.assertEqual(definition.data_sources["orders_path"], str(folder / "records/orders.json"))
            self.assertEqual(definition.model, "deployment-model")
            tools = build_registry().build_tools(definition)
            self.assertEqual(tools["order_lookup"].orders_path, str(folder / "records/orders.json"))
            overridden = store.load("customer_support", {"model": "caller-model", "context": {"current_date": "2026-11-07"}})
            self.assertEqual(overridden.model, "caller-model")
            self.assertEqual(overridden.context["current_date"], "2026-11-07")
            self.assertEqual(overridden.data_sources, definition.data_sources)

    def test_archive_excludes_secrets_samples_tests_and_legacy_helpers(self):
        with tempfile.TemporaryDirectory() as folder:
            artifact = build_runtime(Path(folder) / "runtime.zip")
            with ZipFile(artifact) as archive:
                names = archive.namelist()
                self.assertIn("main.py", names)
                self.assertIn("agent_runtime/core/runner.py", names)
                self.assertIn("agents/customer_support/agent.json", names)
                self.assertIn(".env.example", names)
                for name in names:
                    self.assertFalse(name.startswith(("data_sources/", "data_sources_COPY/", "examples/", "tests/", ".venv/", "customer_support_agent/")), name)
                for name in [".env", "prepare_demo.py", "helper_utils.py", "customer_support_agent.py", "test_connection.py", "agents/writing_assistant/agent.json"]:
                    self.assertNotIn(name, names)
                for name in names:
                    if name.endswith((".py", ".json", ".md")):
                        text = archive.read(name).decode("utf-8")
                        self.assertNotIn("data_sources_COPY", text, name)
                        self.assertNotIn("2026-08-10", text, name)
                archive.extractall(Path(folder) / "extracted")
            # The built artifact can start without importing omitted source helpers.
            result = subprocess.run([sys.executable, "main.py", "--help"], cwd=Path(folder) / "extracted", capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Agent Fabric", result.stdout)


if __name__ == "__main__":
    unittest.main()
