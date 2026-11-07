"""Shared input validation, tool schemas, and post-hook execution."""

import pydantic as pydantic_lib


class ToolInput(pydantic_lib.BaseModel):
    # Reject unknown fields and incorrect types instead of guessing values.
    model_config = pydantic_lib.ConfigDict(extra="forbid", strict=True)


class ToolReasoning(ToolInput):
    """Brief explanations for a tool call, based on the available facts."""

    current_objective: str = pydantic_lib.Field(
        description="Briefly state the customer's goal being addressed."
    )
    why_selected_this_tool: str = pydantic_lib.Field(
        description="Give a short explanation of why this action is appropriate."
    )
    why_using_these_input_arguments: str = pydantic_lib.Field(
        description="Briefly identify the customer input or tool result supporting these values."
    )


def prepare_strict_schema(schema):
    """Make generated schemas follow the API's strict object requirements."""
    if isinstance(schema, dict):
        # Defaults are for local Python calls, not model-generated arguments.
        schema.pop("default", None)
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
        for value in schema.values():
            prepare_strict_schema(value)
    elif isinstance(schema, list):
        for value in schema:
            prepare_strict_schema(value)


class Tool:
    def __init__(self, name, description, input_model,
                 include_reason=False, post_hooks=None):
        self.name = name
        self.description = description
        self.include_reason = include_reason
        self.post_hooks = list(post_hooks) if post_hooks is not None else []
        self.input_model = input_model
        self.last_reason = None

        # Add reason to this tool's model without modifying the original model.
        if include_reason:
            self.input_model = pydantic_lib.create_model(
                input_model.__name__ + "WithReason",
                __base__=input_model,
                # Keep the reference bare: the API rejects description beside $ref.
                # ToolReasoning itself already describes the explanation fields.
                reason=(ToolReasoning, ...)
            )

    def to_json_schema(self):
        parameters = self.input_model.model_json_schema()
        prepare_strict_schema(parameters)
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
            "strict": True
        }

    def __call__(self, model_args):
        self.last_reason = None

        # Validate before allowing the underlying operation to run.
        try:
            args = self.input_model.model_validate_json(model_args)
        except pydantic_lib.ValidationError as error:
            return {
                "error": "Invalid tool arguments.",
                "details": error.errors(include_input=False, include_url=False)
            }

        if self.include_reason:
            self.last_reason = args.reason

        # The operation receives business arguments, without the trace explanation.
        arguments = args.model_dump(exclude={"reason"})
        output = self.execute(arguments)
        return self.run_post_hooks(output)

    def execute(self, arguments):
        raise NotImplementedError("Each tool must define its own operation.")

    def run_post_hooks(self, output):
        # Each hook receives the previous hook's result.
        for hook in self.post_hooks:
            output = hook(output)
        return output
