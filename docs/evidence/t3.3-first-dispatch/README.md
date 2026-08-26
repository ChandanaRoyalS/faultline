# T3.3 — the first real dispatch: **blocked at stage 1, on credentials**

The two-stage split did its job. Stage 1 exists to isolate auth and plumbing from everything
else, and that is exactly where this stopped — before any world was touched, any fault injected,
or any token spent.

| | |
|---|---|
| stage 1, boundary | **FAILED** — `401 invalid x-api-key` |
| stage 2, first dispatch | **not attempted** — it depends on stage 1 |
| world | **not touched.** No injector run, nothing to revert |
| tokens spent | **0** |

## Files

- **`stage1-boundary.txt`** — the run, unedited, ending in the 401.

## What stage 1 established

Everything up to the API call worked:

```
model: claude-opus-5   effort: high   role_models: {}
api key: read from the environment by the SDK; not a setting, not printed
```

Settings loaded, the optional `faultline[agents]` extra installed, `AnthropicModel` constructed,
the request assembled and sent. The failure is at the credential and nowhere else:

```
anthropic.AuthenticationError: Error code: 401 - invalid x-api-key
```

That is the value of running the trivial prompt first. Had this been folded into stage 2, the
same 401 would have surfaced after a rehearsal was injected into the world, with a broken
world to revert and no way to tell an auth failure from a dispatch failure.

## Why: the key file does not contain a key

Checked structurally, without printing its contents:

| property | value |
|---|---|
| length | 125 characters, one line |
| prefix | **not** `sk-ant-…` |
| first word | `pbpaste` |
| shape | 15 whitespace-separated words |

`~/.faultline-anthropic-key` holds **a shell command line, not a credential** — the most likely
explanation is that a `pbpaste > ~/.faultline-anthropic-key` was typed and the command itself
was written to the file instead of the clipboard's contents.

No part of the file has been printed, logged, or committed, here or anywhere else. `AgentSettings`
has no key field by design (ADR-0020, T3.2), so nothing in this repo's configuration could have
carried it even if it had been valid.

## What is unaffected

The T3.3 code is complete and its hermetic tests pass — the planner, the four specialists, the
budget's four bounds, the trajectory wiring. `make check` is green, and the fake model exercises
every path that does not require a real completion. What has *not* been exercised is the one
thing stage 2 exists for: a real model reading a real envelope from a live world.

## To finish it

Put a valid key in the file (`sk-ant-…`), then re-run:

```bash
ANTHROPIC_API_KEY="$(cat ~/.faultline-anthropic-key)" uv run python <stage 1 script>
```

Stage 1 costs a few dozen tokens. Only when it passes is stage 2 worth starting, which is the
whole reason the two are separate.
