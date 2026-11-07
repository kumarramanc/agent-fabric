"""Application plugin registration. The shared framework imports no domain tools."""

from agent_runtime.core.registry import PluginRegistry
from agent_runtime.tools.tools import SearchPoliciesTool, OrderLookupTool, RefundOrderTool
from agent_runtime.tools.policy_hooks import CurrentPoliciesHook


def build_registry():
    registry = PluginRegistry()
    registry.register_tool("ticketing.search_policies", SearchPoliciesTool)
    registry.register_tool("ticketing.order_lookup", OrderLookupTool)
    registry.register_tool("ticketing.refund_order", RefundOrderTool)
    registry.register_hook("policies.current_versions", CurrentPoliciesHook)
    return registry
