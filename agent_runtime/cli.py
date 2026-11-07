"""Command-line entry point for any configured agent."""

import argparse
import json
from pathlib import Path

import openai
from pydantic import ValidationError

from agent_runtime.application import create_service
from agent_runtime.core.config import AgentRequest, AgentSession


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agent Fabric: run a configured agent.")
    parser.add_argument("--agent", help="Agent ID from the agents catalog")
    parser.add_argument("--query", help="Run one query and exit")
    parser.add_argument("--model", help="Override the configured model")
    parser.add_argument("--goal", help="Override the configured goal")
    parser.add_argument("--request", help="JSON file containing agent_id, query, and overrides")
    parser.add_argument("--overrides", help="JSON file containing configuration overrides")
    parser.add_argument("--debug", action="store_true", help="Show full model/tool traces")
    args = parser.parse_args(argv)

    try:
        payload = {}
        if args.request:
            payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
            # Validate request files, including unknown fields, before execution.
            payload = AgentRequest.model_validate(payload).model_dump()
        agent_id = args.agent if args.agent is not None else payload.get("agent_id")
        if agent_id is None or not agent_id.strip():
            print("Agent ID is required. Use --agent <id> or a request file containing agent_id.")
            return 1
        query = args.query if args.query is not None else payload.get("query")
        overrides = dict(payload.get("overrides", {}))
        if args.overrides:
            overrides.update(json.loads(Path(args.overrides).read_text(encoding="utf-8")))
        if args.model:
            overrides["model"] = args.model
        if args.goal:
            overrides["goal"] = args.goal
        debug = args.debug or payload.get("debug", False)

        service = create_service()
        # Fail early on missing configuration, files, or plugin bindings.
        definition = service.store.load(agent_id, overrides)
        service.registry.build_tools(definition)

        if query is not None:
            request = AgentRequest(agent_id=agent_id, query=query, overrides=overrides, debug=debug)
            result = service.run(request)
            print(result.response)
            return 0 if result.status == "completed" else 1

        # The session belongs to this caller, not a shared global conversation.
        session = AgentSession(agent_id=agent_id)
        while True:
            try:
                query = input("Customer (type quit to exit): ").strip()
            except EOFError:
                print("No terminal input is available. Run python main.py in an interactive terminal.")
                return 1
            except KeyboardInterrupt:
                print()
                return 0
            if query.lower() == "quit":
                return 0
            if not query:
                continue
            request = AgentRequest(agent_id=agent_id, query=query, overrides=overrides, debug=debug)
            result = service.run(request, session=session)
            print("Agent:", result.response)
    except ValidationError as error:
        print("Invalid configuration:", json.dumps(error.errors(include_input=False, include_url=False)))
        return 1
    except (OSError, ValueError, TypeError) as error:
        print("Configuration error:", str(error))
        return 1
    except openai.OpenAIError:
        print("OpenAI client could not start. Check OPENAI_API_KEY in your local environment.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
