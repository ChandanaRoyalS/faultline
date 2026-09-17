# Refused run

**Reason:** baseline gate refused

**Nothing was injected and this scenario was not attempted.** This is not a discard: a discard is a run that happened and produced no result. Recorded rather than deleted, so a refusal that recurs is visible as a pattern.

baseline gate refused; nothing was injected.
  - 3 alert(s) firing
  - injector reports active faults: 1 active injection(s)  [state: /Users/chandana/dev/faultline/.faultline/injections.json]

product-catalog-flag-failure
    class  : bad_config
    target : featureflagservice
    started: 2026-09-16T10:19:30.246752+00:00 (989m47s ago)
    params : env_var=FAULTLINE_ENABLED_FLAGS, value=productCatalogFailure
    revert : recreate featureflagservice without /Users/chandana/dev/faultline/.faultline/overrides/product-catalog-flag-failure.yml
  - 1 non-terminal incident(s) in the store: 84f15826-3204-4e5e-ae0d-25b1844301a1 - a new alert would correlate into one rather than opening its own
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
