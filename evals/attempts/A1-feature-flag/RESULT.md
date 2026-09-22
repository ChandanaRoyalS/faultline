# A1 — feature flag `productCatalogFailure` — RESULT

**Run 2026-09-22 13:51:45 → 14:14:41 UTC, \$0.** The first run at 13:46 was void (helper crashed
before its first poll; `transcript-void-1346.txt`). This is the second, `transcript.txt`, and the
only one scored. The verdicts below are the pre-registered definitions applied to the transcript
and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceHighErrorRate/frontend` firing at 13:57:52 — **6 min 07 s** after injection. `frontend` calls `product-catalog` directly, which the definition covers. `ServiceHighErrorRate/frontend-proxy` fired 30 s earlier, at 13:57:22, but `frontend-proxy` calls `frontend`, not the target, so it is recorded as a finding and not counted |
| **DISTINCT from `bad_config`** | **yes, on (b)** | (b) no compose change exists to record — the only change on the world is flagd's reload of a bind-mounted file. A `bad_config` injection leaves a compose override in `change_history`; this leaves nothing. That alone satisfies the definition. (d) supports it: the source sets the span status to *"Error: Product Catalog Fail Feature Flag Enabled"* (`main.go:492-497`), a message no env-var fault produces — **stated from source, not yet read back from Tempo**, see below. (c) is **unavailable**: the target wrote nothing to its logs in thirteen minutes of fault. (a) is not relied on |
| **REVERTS** | **yes** | flag off at 14:05:04; both alerts cleared by 14:07:11 (**2 min 07 s**); quiet for the remaining 7 min 30 s of the recovery window |
| **ADMISSIBLE** | **yes** | pages, distinct, reverts, and is not an existing mechanism |

**Prediction scorecard.** PAGES: right. Rule: right (`ServiceHighErrorRate`). **Service: wrong** —
predicted `product-catalog`, actual `frontend`. Timing: 6:07 against "within 6 min" on the direct
caller; the first fire anywhere was 5:37. DISTINCT: right, but I led with (c) and (c) was empty;
it holds on (b). REVERTS: right.

## What the shape at minute twelve shows, and why the service prediction was wrong

| service | error ratio at 14:03 | role |
|---|---:|---|
| `frontend-proxy` | **8.52%** | fired first |
| `frontend` | **8.00%** | fired; the direct caller |
| `product-catalog` | **4.63%** | **the culprit — under the 5% line** |
| `load-generator` | 4.60% | the client's view of the same failed pages |
| `checkout` | 2.07% | calls product-catalog during checkout |
| `fraud-detection` | 1.82% | downstream of checkout via Kafka |

**The flag fails one specific product, so the culprit's own ratio is one failing product diluted
across everything it serves** — every `ListProducts` for every homepage counts in the denominator.
It reached 4.63%, a third of a point under the rule. **The frontend fetches several products per
page and one failure fails the page**, so its ratio is amplified to 8%. The fault is in
`product-catalog`; the page lands on its caller.

p95 is unchanged everywhere. The failures are fast — `product-catalog` at 4 ms — which is what an
error-injecting flag looks like as opposed to a latency one, and is the reason `ServiceHighLatency`
is silent.

## Three findings beyond A1

**1. ADR-0029 §4's topology finding is now measured on v2.** *"The topology flattens the page"*:
the culprit did not page, its caller did. This is the first v2 instance, and it means alert shape
— dimension (a) — is unlikely to separate classes on this world. **Distinctness for A2, A3, A4 and
A8 should be expected to rest on (b), (c) and (d)**, as it did here. The registration already
named all four dimensions; this is the measurement that says which ones will carry the weight.

**2. `product-catalog` emits no log lines during a fault.** Thirteen minutes, ~4,000 requests,
~185 errors, and `docker logs --tail 8` is empty (driver is `json-file`; the void run at 13:46
saw the same). The service reports failure through span status and span events, not through its
log. **For any scenario on this service, the logs specialist has nothing from the culprit.** That
is a property of the service the catalog will have to carry, and it is a reason (d) — traces —
matters more here than it did on v1.

**3. `frontend-proxy` fires before `frontend`.** 30 s earlier, at a slightly higher ratio (8.52 vs
8.00). Envoy's spans are one per request with no internal children, so its ratio is not diluted the
way a service with client spans is. The first alert on this world for a backend fault will usually
be `frontend-proxy`'s, and the second `frontend`'s. Recorded so a scenario's expected page can be
written correctly.

## What is owed before this result is leaned on

**Dimension (d) is stated from source and has not been read back.** The claim that the span
carries the flag's message is `main.go:492-497`. It should be confirmed with one `trace_query`
against Tempo for a `product-catalog` span in the 13:52–14:05 window, and this file amended with
what came back. It does not change the verdict — (b) is sufficient — but a distinctness argument
that cites a span message should have seen the span.

## Timeline

| clock (UTC) | event |
|---|---|
| 13:51:45 | flag on |
| 13:57:22 | `ServiceHighErrorRate/frontend-proxy` firing (+5:37) |
| 13:57:52 | `ServiceHighErrorRate/frontend` firing (+6:07) — **PAGES** |
| 14:03:22 | last observation poll; shape captured |
| 14:05:04 | flag off |
| 14:07:11 | both alerts cleared (+2:07) — **REVERTS** |
| 14:14:41 | recovery window ends, quiet throughout |
