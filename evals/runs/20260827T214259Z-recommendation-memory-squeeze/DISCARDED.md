# Discarded run

**Reason:** baseline gate refused

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results directory, so the number of runs is a fact nobody can hide by tidying.

baseline gate refused; nothing was injected.
  - 2 alert(s) firing
  - p95 above 1000ms: checkoutservice at 15000ms
  - serving no traffic: accountingservice (frontend-proxy at zero is the healthy state and is not counted)
  - 1 non-terminal incident(s) in the store: d9b52121-de72-4198-8369-2c5b96e3beff - a new alert would correlate into one rather than opening its own
The world must be quiet before a scored run, or the run measures the world's prior state as well as the fault (ADR-0022 §3.1). Containers settle in 300s.
