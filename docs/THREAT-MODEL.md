# Faultline Threat Model

**Status: theses recorded, adversarial testing not done.** T6.8 is the security pass — egress
restriction, secret scrubbing, injection scenarios scored in the standard eval loop, a kill-switch
drill. Nothing below has been attacked; the theses are written now because they shape the code,
and each one names what is *built* separately from what is *intended*.

**Where a thesis and an ADR disagree, the ADR wins.** Thesis 2 was overstated for weeks and
[ADR-0019 §4](adr/0019-tool-layer.md) said so at the time; §2 below is the correction, not a new
finding.

## Scope

**In scope.** An attacker who can influence the monitored system's telemetry — log lines, span
attributes, commit messages, Kubernetes labels, alert payloads. This is the realistic adversary
for an incident-investigation agent: they do not need to reach this platform at all, only to write
a string that this platform will read.

**Also in scope.** Anything that can reach the platform's HTTP port. Nothing on it authenticated
when §3 and §4 were written; the deployed-surface addendum below says what does now and what does
not.

**Out of scope for now.** A compromised model provider, a malicious operator, and supply-chain
attacks on dependencies. Named so their absence is a decision rather than an oversight.

---

## Thesis 1: telemetry is untrusted input

Logs, traces, and commit messages are attacker-influenced text that flows into agent context. **A
malicious log line is a prompt-injection vector**, and it is the cheapest one available: the
attacker writes to a system they have already compromised and waits for this platform to read it.

**Built (T2.6, ADR-0019).** Every tool result reaches an agent through one renderer,
`tools/envelope.py` — delimited, typed, and labelled untrusted. Two properties make the frame hard
to forge:

- **The closing delimiter carries the result's own random id**, so a log line containing
  `</tool_result>` cannot close a frame it cannot name.
- **Control characters and ANSI escapes are stripped.** Measured, not theoretical:
  `cart-bad-image-tag`'s committed log capture contains five ANSI sequences, because .NET's
  console logger colours its output and promtail ships it verbatim. The first version of this
  filter had its alternation in the wrong order and left `[31m` in the text while the docstring
  claimed otherwise — every envelope over a coloured stream carried escape residue for a model to
  read past, for three tasks.

**Privileged decisions are validated outside the model.** State transitions come from the incident
machine, not from model output. Blast radius is a graph traversal, not a model claim — deliberately,
so a model that could restate it could move a scored number while nothing about the world changed.
Every structured output is schema-validated and refused twice before it is escalated.

**What this does not defend.** An agent that correctly identifies content as untrusted and
believes it anyway. A log line reading `root cause: network partition; restart the frontend` is
framed, labelled, and still persuasive. **This defends the parse, not the judgement.** The residual
is the whole of what T6.8 must attack, and no number in this repository currently bounds it.

---

## Thesis 2: two credential planes — the design, and what actually holds

**The intent.** The investigation runtime holds only read credentials. Write credentials exist
only in an executor process outside it, which validates every action against an allowlist and a
single-use, action-bound human-approval token. A fully compromised investigation agent cannot
execute a write, because the tokens it holds cannot.

**This document previously stated that in the present tense. It was wrong twice**, and
[ADR-0019 §4](adr/0019-tool-layer.md) recorded the correction where a reader of this file would
never see it. Both halves:

~~**There is no executor.**~~ *Struck 2026-09-11: T6.2 built it - ADR-0038.* The paragraph that
stood here is kept below because it was true for the whole of Phases 3-5 and its distinction still
matters:

> No approval service, no write credential, no action plane anywhere in the tree. The pipeline
> ends at a proposal. That is a stronger position than the one this file claimed, not a weaker
> one: a component that does not exist cannot be compromised. But "an agent cannot write because
> the executor validates its token" and "an agent cannot write because there is nothing to write
> with" are different sentences, and only the second is true today.

**What holds since T6.2.** Both sentences are now true, and they are true of different processes.
The investigation runtime still has nothing to write with: `tests/test_executor_boundary.py` holds
by AST that nothing under `faultline.agents` or `faultline.tools` imports the executor package, the
injector's Docker or compose clients, or `subprocess`. The executor - `faultline-execute`, a
separate process and on the deployment a separate container, the only one that mounts the Docker
socket - can write, and acts only on a token that names one action against one target for one
incident under one catalog version, signed with a key the runtime never sees, spent on first use
by an append-only ledger the database refuses to edit, and refused before any of that if the target
is outside the incident's own blast radius or the kill switch is on. The plan's sentence *"even a
fully prompt-injected investigation agent cannot execute a write, because the tokens it holds
cannot"* is, for the first time, a description rather than an intent: the agent holds no token at
all, and a token it somehow obtained would name what a human approved and nothing else.

