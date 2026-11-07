"""Generic model/tool loop. No ticketing rules or tool-specific branches."""

import json
import openai

from agent_runtime.tracing import ConsoleOutput
from agent_runtime.core.config import ModelSettings


class AgentRunner:
    def __init__(self, client):
        self.client = client

    def run(self, model, instructions, tools, conversation, settings=None, debug=False):
        settings = settings or ModelSettings()
        trace = ConsoleOutput(enabled=debug)
        schemas = [tool.to_json_schema() for tool in tools.values()]

        for number in range(1, settings.max_requests + 1):
            request = {
                "model": model,
                "instructions": instructions,
                "input": conversation,
                "max_output_tokens": settings.max_output_tokens,
                "store": False
            }
            if schemas:
                request["tools"] = schemas
                request["parallel_tool_calls"] = False
                if number == settings.max_requests:
                    request["tool_choice"] = "none"
            if settings.reasoning_effort is not None:
                request["reasoning"] = {"effort": settings.reasoning_effort}

            trace.print_model_input(request)
            try:
                response = self.client.with_options(
                    timeout=settings.timeout_seconds, max_retries=0
                ).responses.create(**request)
            except openai.APIError as error:
                trace.print_model_output({
                    "error": type(error).__name__,
                    "code": getattr(error, "code", None),
                    "param": getattr(error, "param", None)
                })
                code = getattr(error, "code", None) or type(error).__name__
                answer = "The model request failed (" + str(code) + "). Please try again or check the configuration."
                return self.finish(conversation, answer, "failed")

            data = response.model_dump(mode="json", by_alias=True, exclude_none=True)
            trace.print_model_output(data)
            if response.status != "completed":
                return self.finish(conversation, "The model could not complete this request. Please try again.", "failed")

            # Preserve all model output items so the next round has complete context.
            conversation.extend(data["output"])
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                if response.output_text:
                    return response.output_text, "completed"
                return self.finish(conversation, "The model did not return an answer. Please try again.", "failed")

            for call in calls:
                trace.print_tool_input(call.name, call.arguments)
                if number == settings.max_requests:
                    output = {"error": "The maximum number of model requests was reached."}
                else:
                    output = self.execute_tool(tools, call.name, call.arguments)
                trace.print_tool_output(call.name, output)
                conversation.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(output)
                })

        return self.finish(conversation, "I could not finish within the configured step limit. Please clarify your request.", "failed")

    def execute_tool(self, tools, name, arguments):
        # Only tools explicitly enabled for this invocation can execute.
        if name not in tools:
            return {"error": "Unknown or disabled tool. Use one of the provided tools."}
        try:
            output = tools[name](arguments)
            # Check the plugin result before adding it to the model conversation.
            json.dumps(output, allow_nan=False)
            return output
        except Exception as error:
            return {"error": "Tool could not complete the request: " + type(error).__name__}

    def finish(self, conversation, answer, status):
        conversation.append({"role": "assistant", "content": answer})
        return answer, status
