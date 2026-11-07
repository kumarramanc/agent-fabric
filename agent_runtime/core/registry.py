"""Instantiate only explicitly registered tool and hook plugins."""


class PluginRegistry:
    def __init__(self):
        self.tools = {}
        self.hooks = {}

    def register_tool(self, plugin_id, factory):
        if plugin_id in self.tools:
            raise ValueError("Tool plugin already registered: " + plugin_id)
        self.tools[plugin_id] = factory

    def register_hook(self, plugin_id, factory):
        if plugin_id in self.hooks:
            raise ValueError("Hook plugin already registered: " + plugin_id)
        self.hooks[plugin_id] = factory

    def build_tools(self, definition):
        bindings = dict(definition.data_sources)
        if set(bindings) & set(definition.context):
            raise ValueError("Data-source names and context names must be distinct.")
        bindings.update(definition.context)
        enabled = {}

        for tool_config in definition.tools:
            if tool_config.plugin not in self.tools:
                raise ValueError("Unknown tool plugin: " + tool_config.plugin)
            hooks = []
            for hook_config in tool_config.post_hooks:
                if hook_config.plugin not in self.hooks:
                    raise ValueError("Unknown hook plugin: " + hook_config.plugin)
                settings = self.resolve(hook_config.settings, bindings)
                hooks.append(self.hooks[hook_config.plugin](**settings))

            settings = self.resolve(tool_config.settings, bindings)
            tool = self.tools[tool_config.plugin](
                **settings, include_reason=tool_config.include_reason, post_hooks=hooks
            )
            if tool.name in enabled:
                raise ValueError("Two enabled tools have the same call name: " + tool.name)
            enabled[tool.name] = tool
        return enabled

    def resolve(self, value, bindings):
        # A whole value such as ${orders_path} references a configured binding.
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            name = value[2:-1]
            if name not in bindings:
                raise ValueError(
                    "Missing runtime binding: " + name
                    + ". Supply deployment settings through AGENT_RUNTIME_CONFIG "
                    "or provide data_sources/context in request overrides."
                )
            return bindings[name]
        if isinstance(value, dict):
            return {name: self.resolve(item, bindings) for name, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item, bindings) for item in value]
        return value