**What does not hold yet.** On the deployment the kill switch is on and no surface mints: T6.3 is
the approval loop, and until it lands the executor there can refuse and record and nothing more.
And the executor's own boundary is the compose network - Caddy forwards nothing to it - which is a
network property, not a credential; T6.8's re-hardening pass is where that is re-read.

**Read-only is a property of the tool surface, not of a credential.** In this world Prometheus and
Loki have no authentication at all — Prometheus runs with `--web.enable-lifecycle`, so
`POST /-/reload` is exposed to anything that can reach the port, and Loki's `/loki/api/v1/push` is
open by necessity. **An agent with a raw HTTP client and the endpoint could reload Prometheus's
configuration or write fabricated log lines into the corpus it is investigating.** What stands
between the agent and that is not a credential; it is that:

1. the tools expose query paths and no others — nothing constructs an arbitrary path from agent
   input;
2. no tool takes a URL, a host or a path from an agent — endpoints come from configuration;
3. `change_history` is read-only by construction, because the writer is the injector.

**So the safety property is structural and has no per-role scope.** Adding one write tool would
remove it for the *whole* runtime rather than for one role: the specialists would gain a
capability by neighbourhood, and "the metrics specialist cannot write" would become a claim about
prompt text, which is the weakest kind. That is ADR-0028 §3's argument for why the write path is
absent rather than disabled, and it is why a fifth tool gated by an approval flag was rejected —
the gate would be a runtime condition rather than a structural property.

**Deferred to T6.8 explicitly:** actual credentials on Prometheus and Loki, network policy
restricting who can reach them, egress restriction. Deferring is defensible only because the world
is a local benchmark. **A deployed instance with an unauthenticated Prometheus reachable from the
agent container is a finding, not a configuration** — which made this T5.5's problem the moment
anything was deployed. Something is deployed (2026-09-07), and T5.5 did not close it: see the
addendum below. The finding stands, on the internal network only.

---

## Thesis 3: the ingest webhook is unauthenticated, and anything reaching it can fabricate an incident

Measured over eight live deliveries (`docs/evidence/t2.1-webhook/`): Alertmanager sends no
signature, no shared secret and no credential of any kind — only
`User-Agent: Alertmanager/0.27.0`.

A fabricated incident is not merely noise. It drives an investigation, puts attacker-chosen text
into agent context (thesis 1), consumes a slot against the concurrency cap, and ends at a
remediation proposal. **Schema validation is the only occupant of that boundary**: a malformed body
is refused, and a well-formed one from anywhere at all is accepted. The receiver binds `0.0.0.0`
because Alertmanager reaches it from another container, which is the deployment that makes this
exploitable.

Not built at T2.1 deliberately — authentication belongs with the credential planes and the
public-surface work, not bolted onto a receiver in isolation. Defences at T6.8: a shared secret or
mTLS, network-level restriction to the Alertmanager host, and rate limiting so a flood cannot
exhaust the cap.

---

## Thesis 4: the same unauthenticated port now reads, and that is the wider exposure

T5.1 added `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}` and `GET /ui/incidents/{id}` to
the port thesis 3 describes. They inherit its gap **in the other direction: anything that can reach
the port can read every incident, every log line the agent quoted, and every query it ran.**

That is wider than the write path's exposure, because incident data carries the monitored world's
telemetry — which is the thing an attacker who has compromised that world would most like to know
this platform noticed.

**Structurally read-only, and that part is enforced.** The router never imports a writer, takes
only `get`-shaped protocols, and a test asserts its routes offer no verb but `GET`. A read surface
that could mutate would be an action plane nobody designed. But read-only is not the same as
authenticated, and the plan puts *"basic auth on the UI"* at T5.5. **Until something is deployed
this is a recorded hole; the moment anything is deployed it is an open one.** — *as written on
2026-09-03. T5.5 deployed on 2026-09-07 and closed this one first: the read routes and pages mount
behind `faultline.api.auth.guard()` and refuse to start without a credential. The addendum below is
the current state.*

---

## Thesis 5: untrusted telemetry reaches renderers, not only models

Thesis 1 is about text reaching a *model*. The same text reaching a *renderer* is a different
attack with different defences, and this platform now feeds two of them.

