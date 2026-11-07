# Optional learning examples

Run these commands from the project root, with your Python environment active.
These files and datasets are excluded from the runtime build.

## One demo dataset

```text
data/
  customer_orders.json   The only order file; refunds update this file
  policies/              Policy documents, including version subfolders
```

There is no original/working split and no automatic copying or reset. Existing
refund records are preserved across runs. To verify that the data is present:

```bash
python examples/validate_data.py
```

## Customer-support demo

```bash
python main.py --request examples/request.json
```

The request explicitly supplies the practice date and paths under `examples/data/`.
It enables only policy search and order lookup. The local `runtime.local.json`,
when configured, can bind the same dataset for an interactive session:

```bash
python main.py --agent customer_support
```

Local deployment settings are ignored by Git and excluded from the runtime build.

## API hello test

```bash
python examples/check_connection.py
```

Add `--debug` for payloads. This sends one real API request.

## Another agent

```bash
python main.py --agent writing_assistant --query "Rewrite clearly: We are in receipt of your message."
```

This agent has no tools and uses the same generic runner. `helpers.py` contains
the earlier viewers, and `legacy_agent.py` preserves the older lesson's calling
interface. New integrations use `agent_runtime.application.create_service()` and
`AgentRequest`.
