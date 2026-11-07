"""Send a hello message with the model configured for the selected agent."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openai

from agent_runtime.application import create_service
from agent_runtime.tracing import ConsoleOutput


def test_connection(agent_id="customer_support", debug=False):
    service = create_service()
    definition = service.store.load(agent_id)
    request = {
        "model": definition.model,
        "input": "Hello! Please reply with one short greeting.",
        "max_output_tokens": 100,
        "store": False
    }
    if definition.model_settings.reasoning_effort is not None:
        request["reasoning"] = {"effort": definition.model_settings.reasoning_effort}
    trace = ConsoleOutput(enabled=debug)
    trace.print_model_input(request)
    try:
        response = service.runner.client.with_options(timeout=30, max_retries=0).responses.create(**request)
    except openai.APIError as error:
        print("Connection test failed:", getattr(error, "code", None) or type(error).__name__)
        return 1
    trace.print_model_output(response.model_dump(mode="json", by_alias=True, exclude_none=True))
    print(response.output_text)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default="customer_support")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    raise SystemExit(test_connection(args.agent, args.debug))
