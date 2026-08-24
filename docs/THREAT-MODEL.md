# Faultline Threat Model

> Skeleton — completed at T6.8 (security pass). Core theses recorded now so they shape
> the code from the start, not as retrofits.

## Thesis 1: telemetry is untrusted input
Logs, traces, and commit messages are attacker-influenced text that flows into agent
context. A malicious log line is a prompt-injection vector. Defenses (built at T2.6,
attacked at T6.8): tool results wrapped as delimited, typed, trust-labeled data;
privileged decisions (state transitions, action proposals) validated outside the model;
injection scenarios scored in the standard eval loop.

## Thesis 2: two credential planes, structurally separated
The investigation runtime holds only per-tool read-only credentials. Write credentials
exist only in the executor service, which validates actions against an allowlist and a
single-use, action-bound human-approval token. A fully compromised investigation agent
cannot execute a write, because the tokens it holds cannot.

## Thesis 3: the ingest webhook is unauthenticated, and that is currently a hole
Measured over eight live deliveries (`docs/evidence/t2.1-webhook/`): Alertmanager sends no
signature, no shared secret and no credential of any kind — only
`User-Agent: Alertmanager/0.27.0`. **Anything that can reach the port can fabricate an
incident**, and a fabricated incident is not merely noise: it drives an investigation, puts
attacker-chosen text into agent context (thesis 1), and ends at a remediation proposal.

Schema validation is the only occupant of that boundary today (T2.1, ADR-0015): a malformed
body is refused, and a well-formed one from anywhere at all is accepted. Nothing else about
the receiver assumes otherwise — it is bound to `0.0.0.0` because Alertmanager reaches it
from another container, which is the deployment that makes this exploitable.

Deliberately not built at T2.1: authentication belongs with the credential planes and the
public-surface work, not bolted onto a receiver in isolation. Defences (built at T2.6,
hardened at T6.8): a shared secret or mTLS on the receiver, network-level restriction to the
Alertmanager host, and rate limiting so a flood cannot exhaust the investigation concurrency
cap.

## To complete at T6.8
Egress restriction · secret scrubbing before model calls · public-surface re-hardening of
the deployed instance (authenticated approval endpoints, executor unreachable from the
internet) · audit log review · kill-switch drill.
