"""The pre-flight model check (Q20).

Dev sweep 8 **injected `product-catalog-flag-failure` four times and discarded all four** when the
API answered `invalid_request_error: credit balance too low` at the triage call. Each attempt
injected the fault, failed, reverted, confirmed recovery and wrote a `DISCARDED.md`. Two more
scenarios never started for the same reason. Sixteen non-scored outcomes against six scored, and
the cause was not the pipeline.

The harness already establishes this principle in the other direction: **the baseline gate refuses
before touching the world when the world is not quiet.** The model's reachability was not checked
at all, so a run would break the world first and discover it could not investigate second.

## One token on the configured model, not a models-list call

The queue row settled this and the reasoning is worth keeping: **a one-token completion proves
reachability *and* balance**, where listing models proves only that the key is valid. The failure
that cost sweep 8 three scenarios was a *balance* failure on a perfectly valid key, and a check
that would have passed it is not a check.

The cost is one token. Against a run that costs about \\$0.70 and roughly four minutes of world
time, that is not a trade worth thinking about twice.

## Where it goes, and why not later

**Before the baseline gate**, which is before the freeze, which is before injection. The gate can
wait out a 300-second settle window, and discovering an unreachable model *after* that wait would
throw the wait away as well as the run. Cheapest check first.

## What a failure is, and what it is not

**A refusal, not a discard.** Nothing is injected, the world is untouched, and the scenario has
not been attempted - so it must not be counted as a run that produced no result. ADR-0022 §3.3
keeps the discard number honest precisely so it means something, and a run that never started is
not a run that failed. Exit 3, the same code the gate's own refusals use.

## What this cannot catch

A balance that runs out **mid-run**. One token proves the account could be billed a moment ago,
not that it can be billed eleven model calls from now, and a sweep that starts with barely enough
credit will still discard somewhere in the middle. This narrows the window from "the whole run"
to "after the first call"; it does not close it. Stated because the next person to see a
credit-balance discard should not conclude this check is broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROBE_TOKENS = 1
"""The completion is capped at one token. **The answer is discarded** - what is being tested is
whether the call is *possible*, not what the model says."""

PROBE_PROMPT = "ok"
"""Deliberately content-free. A probe that asked something real would tempt a future reader to
use the answer, and this call's answer is meaningless by design."""


class PreflightError(RuntimeError):
    """The configured model could not be reached or billed. **Nothing has been injected.**"""

    discard_reason = "model unreachable"
    """Carried for shape-compatibility with the harness's other refusals. It is never used to
    record a discard - this refusal happens before anything is injected, so there is nothing to
    discard - but a refusal type that could not say why would be the odd one out."""


@dataclass(frozen=True, slots=True)
class Preflight:
    """What the check found, recorded on the manifest whether it passed or not."""

    checked: bool
    model: str = ""
    ok: bool = False
    detail: str = ""
    skipped_because: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "model": self.model,
            "ok": self.ok,
            "detail": self.detail,
            "skipped_because": self.skipped_because,
        }


def probe(model: Any, model_name: str) -> Preflight:
    """One capped completion. Returns rather than raises, so the caller decides what a failure is.

    Every exception is caught, including ones this module has never seen. A pre-flight check that
    itself raises an unexpected error would abort the run in a path with no manifest and no
    recorded reason - strictly worse than the problem it exists to prevent.
    """
    from faultline.agents.model import ModelRequest

    try:
        response = model.complete(
            ModelRequest(
                system="Reply with the single word ok.",
                messages=[{"role": "user", "content": PROBE_PROMPT}],
                role="preflight",
                max_tokens=PROBE_TOKENS,
                effort="low",
            )
        )
    except Exception as failure:
        return Preflight(checked=True, model=model_name, ok=False, detail=str(failure))
    return Preflight(
        checked=True,
        model=model_name,
        ok=True,
        detail=f"{response.input_tokens + response.output_tokens} token(s) billed",
    )


def require(baseline: str | None, model_name: str, build: Any) -> Preflight:
    """Check the model, or record why the check does not apply.

    `build` is a zero-argument callable returning a `LanguageModel`, so a run that skips the check
    never constructs a client - which matters for B0, whose whole claim is that it makes no model
    call and costs \\$0.00. Constructing one just to skip it would put a connection in the latency
    of a baseline that has none.

    Raises `PreflightError` when the check runs and fails. **Nothing has been injected at that
    point**, which is the entire purpose.
    """
    if baseline == "b0":
        # B0 makes no model call at all. Refusing it for an unreachable model would refuse a run
        # that cannot be affected by one.
        return Preflight(checked=False, skipped_because="b0 makes no model call")

    result = probe(build(), model_name)
    if not result.ok:
        raise PreflightError(
            f"the configured model ({model_name}) could not be reached or billed.\n"
            f"  {result.detail}\n"
            "Nothing was injected and the world is untouched. This is not a discard - the run\n"
            "never started, and counting it as one would inflate a number kept honest on purpose.\n"
            "Dev sweep 8 injected the same scenario four times before discovering this at the\n"
            "triage call; the check that would have caught it costs one token (Q20)."
        )
    return result
