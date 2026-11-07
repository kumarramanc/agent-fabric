# Agent Fabric

Read the [two-page solution vision and framework appendix](docs/agent-fabric-vision.html)
for the proposed ontology and Agent Meta Store architecture.

Start with **`main.py`** to run the application and **`agents/customer_support/`**
to configure its behavior. The model/tool loop runs quietly behind the scenes.

## Project map

```text
main.py                         Start here: run the application
requirements.txt                Python dependencies

agents/                         Agent configuration and instructions
  customer_support/
    agent.json                  Goal, model, enabled tools, and bindings
    system.md                   Agent behavior
    skills/refunds.md           Refund-handling procedure
  writing_assistant/            Optional example agent

agent_runtime/                  Python implementation
  application.py                Connect configuration, plugins, and client
  cli.py                        Command-line and interactive input
  plugins.py                    Register available tools and hooks
  tracing.py                    Optional debug output
  core/                         Generic configuration and execution loop
  tools/                        Ticketing tool implementations and hooks

examples/                       Source-only learning material
  request.json                  Explicit demo request and data bindings
  data/                        One dataset: orders and versioned policies
  validate_data.py              Check that the demo data is present
  check_connection.py           Optional API hello test
  helpers.py                    Learning viewers and copy helper
  legacy_agent.py               Earlier lesson's compatibility wrapper

tests/                          Local tests; no paid API calls
scripts/build_runtime.py        Create the deployable archive
```

Generated caches, virtual environments, and `dist/` are hidden in the VS Code
Explorer. Their files still exist; environment activation paths have not changed.

## Run

Create the local environment once, then activate it:

```bash
python3 -m venv --prompt agent-fabric .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --agent customer_support
```

An agent ID is mandatory: supply `--agent <id>` or an `agent_id` in the request
file. Running `python main.py` alone stops before loading an agent or contacting
the model. The VS Code terminal launch asks you to enter the agent ID.

The deployed customer-support agent requires externally supplied data locations
and a business date. It never defaults to the sample data. See the deployment
configuration below.

For the opt-in local learning example:

```bash
python main.py --request examples/request.json
```

That request explicitly selects the demo data and read-only tools. It does not
process refunds. See [examples/README.md](examples/README.md) for other local checks.

Normal output contains only the conversation. Add `--debug` for full payloads.
Available options include `--agent`, `--query`, `--model`, `--goal`, `--request`, and
`--overrides`. Run `python main.py --help` to inspect them.

## Watch the code execute in VS Code

Select **Run and Debug → Agent Fabric walkthrough (read-only)** and press **F5**.
Execution pauses at startup. This configuration supplies the example request and
asks about order 1002; refund execution is not enabled. Continuing the run sends
real OpenAI requests.

- **F10 / Step Over:** execute the current line and stay in this function.
- **F11 / Step Into:** follow a call into our next function.
- **Shift+F11 / Step Out:** finish the function and return to its caller.
- **F5 / Continue:** run to the next breakpoint or the end.

Click the gutter beside a line number to add a breakpoint. Useful checkpoints:

| File / function | Inspect | Purpose |
| --- | --- | --- |
| `agent_runtime/cli.py`, `main()` before `service.run(request)` | `query`, `request` | Assemble the caller's input |
| `agent_runtime/core/store.py`, `load()` before returning | `metadata` | Resolve prompt, skills, overrides, and data locations |
| `agent_runtime/core/service.py`, `run()` before `self.runner.run(...)` | `definition`, `tools`, `session.conversation` | Assemble the agent for this invocation |
| `agent_runtime/core/runner.py` before `responses.create(...)` | `request` | See exactly what goes to the model |
| `agent_runtime/core/runner.py`, `execute_tool()` | `name`, `arguments`, `output` | Watch a requested tool execute |
| `agent_runtime/tools/policy_hooks.py`, `__call__()` | `output`, `selected_policies` | Watch policy-version pruning |
| `agent_runtime/cli.py` before `print(result.response)` | `result` | See the final framework output |

The **Call Stack** panel shows which function called the current one. Hover over a
variable or expand **Variables** to inspect its value without printing payloads.

## Deployment configuration

Keep private settings in environment variables or a local `.env`:

```dotenv
OPENAI_API_KEY=your-private-key
AGENT_RUNTIME_CONFIG=/etc/agent/runtime.json
```

The external JSON file is keyed by agent ID:

```json
{
  "customer_support": {
    "data_sources": {
      "orders_path": "/srv/ticketing/orders.json",
      "policies_dir": "/srv/ticketing/policies"
    },
    "context": {"current_date": "YYYY-MM-DD"}
  }
}
```

Replace these values with actual deployment paths and the appropriate business
date. A caller or metadata adapter should supply the date for each invocation.
Relative deployment paths resolve beside that external file; catalog paths resolve
from the project root.

Precedence: agent defaults → deployment settings → request overrides. Dictionaries
merge; lists and scalar values replace existing ones. Missing bindings fail before
calling the model. The application never copies or resets business data at startup.

## Call from another application

```python
from datetime import date
from agent_runtime.application import create_service
from agent_runtime.core.config import AgentRequest, AgentSession

service = create_service()
session = AgentSession(agent_id="customer_support")
result = service.run(
    AgentRequest(
        agent_id="customer_support",
        query="What is the status of my order?",
        overrides={"context": {"current_date": date.today().isoformat()}}
    ),
    session=session
)
print(result.response)
```

The other bindings come from deployment settings. Overrides can also supply the
model, goal, prompt, skills, tools, data sources, business facts, and model settings.
Use inline `system_prompt`/`skills` for externally supplied text, or
`system_prompt_file`/`skill_files` for local resources. Tools can reference bindings
with `${orders_path}` or `${current_date}`.

Reuse a session for follow-up messages with the same agent and configuration.
Start a new session when either changes. Sessions currently live in memory.

## Future metadata store

Implement `load(agent_id, overrides=None)` returning a validated `AgentDefinition`
and pass your adapter to `create_service(store=your_store)`. Plugin registration
lives in `agent_runtime/plugins.py`; the generic runner has no ticketing branches.

Configuration is trusted application input, separate from customer chat. It can
select only registered plugins. Your application must authorize tools and resource
access for each caller. The current client supports the OpenAI Responses API;
other providers need an adapter. Skills here are explicitly loaded Markdown text.

The included refund plugin updates a JSON record; it does not execute payments.
The policy hook selects versions using effective-date headers in the documents.

## Build and test

```bash
python -m unittest discover -s tests -v
python scripts/build_runtime.py
```

The build creates `dist/agent-fabric.zip`. It contains the launcher, runtime code,
customer-support agent assets, requirements, and documentation. It excludes
examples, sample data, tests, virtual environments, private `.env` files, and the
optional writing agent.
