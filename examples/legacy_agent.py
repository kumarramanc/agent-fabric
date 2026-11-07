"""Compatibility entry point for the earlier learning examples.

New applications use agent_runtime.application.create_service() and AgentRequest instead.
"""

from agent_runtime.core.config import ModelSettings
from agent_runtime.core.runner import AgentRunner


def run_agent(client, model, instructions, conversation,
              search_policies_tool, order_lookup_tool, refund_order_tool):
    tools = {
        tool.name: tool
        for tool in [search_policies_tool, order_lookup_tool, refund_order_tool]
    }
    answer, status = AgentRunner(client).run(
        model=model, instructions=instructions, tools=tools,
        conversation=conversation,
        settings=ModelSettings(reasoning_effort="none")
    )
    return answer
