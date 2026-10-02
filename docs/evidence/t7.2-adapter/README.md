# T7.2 - the adapter build

Registered in [`PREREGISTRATION-T7.2-adapter.md`](../../../evals/runs/PREREGISTRATION-T7.2-adapter.md).

## Stage 0 - can Faultline run in SREGym's agent container?

Written before the stage is run. No cluster is started, no model is called, and nothing on the
world is changed.

| file | what it is |
|---|---|
| `spike_vm.sh.txt` | the stages run on the deployment, one at a time from the Mac: `preread`, `install`, `host-on`, `pg-up`, `box`, `pg-down`, `host-off`, `cleanup`, `postread` |
| `spike_box.py.txt` | run with SREGym's own venv: starts SREGym's `ContainerRunner` with the run's settings (filtered, hardened, no host credential) and runs `spike_inside.sh` in the container |
| `spike_inside.sh.txt` | the six checks inside the container, A to F, one line each |
| `spike_tunnel.py.txt` | a loopback port that reaches a host port through the egress proxy by CONNECT, for psycopg; tested against a local fake proxy before registration |

The outputs are added here as each stage is run, as `t72-spike-<stage>.txt`, with the VM's address
withheld.
