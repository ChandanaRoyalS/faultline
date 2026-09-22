# The mount that detached — 2026-09-22, and the 45 minutes it cost

**\$0, no model call.** A merged change to `compose/prometheus/alert-rules-v2.yml` did not reach the
running Prometheus, `POST /-/reload` reported a failure whose text named no cause, and a 45-minute
quiet baseline was then taken against rules that had been frozen for two hours. **The capture looks
like a result and is not one.** It is recorded here and marked invalid in the baseline note rather
than discarded.

## What was observed, in order

| time (UTC) | event |
|---|---|
| 04:18:22 | Prometheus loads its config successfully. `rules=6.155209ms`. **These are the pre-widening `[2m]` rules.** |
| ~05:58 | PR #438 merges: the rate windows widen `[2m]` → `[5m]`. `git am` rewrites `alert-rules-v2.yml` on the host. |
| 06:03:42 | `make world-v2-up` reports every container **Running**. Prometheus is **not recreated**. |
| 06:03:42 | `POST /-/reload` returns `failed to reload config: one or more errors occurred while applying the new configuration`. |
| 06:03:42 | `/api/v1/rules` still reports `2m / 2m / 3m`. |
| 06:04:14 | The 45-minute baseline starts anyway (`evals/baselines/20260922T060414Z/`). |

## The cause, in Prometheus's own words

The `/-/reload` response carries no reason. The container log does:

```
level=ERROR source=manager.go:241 msg="loading groups failed" component="rule manager"
  err="/etc/prometheus/alert-rules.yml: open /etc/prometheus/alert-rules.yml: no such file or directory"
level=ERROR source=main.go:1538 msg="Failed to apply configuration"
  err="error loading rules, previous rule set restored"
```

And directly:

```
$ docker exec prometheus md5sum /etc/prometheus/alert-rules.yml
md5sum: can't open '/etc/prometheus/alert-rules.yml': No such file or directory
$ md5 -q compose/prometheus/alert-rules-v2.yml
9fae77fc993886ecf9f66b6a85eda87f
```

**The file was not stale inside the container. It was gone.**

**A single-file bind mount binds the host inode, not the path.** `git am` and `git checkout` do not
edit a file in place — they write a new file and rename it over the old one. The instant the merge
landed, the container's mount referred to an inode the host directory no longer named, and the path
inside the container became `ENOENT`. The host file was perfectly fine the entire time, which is
why every check run on the host agreed that nothing was wrong.

## Why four independent signals all said the world was healthy

**This is the part worth keeping.** The defect was not hidden behind a missing check; it was visible
to none of the checks that existed.

- **`make world-v2-up` reported `Running` and recreated nothing.** Correctly: no compose *path*
  changed, only the content behind one, and Compose compares the spec.
- **`make check` passed.** `tests/test_world_v2.py` parsed the rule file's YAML and asserted every
  window read `5m`. It did — **on the host**, which was never the question.
- **`promtool check config` reported `SUCCESS: 1 rule files found`** for
  `prometheus-config-v2.yaml` while the rule file it named could not be opened. Run from a host, it
  resolves a *container* path against the host filesystem. Both readings are true and neither is
  the relevant one.
- **`/api/v1/rules` answered.** With three rules, correctly formatted, on the old windows.
  **Prometheus's documented behaviour on a failed rule load is to keep the previous rule set**, so
  the API's answer was accurate and misleading at once.

**Nothing failed loudly. The world kept alerting on a rule set that had silently stopped changing.**

## What it cost, and what would have been worse

Two hours and one 45-minute quiet baseline that cannot be cited. The capture fired
`ServiceHighLatency/accounting` continuously for all 45 minutes, which was read at the time as the
widening having failed to help — **it was the `[2m]` rules doing exactly what the previous baseline
said they would.**

**The expensive version of this was available and was not reached.** Had the reload returned success
— which it would have, on a Docker implementation that serves stale content through a detached mount
rather than `ENOENT` — the baseline would have been accepted, the thresholds ratified against it,
thirty scenarios authored on top, and the error found weeks later with a corpus to re-record. The
reload failing loudly is the only reason this cost one afternoon.

## The fix

**`compose/prometheus/` is mounted as a directory**, at `/etc/faultline`, for both `prometheus` and
`alertmanager` (`compose/telemetry-v2.yml`). A directory mount resolves the name on every lookup, so
a file replaced by rename is seen. `/-/reload` now does what three years of Prometheus documentation
says it does.

**The target is `/etc/faultline` and not `/etc/prometheus`** because mounting over `/etc/prometheus`
would hide the image's own `consoles/` and `console_libraries/`, which two flags in the same
`command:` still point at. A guard pins that
(`test_the_v2_prometheus_does_not_mount_over_its_own_image_directories`), because replacing one
silent breakage with another is not a fix. A side benefit: the rule file keeps its repository name
inside the container, so `alert-rules-v2.yml` can no longer be mistaken for v1's `alert-rules.yml`
by anyone reading a shell.

**Two guards, and they do different jobs.** `test_the_reloadable_services_mount_a_directory_not_a_file`
is the one that catches this bug, by removing the shape that permits it — it was checked against the
exact pre-fix compose file and fails on it.
`test_every_config_path_named_inside_the_v2_containers_is_a_file_we_ship` **would not have caught
this bug** and is not claimed to: it protects the fix, because the rule file's location is now
spelled in two places (`--config.file` and `rule_files`) and both are container paths that no tool
in `make check` can resolve.

## What the fix does not cover, stated rather than left to be discovered

**Every other config in this repository is still mounted as a single file**, in both worlds:
`promtail-config.yml`, `tempo.yaml`, the two Grafana datasource files, `otelcol-extras-v2.yml`, and
all of v1's `telemetry.yml`. They were left alone deliberately and the reasoning is:

- **None of them is reloaded.** They are read at startup, so a detached mount does not silently
  freeze a live config the way Prometheus's did.
- **Their failure mode is different and quieter**: edit one, run `make world-v2-up`, and Compose
  recreates nothing because no spec changed — so the edit simply does not take effect, with no
  error. That is a real trap and it is **unfixed**. It has not yet cost anything measurable, and
  fixing it by mounting `compose/` wholesale into five containers would be worse than the disease.
- **v1 is frozen on purpose.** Every published figure was measured on that world; changing how its
  containers receive configuration is not a change to make for tidiness while it is still the
  reference.

**The remaining open question is whether `docker compose up -d` should force-recreate the
config-carrying services**, which would close the second bullet at the cost of a restart on every
bring-up. Not decided here, and not decided by argument — it wants a measurement of what a restart
costs this world.

## What happens next

The baseline is re-run, and **this time the rules are verified live before the clock starts**:
`/api/v1/rules` must report `5m` on all three and `md5sum` inside the container must match the host.

**One artefact of the recreate is known in advance and will be stated in the capture rather than
discovered in it.** A freshly recreated Prometheus has no history, so `ServiceNoTraffic`'s
`[30m] offset 10m` lookback is empty for the first forty minutes and its second clause (`> 0`)
cannot be satisfied. **That silences the rule rather than making it fire**, so it does not
contaminate a false-positive test — but it does mean a baseline started immediately after a recreate
does not test `ServiceNoTraffic` at all. The re-run therefore waits forty minutes after the recreate
before the window opens.
