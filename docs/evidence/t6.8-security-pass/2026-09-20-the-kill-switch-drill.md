# The kill-switch drill, and the audit-log review — 2026-09-20

**The deployment, `deploy@ubuntu`, 20:39–20:41 UTC. $0.** The two items
`docs/THREAT-MODEL.md` has carried as *not done* under T6.8 since the security pass closed:
*"audit-log review and a kill-switch drill are not done — the switch is documented (README §3.11)
and has been thrown once (T6.3), which is not a drill."*

**A drill is following the documentation cold and recording what happens, including what the
documentation gets wrong.** That is the whole difference from the T6.3 throw, which established
that the switch works. This establishes whether an operator can *use* it from the page that
describes it, and the answer is no — the section's only verification step cannot work, and it
fails in the one way that matters.

## What was run, and what happened

| # | step | result |
|---|---|---|
| 1 | `curl -s --max-time 5 localhost:8100/healthz` — before anything | **exit 7**, no output |
| 2 | §3.11's `sed`, then `docker compose up -d executor` | executor recreated, postgres healthy, 1.3 s |
| 3 | **§3.11's confirmation, verbatim** — `curl -s localhost:8100/healthz` | **exit 7, no output** |
| 4 | the same check through the compose network | **`{"status":"ok","kill_switch":true}`** |
| 5 | `git status --short` — the divergence §3.11 promises | **`M compose.yml`** |
| 6 | a token presented while the switch is on | **`outcome: kill_switch`**, audit `e75bf48f` |
| 7 | the `sed` in reverse, `up -d executor` | `{"status":"ok","kill_switch":false}` |
| 8 | **the same token with the switch off** | **`outcome: refused`** — *"token refused: token is not in the form `<payload>.<signature>`"*, audit `e7eaa143` |
| 9 | `git status --short` again | clean |

**Steps 6 and 8 are the drill's proof and were designed as a pair.** The executor checks the switch
**before** it verifies anything (`executor/core.py`), so a deliberately invalid token produces a
genuine `kill_switch` row without needing a real approval — and the same invalid token with the
switch off produces the ordinary token refusal instead. **The refusal at step 6 was the switch and
not the token**, and step 8 is what establishes that rather than asserting it. Both rows carry
`caller: chandana (kill-switch drill)`, so the ledger says what they are.

**Nothing was executed, no world state changed, and the tree came back clean.** The switch was on
for roughly seven seconds.

## The defect, and it is in the section an operator reads in an emergency

**§3.11 told the operator to confirm the switch with `curl -s localhost:8100/healthz` from the VM's
shell. The executor publishes no host port.** That command answers nothing, with exit 7 — **and
answers it identically whether the switch is on or off** (steps 1 and 3). The section's single
verification step could not distinguish the state it existed to verify, and its own next sentence
was *"`kill_switch: true` in that reply is the confirmation; nothing else needs checking."* There
is no reply.

**The document already knew.** Three other places have it right:

- **§3.6**, 360 lines earlier: `docker compose exec executor curl -fsS localhost:8100/healthz`.
- **§4**: *"it has no published port, Caddy forwards nothing to it."*
- **§3.6 again**, for the platform: `docker compose exec faultline curl -fsS localhost:8000/healthz`
  **`# not from the host: 8000 is not published`** — the principle, written out, beside a command
  that honours it.

And `tests/test_deploy.py::test_only_caddy_publishes_a_port` has asserted the executor's lack of a
port since T6.2. **So the README contradicted a tested property of the file next to it, in its
emergency procedure, for nine days**, and the throw of 2026-09-11 did not catch it because that
throw was not made from the documentation.

**A second, smaller one in the same breath.** §3.6's line carried the comment
`# {"status":"ok","kill_switch":true}` — but the committed configuration is
`FAULTLINE_EXECUTOR_KILL_SWITCH: "0"`, so a healthy deployment answers **`false`**. An operator
running the routine check as documented would have read a correct system as a wrong one. Corrected
to `false`.

**Both fixed, and the first is now guarded**:
`test_the_readme_never_reaches_an_unpublished_port_from_the_host` reads the README's fenced blocks
and fails on any command reaching 8000 or 8100 without `docker compose exec`. It was run against
the old text first and fails on it. §1a's `localhost:8001` is outside the rule on purpose — that
section rehearses a different, deliberately published shape on a development machine.

## The audit-log review

`action_audit` on the deployment, in full — **six rows, four callers, nine days**:

| at (UTC) | outcome | caller | action | target | exit | reason |
|---|---|---|---|---|---|---|
| 2026-09-11 22:07:35 | `kill_switch` | owner, prediction 9 | | | | the switch, on the VM's first day with an executor (T6.2) |
| 2026-09-18 12:15:18 | `approved` | faultline | `restart_service` | cartservice | | expires 12:30:18 |
| 2026-09-18 12:15:20 | **`executed`** | faultline | `restart_service` | cartservice | **0** | |
| 2026-09-18 12:34:39 | `refused` | probe | | | | token not in the form `<payload>.<signature>` |
| 2026-09-20 20:40:13 | `kill_switch` | chandana (kill-switch drill) | | | | this drill, step 6 |
| 2026-09-20 20:40:20 | `refused` | chandana (kill-switch drill) | | | | this drill, step 8 |

**Four of the five outcomes have occurred. `error` never has** — the executor has never tried to
act and failed. One action has touched this world in the deployment's life, and it exited 0.

**The inverse clause, satisfied in the only way this sample could satisfy it.** The plan asks that
*"every executed action records its inverse where one exists."* The one executed row carries
`inverse: no inverse: a restart discards process state and nothing restores it` — the words, not a
null, exactly as `executor/audit.py` documents. So the clause holds 1 / 1 **and the sample has
never exercised the case where an inverse does exist**: no `config_revert` or `rollback_image` has
been approved on this deployment, and those are the actions whose inverse is a real command. The
review can say the field is filled honestly; it cannot say the inverse has ever been usable.

**What this ledger cannot answer, and it is worth knowing before someone asks it to.** The
outcomes are five attempts *to act*. **An operator rejecting a proposal leaves no row here** — the
T6.6 note records that the 2026-09-18 execution came *after* an operator rejection, and that
rejection is in the incident state machine, not in this table. *"Was this proposal rejected before
it was approved?"* is not an audit-log question on this deployment. Similarly `token_id` is null on
all four non-executing rows, because three of them never reached verification and one had no
parseable token: the token index answers *"has this token been spent"* only for rows that got far
enough to have an id.

**What it does establish.** Every attempt to act on this deployment is on one append-only table —
enforced by a trigger, not by convention (`migrations/versions/0005_action_audit.py`) — with who,
when, what, against what, the exit code, a hash of the output, and the reason for every refusal.
Six rows in nine days is the action plane being approval-gated and the deployment being quiet,
which is what both were meant to be. **Nothing in the ledger is unexplained**, which is the
property a review of an audit log is for.

## What this closes, and what it does not

**Closed**: T6.8's *kill-switch drill* and *audit-log review*, both now done rather than
documented. **Not closed**: an execution on this deployment that recovers the system (G6 clause 1
— the one execution restarted cartservice and the note says outright *"Not shown: an action that
fixed anything"*), and an inverse that has ever been exercisable. Neither is a security question
and neither belongs to T6.8; both are G6's, where they are already recorded.
