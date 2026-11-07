"""The data contract shared by agent callers, stores, and the runner."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HookConfig(ConfigModel):
    plugin: str
    settings: dict[str, Any] = Field(default_factory=dict)


class ToolConfig(ConfigModel):
    plugin: str
    settings: dict[str, Any] = Field(default_factory=dict)
    include_reason: bool = False
    post_hooks: list[HookConfig] = Field(default_factory=list)


class ModelSettings(ConfigModel):
    # Omit reasoning_effort for models that do not support that parameter.
    reasoning_effort: str | None = None
    max_output_tokens: int = Field(default=2000, ge=1)
    timeout_seconds: float = Field(default=45, gt=0)
    max_requests: int = Field(default=10, ge=1, le=100)


class AgentDefinition(ConfigModel):
    agent_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    goal: str = Field(min_length=1)
    model: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    data_sources: dict[str, str] = Field(default_factory=dict)
    business_data: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    model_settings: ModelSettings = Field(default_factory=ModelSettings)


class AgentRequest(ConfigModel):
    agent_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    query: str = Field(min_length=1)
    # Trusted application configuration, not instructions extracted from customer text.
    overrides: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False


class AgentSession(ConfigModel):
    agent_id: str
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    definition_key: str | None = None


class AgentResult(ConfigModel):
    agent_id: str
    model: str
    response: str
    status: str = "completed"
