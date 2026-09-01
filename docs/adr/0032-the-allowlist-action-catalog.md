# ADR-0032 — the allowlist action catalog

**Status:** accepted, 2026-09-01
**Task:** T2.4b (the third of its three deliverables)

## Context

T2.4b's deliverable is *"Seeded runbook corpus + past-incident store + read-only allowlist"*.
An audit on 2026-09-01 found the past-incident store delivered and the other two absent — the
string `allowlist` appeared nowhere in `src/`, in any ADR, or in any file of this repository.

Two later tasks depend on it. T3.9's remediation proposer is specified to map an accepted
hypothesis to *"runbook-derived remediation options"* against this catalog, and T6.2 is what
makes its entries executable. The proposal's failure table also assigns it a job: an action
whose target is outside the incident's scoped topology is *"hard-rejected before the approval
is even requested"*, and the allowlist validator is where that rejection lives.

## Decision

A read-only, git-versioned YAML document at `knowledge/allowlist.yaml`, loaded by
`faultline.context.allowlist`, with four decisions worth recording.

**It names classes of action against a selector, never a service.** Every entry's target is
`incident_scoped_service`. Pinning services here would move the blast-radius check into a
document that cannot see the incident, and the executor is where the proposal says that check
belongs.

**Read-only is enforced, not asserted.** `tests/test_allowlist.py` fails if any module other
than the loader names the file, and parses the loader's AST to prove it cannot write —
docstrings excluded, since prose may name what code must not do. The reasoning: the
investigation runtime is the part of this system that reads untrusted telemetry, and a
catalog it can edit is not a control. `docs/THREAT-MODEL.md` already assumes this property;
until today nothing produced it.

**`scale` is listed and marked unperformable.** ADR-0029 measured that Compose refuses to
scale a service declaring `container_name` and that 25 of this world's services declare one.
Omitting the class would make its absence look like an oversight; listing it without the
status would let something propose an action the world cannot perform. It is listed, marked,
and made to cite the ADR that measured it — a test enforces that citation.

**`remediation_class` is a `str`, not `RemediationClass`.** That enum lives in `evalharness`
and ADR-0004 forbids the product depending on the harness. The correspondence is checked in
a test, which may import both, rather than by a type the product is not allowed to hold.

## Consequences

The catalog is a document and not yet a capability: T6.2 makes entries executable, and until
then a proposer may cite an entry and nothing may perform one.

It does **not** move any digest. `compose_digest` and `observability_digest` cover named file
lists that do not include it, and `runtime_version` hashes `stamp._CONTRACTS` — an explicit
four-model tuple — plus the role `*_SYSTEM` prompts. `AllowlistAction` is deliberately not in
that tuple, because no role prompt yet promises a model it will be held to it. **T3.9 will
move the stamp**, on both counts: it adds a proposer system prompt and a proposal contract.
That cost belongs to T3.9 and is recorded here so it is not a surprise.

The catalog is versioned by an integer, and `catalog_version` is expected to change when an
entry's meaning changes. Nothing consumes the version yet; T6.2 should pin it per approval so
an approval token cannot outlive the catalog it was granted against.