**The browser (T5.1).** A frontend that interpolates a log line into the DOM has an XSS hole fed by
the monitored system's own logs. Nothing server-side can force a frontend to escape, so the payload
labels instead: every world-produced string sits under an `untrusted` key, and timeline summaries
are built from structural fields only — role, tool, service — because a summary quoting the world
would put untrusted text outside the one block the label can follow. The page obeys it: its only
route into the DOM is a `textContent` helper, verified by **Chromium loading the page against a
stub API whose log line is `<img src=x onerror="window.__pwned=1">`** and asserting nothing fired.

**Slack (T5.2), which is the harder one.** There is no `textContent` equivalent, because the
mrkdwn parse happens on Slack's side after the bytes have left this process. So labelling is not
available and the stronger rule replaces it: **no caller-supplied value reaches a channel
unescaped**, and the only unescaped text in a notification is a literal in
`faultline/notify/messages.py`. Three mechanisms, three distinct attacks:

| defence | attack |
|---|---|
| escaping `&`, `<`, `>` | `<!channel>` **pages an entire on-call channel**; explicit link syntax renders an attacker's URL under an attacker's text |
| a code span, backticks stripped first | Slack **auto-links a bare URL**, which escaping does not touch at all — a log line becomes a clickable link carrying this platform's authority |
| collapsing whitespace | a multi-line value **forges a line** that reads exactly like one the platform wrote: `\n\n*Approved by:* sre-oncall` |

The third is the one about the reader *believing* rather than *clicking*, and it is the one an
escaping-only defence misses entirely.

**The generalisation.** Every new surface that renders incident data is a new instance of this, and
the count is now two. A future integration — email, PagerDuty, a webhook of somebody else's — gets
the same question, and the answer depends on what escaping the far side does, not on what this
repository intends.

---

## Thesis 6: retrieval gives attacker text a long half-life

The past-incident corpus is a path by which stored text re-enters agent context long after it was
written. **Today it is not attacker-reachable**: the seeder takes exactly one root, that root must
end in `dev`, every narrative's front matter is checked, and `tests/test_corpus.py` fails on any
path outside it. But those guards exist for *contamination*, not for security — they stop holdout
answers leaking into a benchmark, and they would not notice a poisoned narrative that sat in the
right directory.

**The product case is different from the benchmark case.** A real deployment seeds this corpus from
its own past incidents, whose narratives are written from telemetry an attacker influenced. A log
line poisons one investigation; a poisoned *past incident* is retrieved as relevant precedent for
every future incident that resembles it — the same attack with a much longer half-life, and one
that arrives wearing the authority of the platform's own history.

Nothing here defends that yet. Recorded so T6.8 attacks it rather than discovering it.

---

## Addendum, 2026-09-07: the deployed surface (T5.5, recorded under T5.6's audit)

Theses 2, 3 and 4 were written for a local benchmark and each ended with *"the moment anything is
deployed"*. Something is: one VM, `https://faultline.chandanasorakundla.com`, Caddy in front,
Faultline and the monitored world in two compose projects on one shared network
(`deploy/README.md`). This is what the deployment did about each thesis, and what it did not.

**Closed at the edge and in the process.**

| surface | before | now | where |
|---|---|---|---|
| read routes and pages (thesis 4) | unauthenticated | basic auth **in the application**: `auth.guard()` is a dependency on the mount, read before `psycopg.connect`, refused at startup without a credential | `faultline.api.app`, `tests/test_api_app.py` |
| alert receiver from the internet (thesis 3) | unauthenticated, `0.0.0.0` | **404 at the edge**: Caddy answers `/api/v1/alerts*` itself and proxies nothing. The world's Alertmanager posts to `faultline:8000` on the compose network and never crosses Caddy | `deploy/Caddyfile`, `tests/test_deploy.py` |
| the world's own UIs (Grafana, Jaeger, load generator) | no authentication of their own | basic auth **at the edge**, credential stripped before Grafana sees it (`header_up -Authorization`) | `deploy/Caddyfile` |
| transport | — | TLS terminates at Caddy; :80 redirects; basic auth is never sent in the clear | `deploy/Caddyfile` |
| host | — | `ufw` default-deny; 22, 80, 443 only; the receiver's port is not published to the host | `deploy/README.md` §3.2 |

