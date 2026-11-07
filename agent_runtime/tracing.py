"""Trace model requests, model responses, and tool calls in the terminal."""

import json as json_lib


class ConsoleOutput:
    def __init__(self, enabled=False):
        self.enabled = enabled

    def print_model_input(self, model_request):
        if not self.enabled:
            return
        print()
        print("[MODEL INPUT]", flush=True)
        print(json_lib.dumps(model_request, indent=2), flush=True)

    def print_model_output(self, model_response):
        if not self.enabled:
            return
        print()
        print("[MODEL OUTPUT]", flush=True)
        print(json_lib.dumps(model_response, indent=2), flush=True)

    def print_tool_input(self, tool_name, tool_args):
        if not self.enabled:
            return
        print()
        print("[TOOL INPUT]", tool_name, flush=True)
        try:
            arguments = json_lib.loads(tool_args)
        except (json_lib.JSONDecodeError, TypeError):
            arguments = tool_args
        print(json_lib.dumps(arguments, indent=2), flush=True)

    def print_tool_output(self, tool_name, output):
        if not self.enabled:
            return
        print()
        print("[TOOL OUTPUT]", tool_name, flush=True)
        print(json_lib.dumps(output, indent=2), flush=True)


out = ConsoleOutput()
