# RESULT - T7.2 adapter fixes

Read against [`PREREGISTRATION-T7.2-adapter.md`](../../runs/PREREGISTRATION-T7.2-adapter.md),
Addendum 4. Built 2026-10-03, offline. No model was called and nothing was run against SREGym.
$0.

## What was built

| fix | where | what changed |
|---|---|---|
| **F1**, the selector | `toolset.pod_pattern` | written for the string literal it sits in: `.` escaped for Go and RE2, `-` as itself, a non-DNS-1123 name refused |
| **F2**, the change commands | `kube.Commands`, `kube.KubernetesChangeLog`, `McpToolSet.change_history` | six field-projected `kubectl get` templates replace the four `-o json` reads; Services, NetworkPolicies and claims by name and time; a cut answer marked truncated, a cut pod spec named |
| **F3**, the fifteen seconds | `mcp.McpSession.__exit__` | the socket is shut down before the close, and the close is never waited on |
| **F4**, the shop's p95 | `Profile.latency_readable`, `McpToolSet.unreadable` | Astronomy Shop's `latency-p95` reports *unavailable*, naming the 0.005 ms bound |

[ADR-0044](../../../docs/adr/0044-faultline-under-sregym.md) records the change mapping as
rewritten, and the two properties now reported as unavailable.

## The predictions

| prediction | held? |
|---|---|
| both stamps unchanged | **held**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, computed after the build |
| `make check` passes, the old tests unchanged in substance | **held, with four tests changed because they asserted the old behaviour**. <br>- `test_runtime_memory_reads_cadvisor_for_the_workload` asserted the escaped `nginx\-thrift`, the defect itself, and now asserts the unescaped form. <br>- The parity test for `metric_baseline`'s copied body moved from Astronomy Shop to Hotel Reservation, where `latency-p95` is still read. <br>- The command test and the change-log test were rewritten for the new commands. <br>- The three revision-diff tests read the new revision shape, with the same assertions |
| each new test fails against the code it replaces | **held**, each fix reverted alone: <br>- **F1**: four failures, including both hyphenated and dotted names; `rate`, with neither, passes either way; <br>- **F3**: the keep-alive test fails; <br>- **F4**: the latency test fails; <br>- **F2**: the old module has no `Commands`, so nothing in the file can run |

**The tests**: `tests/test_sregym.py` holds 46, up from 37.

- The selector is decoded by Go's escape rules (`json.loads` as the stand-in) and matched against
  Deployment and StatefulSet pod names, never a service sharing a prefix. The shipped spelling is
  shown to fail the decode.
- The keep-alive test runs a server that sends nothing after its replies. A call must finish in
  under 2 s, and a plain close is shown still blocked after 1 s.
- The change log runs against a fake kubectl answering per command:
  - every command it sends is one of the templates;
  - it covers a Deployment's diff, a StatefulSet's revisions, and a changed Service, NetworkPolicy
    and mounted claim, with another service's objects and an unmounted claim left out;
  - a cut index keeps its lines and is marked truncated;
  - a cut pod spec is named;
  - at most six pod specs are read, and the rest are named.
- **Checked against SREGym's own guard**: every command parses under `bashlex` as one plain
  command, which is what `kubectl_cmd_runner._check_kubectl_command` requires.

## Not yet established

These are for the re-check, Addendum 4's last section:

- **Whether every projected answer fits** on the live applications. The pilot measured a largest
  pod template of 14,077 characters as indented JSON. A jsonpath answer is compact, and its size is
  not yet measured.
- **That the jsonpath and custom-columns forms run** as written through SREGym's shell.
- **Each tool call's time**, now that a session no longer waits for a keep-alive.
- **Hotel Reservation's p95**, which F4 expects to be real.

## Next

The re-check: Faultline alone on the three dev problems, $2-3 within the run's cap. It passes only
on the conditions Addendum 4 registered.
