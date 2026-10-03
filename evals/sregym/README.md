# Faultline's agent row for SREGym (T7.2)

`faultline-agent.patch` is the whole change Faultline makes to SREGym's tree, against
`46c853db3a79332ea1c0ada076d888cec7a02f7e` (adapter registration §1,
[`PREREGISTRATION-T7.2-adapter.md`](../runs/PREREGISTRATION-T7.2-adapter.md)). It is kept here
rather than under `deploy/`: benchmark infrastructure is not product infrastructure (ADR-0004).

| file in SREGym's tree | what it is |
|---|---|
| `agents.yaml` | a `faultline` row: containerised (the default), `install-faultline.sh`, and the driver below. Its one `kickoff_env` value, the benchmark database's password, is a placeholder that is set for the run on the deployment and never committed |
| `docker/agents/install-scripts/install-faultline.sh` | fetches Faultline's **source bundle** (`faultline.sregym.bundle`) from the host through SREGym's egress proxy, extracts it to `/opt/faultline` and installs it editable with `[agents,embeddings]` and CPU torch. Changed from a wheel by the adapter's Addendum 3: a wheel carries no repository data, so no graph would load |
| `clients/faultline/driver.py` | three lines: `faultline.sregym.driver.main`. All the logic is in this repository, under its tests |

Apply it to a checkout at the pin with `git apply`, then build SREGym's agent image locally
(`--force-build`). **Both arms of the run use that one image**, so the baseline runs on exactly
the image Faultline does.

**Not in the patch, by registration**: `claudecode`'s `agent_version`, which is pinned to the
version the dev pilot installs, recorded with the pilot.
