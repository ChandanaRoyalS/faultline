# T7.48 — the world was torn down and rebuilt, and it came back the same

**The single most important thing this project had never checked.** Every provenance claim assumes
the world can be rebuilt; it had run continuously for the benchmark's entire life.

**Result: identical on every provenance field.** [`BEFORE.json`](BEFORE.json) was written before
anything was touched; [`AFTER.json`](AFTER.json) is the comparison.

## The comparison

| field | before → after |
|---|---|
| `compose_digest` | `f5bd108f4f70f460…` → **identical** |
| `observability_digest` | `857d95b4d174ec43…` → **identical** |
| `ffs_stub_source_digest` | `8defed3104c42adf…` → **identical** |
| all **7** observability files, individually | **all identical** |
| `otel_demo_image_digest` | `sha256:97d55955…` → **identical** |
| `ffs_stub_image_id` | `sha256:e273759f…` → **identical** |
| `docker_arch`, `host_platform`, `otel_demo_image` | **identical** |
| containers | 28 → **28**, same names, **no image id changed** |

**So the recorded bundles describe a world that rebuilds.** Nothing in the provenance family moved,
which is what those digests exist to detect.

## One check a rebuild alone cannot make

A teardown-and-up reuses local images, so it cannot detect a **moved tag**. Checked separately and
non-destructively, before the teardown:

```
$ docker buildx imagetools inspect ghcr.io/open-telemetry/demo:v1.2.1-cartservice
Digest: sha256:97d55955ecfd51988a29d15d66a4d281c86af5b2b40ac94445a617d66f3f9994
```

**Identical to the local image and to what every bundle records. The tag has not moved**, so a
genuinely cold pull today would fetch the same image. That is the strongest available evidence for
reproducibility short of deleting the images, which was out of scope as destructive beyond the
running stack.

## A dirty clone that is not drift

`world/` reports dirty, with exactly two untracked paths: `.cloned` (the Makefile's marker) and an
**empty** `src/grafana/provisioning/datasources/loki.yml`. Both are documented in the Makefile as
expected (T7.16, ADR-0026) — the second is a Docker-materialised bind-mount target recreated on
every bring-up. **Checked before the teardown because it would have been the finding.**

## The documented path, run as written

| step | result |
|---|---|
| `make world-down` | 28 → 2 containers; only the Faultline platform survives (separate compose) |
| `make world-up` | 28 back in **12 seconds**; no pull, no build |

**Both worked exactly as README describes.** No missing step, no undocumented prerequisite hit.

## The settle, which is a test of T7.47's own correction

T7.47 changed README from *"~2 minutes"* to *"~5 minutes"* because the gate refuses containers
younger than 300s. **That correction is now validated by experience rather than by reading:**

| when | gate |
|---|---|
| +75s after `world-up` | **REFUSED** — *"26 container(s) have been up for less than 300s and are still settling"* |
| +6m | **PASSED** — 14 services, nothing unexpectedly silent, kafka 28.5% vs an 84.0% threshold |

**A stranger following the old README would have hit that refusal and had no way to read it.**

## Behaviour reproduces, not only digests

| | measured from cold | documented baseline |
|---|---|---|
| `cartservice` p95 | **1.9 ms** | *"flat 1.9ms — 181 consecutive samples"* (`alert-rules.yml`) |
| `checkoutservice` p95 | **38.1 ms** | ~37–38 ms |
| kafka at cold start | **25.5%** | ~26.27% after a restart (T7.30) |

**The world does not merely hash the same; it behaves the same.**

## The known pathologies, against the hazards page

**Neither appeared in the six minutes observed**, and both are consistent with what
[`docs/TROUBLESHOOTING.md`](../../TROUBLESHOOTING.md) says:

- **No checkout stall.** Consistent with T7.38 finding checkout healthy at 1h20m; the stall is a
  longer-horizon property, and its absence from a cold world is expected rather than surprising.
- **kafka growth from cold is visible and benign**: 25.76% → 28.40% over five minutes, tracking the
  documented emulation growth. A reader seeing that page would have recognised it and would not have
  needed to act — the hazards page's threshold framing (refuses near 90%) correctly implies that
  28% is nothing to do anything about.

**Whether a reader would have understood the settle refusal:** yes, and this is the strongest claim
this task can make about the documentation — the refusal message names the reason and the count, and
README now gives the number in advance.

## Where this stops, and what remains unverified

**Stopped at `make demo`**, which needs a model call and therefore money. Verified up to that line
and no further:

| verified without a model call | result |
|---|---|
| `make eval` bare | usage, exit 2 |
| `faultline-eval` without intent | refuses with the documented message (T7.33) |
| baseline gate, cold and settled | refuses then passes, as documented |
| kafka headroom projection | 25.5% vs 84.0%, fits |
| world lock | free, uncontended |
| demo preflight inputs | key present at `~/.faultline-anthropic-key`, `faultline-eval` on PATH |

**Unverified for want of credit:** the demo end to end, any scored run, and therefore whether a
rebuilt world produces comparable *figures* — this task shows it produces an identical *world*.

**Also still unverified, and unchanged from T7.46:** a genuinely cold path — deleting `world/`,
re-cloning, and re-pulling every image. The tag check above is the non-destructive substitute and it
is weaker: it proves the tag resolves the same today, not that a full cold pull assembles the same
28 containers.

## World state at the end

**Left healthy and running.** 28 containers, 14 services reporting, no alerts firing, gate passing,
kafka at 28.5%, no lock held, no active injections.
