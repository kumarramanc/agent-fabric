"""Local metadata adapter. A database adapter can implement the same load method."""

import json
import re
from pathlib import Path
from typing import Protocol

from agent_runtime.core.config import AgentDefinition


class AgentStore(Protocol):
    def load(self, agent_id: str, overrides: dict | None = None) -> AgentDefinition:
        ...


class LocalAgentStore:
    def __init__(self, project_root, runtime_config_path=None):
        self.project_root = Path(project_root).resolve()
        self.runtime_config_path = Path(runtime_config_path).resolve() if runtime_config_path else None

    def load(self, agent_id, overrides=None):
        # Agent IDs select catalog entries, not arbitrary filesystem paths.
        if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
            raise ValueError("Agent IDs may contain letters, numbers, hyphens, and underscores.")
        path = self.project_root / "agents" / agent_id / "agent.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Agent metadata must be a JSON object.")
        runtime_overrides = self.load_runtime_overrides(agent_id)
        metadata = self.merge(metadata, runtime_overrides)
        overrides = dict(overrides or {})
        if "agent_id" in overrides and overrides["agent_id"] != agent_id:
            raise ValueError("An override cannot change the selected agent ID.")

        # Replace scalar/list values; merge dictionaries so one data source or
        # model setting can change without discarding all the other settings.
        metadata = self.merge(metadata, overrides)

        if metadata.get("agent_id") != agent_id:
            raise ValueError("The catalog entry's agent_id must match its directory.")

        # A store returns resolved text, not file references, to the generic runner.
        prompt_file = metadata.pop("system_prompt_file", None)
        if prompt_file:
            metadata["system_prompt"] = self.read_text(prompt_file)
        skills = list(metadata.get("skills", []))
        for skill_file in metadata.pop("skill_files", []):
            skills.append(self.read_text(skill_file))
        metadata["skills"] = skills

        # Only this local adapter interprets data-source locations as local paths.
        metadata["data_sources"] = {
            name: str(self.local_path(location))
            for name, location in metadata.get("data_sources", {}).items()
        }
        return AgentDefinition.model_validate(metadata)

    def merge(self, metadata, overrides):
        metadata = dict(metadata)
        for name, value in overrides.items():
            if name in {"context", "data_sources", "business_data", "model_settings"}:
                metadata[name] = {**metadata.get(name, {}), **value}
            else:
                metadata[name] = value
        if "system_prompt" in overrides:
            metadata.pop("system_prompt_file", None)
        if "system_prompt_file" in overrides:
            metadata.pop("system_prompt", None)
        if "skills" in overrides and "skill_files" not in overrides:
            metadata["skill_files"] = []
        return metadata

    def load_runtime_overrides(self, agent_id):
        if self.runtime_config_path is None:
            return {}
        catalog = json.loads(self.runtime_config_path.read_text(encoding="utf-8"))
        if not isinstance(catalog, dict):
            raise ValueError("Deployment configuration must be an object keyed by agent ID.")
        overrides = catalog.get(agent_id, {})
        if not isinstance(overrides, dict):
            raise ValueError("Each deployment configuration must be a JSON object.")
        overrides = dict(overrides)
        # Deployment file references resolve relative to that external file.
        if "data_sources" in overrides:
            overrides["data_sources"] = {
                name: self.deployment_path(location)
                for name, location in overrides["data_sources"].items()
            }
        if "system_prompt_file" in overrides:
            overrides["system_prompt_file"] = self.deployment_path(overrides["system_prompt_file"])
        if "skill_files" in overrides:
            overrides["skill_files"] = [self.deployment_path(path) for path in overrides["skill_files"]]
        return overrides

    def deployment_path(self, location):
        path = Path(location)
        if not path.is_absolute():
            path = self.runtime_config_path.parent / path
        return str(path.resolve())

    def local_path(self, location):
        path = Path(location)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def read_text(self, location):
        return self.local_path(location).read_text(encoding="utf-8")
