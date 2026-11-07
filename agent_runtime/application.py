"""Wire a metadata source, plugin registry, and model client into the framework."""

from pathlib import Path
import os
import dotenv
import openai

from agent_runtime.core.service import AgentService
from agent_runtime.core.store import LocalAgentStore
from agent_runtime.plugins import build_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_service(project_root=None, store=None, registry=None, client=None):
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    if client is None:
        dotenv.load_dotenv(root / ".env")
        client = openai.OpenAI()
    return AgentService(
        store=store if store is not None else LocalAgentStore(
            root, runtime_config_path=os.getenv("AGENT_RUNTIME_CONFIG")
        ),
        registry=registry if registry is not None else build_registry(),
        client=client
    )
