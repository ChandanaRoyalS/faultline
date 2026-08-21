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

## To complete at T6.8
Egress restriction · secret scrubbing before model calls · public-surface re-hardening of
the deployed instance (authenticated approval endpoints, executor unreachable from the
internet) · audit log review · kill-switch drill.
