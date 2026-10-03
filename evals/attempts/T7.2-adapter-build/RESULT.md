# RESULT - T7.2 adapter build

Read against [`PREREGISTRATION-T7.2-adapter.md`](../../runs/PREREGISTRATION-T7.2-adapter.md), its
build section and Addendum 2. Built 2026-10-03, offline. No model was called and nothing was run
against SREGym. $0.

## What was built

- **`faultline.sregym`** (`src/faultline/sregym/`):
  - `mcp`: the MCP-over-SSE client;
  - `toolset`: `McpToolSet`;
  - `kube`: the change mapping and its leak guard;
  - `opening`: the alarms and the incident;
  - `render`: the frozen rendering;
  - `tunnel`: the CONNECT tunnel;
  - `profiles`: per application;
  - `driver`: one attempt, as `faultline-sregym`.
- **Two existing files**: `ToolSettings.backend` and `faultline-investigate`'s `_tool_set`
  (Addendum 2, item 1).
- **SREGym's side**, as a patch against `46c853db`
  ([`evals/sregym/faultline-agent.patch`](../../sregym/faultline-agent.patch)): the `faultline`
  row in `agents.yaml`, `install-faultline.sh` and a three-line driver. Checked with
  `git apply --check` at the pin.
- **[ADR-0044](../../../docs/adr/0044-faultline-under-sregym.md)**, the design.
- **`tests/test_sregym.py`**: 35 tests covering each piece registered in §5.

## The predictions

| prediction | held? |
|---|---|
| both stamps unchanged | **held**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, computed after the build |
| `make check` passes with the new tests and nothing else changed | **held, with three guards met on the way**: 2,397 passed, the 2,362 before plus the 35 new. **The guards**: `test_subprocess_timeouts` refused the driver's unbounded `subprocess.run`, now bounded at 1,500 s; `test_readme_covers_the_commands` refused `faultline-sregym` until README named it; `test_docs_pack` refused ADR-0044 until `ARCHITECTURE.md`'s index listed it |
| the adapter's own code under 1,500 lines, tests excluded | **wrong**: 1,915 lines in `faultline.sregym`, plus 32 in the SREGym patch and 39 changed in existing files. About half of it is docstrings |

## Before the pilot

- **The dev read** (Addendum 2, item 9), which sets `PROFILE_READ`.
- **The pilot's registration**, which also carries the run's operation:
  - the benchmark database seeded at the run's commit;
  - the docker0-only firewall rules for 8000, 9954 and the database;
  - the wheel served to `install-faultline.sh`;
  - the database password, set outside the repository;
  - `claudecode`'s pinned version.
