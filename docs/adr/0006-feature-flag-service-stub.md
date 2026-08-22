# ADR-0006: A native stub for the feature-flag service

- **Status:** accepted (supersedes the "disable it" decision in ADR-0005)
- **Date:** 2026-08-22
- **Task:** T1.1 / T1.3

## Context
ADR-0005 disabled the demo's feature-flag service because it segfaults under x86
emulation on Apple Silicon and its native build is blocked by upstream bit-rot. That ADR
measured the cost as log noise (17% of lines) and judged it filterable.

That measurement was incomplete. Baseline metrics collected in T1.3 showed the real cost:

    recommendationservice   FeatureFlagService/GetFlag      66.7% error rate
    productcatalogservice   FeatureFlagService/GetFlag      11.5%
    recommendationservice   get_product_list                 cascade
    frontend                RecommendationService/List...    cascade
    frontend / loadgenerator  HTTP GET                       user-visible errors

Callers record a failed flag lookup as an error span, so a dead dependency cascaded all
the way to the storefront. A permanently broken world is unusable for this project: alert
thresholds would have to sit above a 66% error rate, and the metrics analyst agent would
learn to ignore precisely the signal it exists to detect.

## Decision
Replace the service with a native-arm64 gRPC stub implementing the same contract
(`compose/ffs-stub/`). gRPC code is generated at image build time from the demo's own
`pb/demo.proto`, so the contract cannot drift. Every flag lookup returns `enabled: false`
— which is what the real service returns in normal demo operation, since flags exist to
inject faults on demand.

The stub occupies the same compose service name, so callers resolve it by DNS with no
change on their side. Compose runs with `--no-build`, so the demo's own build definition
is inert and the pinned clone is never edited.

## Consequences
Measured after the change, with dependents restarted to reset cached gRPC channels:
**error rate 0.000 across every service; no erroring operations.**

We lose the demo's built-in fault injection, which costs nothing — T1.4 builds a
purpose-built injector covering all eight fault classes precisely because the demo's flags
cover only a few.

ADR-0005's log filter remains in place and is now redundant but harmless; it stays as a
safety net and costs one Promtail stage.

Revisit if: the project moves to x86 hardware, where the real service runs unmodified.