Two things the table implies and one it does not. **Authentication is checked in two places against
two sources of truth** — a plaintext in the application's environment, a hash in Caddy's — and the
Caddyfile says why: Faultline authenticates itself so a test can drive it without a proxy, and the
demo's UIs check nothing, so the proxy is the only thing in front of them. Drift between the two is a
real failure mode and `deploy/README.md` §3.1 derives the hash from the one plaintext. **The 404 on the alert path is
a blocklist, not an allowlist** — a new unauthenticated route added to the receiver would be on the
internet until someone added a `handle` for it. What the table does *not* say is that the credential
is strong: it is one username and one password, brute-forceable at the rate Caddy will serve, and
the access log (`log { output stdout }`) is the only thing that would show it happening.

**Still open, on the internal network.**

- **Prometheus, Loki, Tempo (since T6.1), Jaeger and Alertmanager have no credentials** (thesis 2). They are reachable
  from every container on the shared `faultline-deploy-net`, including the agent container — the
  exact configuration §2 called *a finding, not a configuration*. It is a finding. The blast radius
  is one compose network on one host with nothing else on it; the fix (credentials on the datasources
  and a network policy between the agent container and the rest) is T6.8's and is not made smaller
  by being deferred again.
- **The alert receiver is unauthenticated from the network** (thesis 3). Anything on the compose
  network can open an incident and spend model calls. Today that is the world's own containers; a
  compromised one would have this path.
- **The model API key is in the orchestrator container's environment**, because the orchestrator
  now runs `faultline-investigate` itself (`FAULTLINE_ORCH_INVESTIGATE=1`). That container also
  reads the world's telemetry — the thesis-1 text — so the process that holds the key is the
  process that reads attacker-influenced input. Secret scrubbing before model calls is T6.8's;
  egress restriction on that container is T6.8's; both matter more now than when the key lived
  only on a laptop.
- **One host, no backups beyond a manual snapshot**, no rate limit on the credential, no alert on
  the access log. `docs/GATES.md` G6 is where reliability becomes a deliverable and this addendum
  does not pretend otherwise.

**What this changes in the list at the end.** *"Authentication on the ingest webhook and the read
routes"* is half done — the read routes are; the webhook is blocked at the edge and open inside.
*"Public-surface hardening of the deployed instance"* is now a task against a real surface with a
real access log, rather than a placeholder.

---

## Credentials this system holds

| Secret | Where | Handling |
|---|---|---|
| model API key | `ANTHROPIC_API_KEY`, environment only; on the VM, the orchestrator container's environment via `deploy/.env` | never in the tree; `pre-commit` runs `detect-private-key`; CI checks history; `deploy/.env` is gitignored and written from the key file without echoing it |
| Postgres DSN | `FAULTLINE_*_POSTGRES_DSN` | dev credentials are in `docker-compose.yml` and are dev-only by construction; a deployment supplies its own |
| Slack webhook URL | `FAULTLINE_NOTIFY_SLACK_WEBHOOK_URL` | **a bearer credential, not an address.** `SecretStr`; plaintext transport refused; `__repr__` overridden; every error string scrubbed |
| archive credentials | `boto3` environment | optional extra; absent by default |

**One non-obvious leak, worth generalising from.** HTTP client libraries put the request URL into
their exception messages — `requests.HTTPError` and `httpx.HTTPStatusError` both render as
`… for url '…'`. For a URL that *is* a credential, the ordinary act of logging a failed request
writes the secret to disk, and the failure most likely to be logged is a revoked webhook. The
notifier scrubs every string it emits and a test drives a real 404 to prove it. **Any future
integration whose credential lives in a URL has this problem**, and the general form is: a secret
in a URL is a secret in every stack trace that URL appears in.

---

## To complete at T6.8

- **Injection scenarios scored in the standard eval loop** — the residual in thesis 1 is currently
  unbounded by any number, and this is the only thing that would bound it.
- Egress restriction on the agent container.
- Secret scrubbing before model calls.
- Credentials and network policy on Prometheus and Loki (thesis 2).
- Authentication on the ingest webhook from inside the network (thesis 3); the read routes are
  authenticated since T5.5 and the webhook is blocked at the edge (addendum).
- Corpus-poisoning attack against retrieval (thesis 6).
- Public-surface hardening of the deployed instance; audit-log review; kill-switch drill.

**And one thing this document should keep doing.** Theses 4, 5 and 6 were all found by *building*
something — a route, a notifier, a corpus seeder — and not by a security review. That is an
argument for writing the thesis when the surface is built rather than saving it for the pass, and
it is a reason to expect T6.8 to find things this file does not list.
