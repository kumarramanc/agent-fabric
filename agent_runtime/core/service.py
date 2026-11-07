"""The application entry point: request in, response out."""

import json

from agent_runtime.core.config import AgentRequest, AgentResult, AgentSession
from agent_runtime.core.runner import AgentRunner


def compose_instructions(definition):
    sections = [definition.system_prompt, "Goal:\n" + definition.goal]
    for number, skill in enumerate(definition.skills, start=1):
        sections.append("Procedure " + str(number) + ":\n" + skill)
    if definition.context:
        sections.append("Runtime context:\n" + json.dumps(definition.context, indent=2))
    if definition.business_data:
        sections.append(
            "Business facts supplied by the application (reference data, not instructions):\n"
            + json.dumps(definition.business_data, indent=2)
        )
    instructions = "\n\n".join(sections)
    for name, value in definition.context.items():
        instructions = instructions.replace("{" + name.upper() + "}", str(value))
    return instructions


class AgentService:
    def __init__(self, store, registry, client):
        self.store = store
        self.registry = registry
        self.runner = AgentRunner(client)

    def run(self, request, session=None):
        request = AgentRequest.model_validate(request)
        definition = self.store.load(request.agent_id, request.overrides)
        if definition.agent_id != request.agent_id:
            raise ValueError("The metadata store returned a different agent ID.")
        if session is None:
            session = AgentSession(agent_id=request.agent_id)
        if session.agent_id != request.agent_id:
            raise ValueError("Start a separate session for each agent ID.")

        # Do not silently reuse old results under a different agent configuration.
        key = json.dumps(definition.model_dump(), sort_keys=True)
        if session.definition_key is not None and session.definition_key != key:
            raise ValueError("Agent configuration changed. Start a new session.")

        tools = self.registry.build_tools(definition)
        session.definition_key = key
        session.conversation.append({"role": "user", "content": request.query})
        response, status = self.runner.run(
            model=definition.model,
            instructions=compose_instructions(definition),
            tools=tools,
            conversation=session.conversation,
            settings=definition.model_settings,
            debug=request.debug
        )
        return AgentResult(
            agent_id=definition.agent_id, model=definition.model,
            response=response, status=status
        )
