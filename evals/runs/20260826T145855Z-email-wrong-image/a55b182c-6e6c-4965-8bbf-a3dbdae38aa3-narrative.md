# Checkout alert with nine-service blast radius: change history cleared, mechanism never established

## What was visible at the start

The page came from checkoutservice. Triage put the blast radius at nine services and flagged four edges between them as unmeasured — no telemetry crossing those links, so any reasoning about who was waiting on whom would be guesswork. The incident marker was placed at 15:02:30Z. Nothing about the alert itself said whether checkout was returning errors, timing out, or simply breaching a threshold on a metric that had been drifting for a while; that ambiguity was never resolved during the investigation and it shapes everything below.

Severity was set critical. That is worth remembering when reading the sequence of dispatches that followed, because the entire budget went to a single line of questioning.

## The line of questioning that was actually pursued

Every dispatch made in this investigation was a change-history lookup. Four services were queried in turn: checkoutservice first (T+0 through the early minutes), then cartservice, then productcatalogservice, then shippingservice. The hypothesis behind all four was the obvious first one — something shipped, and the thing that shipped broke checkout.

All four came back empty. No deploys, no config pushes, no rollouts in progress, no feature flag flips, for any of those four services. Consistently empty across four independent services is itself mildly informative: it is not one service's change log being unwired, it is a genuine quiet period in the deploy record.

> Evidence `tr_bb89b8b60376`:

```
<tool_result id="tr_bb89b8b60376" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_bb89b8b60376>
```

> Evidence `tr_1adfefef832f`:

```
<tool_result id="tr_1adfefef832f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_1adfefef832f>
```

> Evidence `tr_f7b2ba25b9a0`:

```
<tool_result id="tr_f7b2ba25b9a0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f7b2ba25b9a0>
```

> Evidence `tr_9ee9d491d4c3`:

```
<tool_result id="tr_9ee9d491d4c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for shippingservice over this window
</tool_result:tr_9ee9d491d4c3>
```

## The window problem — read this part twice

Each of the four queries was asked to cover the hour preceding the incident. Each of them silently executed against a fifteen-minute window instead: 14:52:30 to 15:07:30Z. Ten minutes before the marker, five minutes after. Nobody noticed at dispatch time; it only surfaces when you read the returned window boundaries against the requested ones.

The practical consequence is that the negative result is much narrower than it reads. What is genuinely excluded is a change landing in the ten minutes before onset, or a rollout still progressing through the five minutes after. What is entirely unexamined is 14:02:30 to 14:52:30 — forty minutes in which something could have landed and then taken time to bite. A leaked handle, a connection pool filling slowly, an image pulled lazily on the first cold start after a rollout: all of those detach the moment of the change from the moment of the symptom, and all of them would be invisible to the queries that were run.

If you are picking this up cold, re-running these four lookups against the actual full hour is the cheapest useful thing you can do.

> Evidence `tr_bb89b8b60376`:

```
<tool_result id="tr_bb89b8b60376" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_bb89b8b60376>
```

> Evidence `tr_1adfefef832f`:

```
<tool_result id="tr_1adfefef832f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_1adfefef832f>
```

> Evidence `tr_f7b2ba25b9a0`:

```
<tool_result id="tr_f7b2ba25b9a0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f7b2ba25b9a0>
```

> Evidence `tr_9ee9d491d4c3`:

```
<tool_result id="tr_9ee9d491d4c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for shippingservice over this window
</tool_result:tr_9ee9d491d4c3>
```

## Dead ends, and why they were reasonable

Four sub-hypotheses were retired on the strength of the empty change logs, and they are worth keeping so nobody re-treads them for the narrow interval they do cover.

A just-in-time deploy of checkoutservice as trigger: excluded for the ten minutes before onset. A flag flip or config push landing exactly at onset: excluded, the log is empty across the marker itself. A rolling change still in flight and worsening things: excluded, nothing recorded through 15:07:30. And on productcatalogservice specifically, rollback was ruled out as a remediation avenue — there is no recent change there to roll back, so a responder reaching for that lever is wasting minutes.

One more that reads as a dead end but is really a soundness check: an emergency rollback performed during the incident would itself appear as a recorded change event on cartservice. None does. So the empty log is not hiding in-window firefighting.

These are all real eliminations. They are also all eliminations of the same hypothesis, sliced four ways. The investigation ended having established that one causal story is unlikely within a fifteen-minute slice, and nothing at all about what the actual mechanism is.

> Evidence `tr_bb89b8b60376`:

```
<tool_result id="tr_bb89b8b60376" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_bb89b8b60376>
```

> Evidence `tr_1adfefef832f`:

```
<tool_result id="tr_1adfefef832f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_1adfefef832f>
```

> Evidence `tr_f7b2ba25b9a0`:

```
<tool_result id="tr_f7b2ba25b9a0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f7b2ba25b9a0>
```

> Evidence `tr_9ee9d491d4c3`:

```
<tool_result id="tr_9ee9d491d4c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for shippingservice over this window
</tool_result:tr_9ee9d491d4c3>
```

## What was never looked at

No error rates. No latency percentiles. No saturation or resource metrics. No logs. No traces. Not for checkoutservice, which raised the alert, and not for any of the other eight services in the blast radius. Five of the nine services were never dispatched to at all, and the four edges triage flagged as unmeasured stayed unmeasured.

Because of that gap, the two broad shapes of a checkout failure cannot be separated: did checkout stall waiting on something downstream, or did it run out of something of its own? Dependency timing would answer the first, resource and saturation data the second, and neither was gathered.

The onset time is also unconfirmed as an onset. 15:02:30 is when a threshold was crossed. Whether that is when the condition began, or simply when a slow degradation finally tripped a line, is open — and the answer changes which forty-minute window matters.

## A prior pattern that deserves a look

Two historical incidents surfaced during retrieval, both centred on cartservice: one involving a bad image tag, one a Redis misconfiguration. What makes them relevant is not the specific cause but the shared presentation — in both, cartservice reported a flat-zero error rate and looked entirely healthy on its own dashboards while starving the services calling into it.

cartservice is inside this blast radius. The change-log lookup done here says only that cart shipped nothing in the queried fifteen minutes; it says nothing whatsoever about cart's runtime state. So the healthy-looking-but-starving pattern is neither confirmed nor refuted. Given two prior incidents with the same signature, checking cart's actual behaviour — downstream call latency, queue depth, connection pool state, and critically the view from its callers rather than from cart itself — is the strongest lead available.

## Where this stands

The cause is not established. Confidence is low and no fix class was identified. What exists is a negative result about one hypothesis, valid only for a fifteen-minute window that was not the window requested.

Open questions, in the order I would take them: (1) get any failure signature at all — error rate and latency for checkoutservice, then outward across the blast radius; (2) re-run the four change lookups against the genuine full hour, 14:02:30 onward, watching for a delayed-onset change; (3) test whether cartservice is healthy or merely healthy-looking, using its callers' view; (4) separate waiting-on-something from running-out-of-something with dependency timing and saturation data; (5) reach the five untouched services and the four unmeasured edges; (6) determine whether 15:02:30 is onset or merely detection.

> Evidence `tr_bb89b8b60376`:

```
<tool_result id="tr_bb89b8b60376" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_bb89b8b60376>
```

> Evidence `tr_1adfefef832f`:

```
<tool_result id="tr_1adfefef832f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for cartservice over this window
</tool_result:tr_1adfefef832f>
```

> Evidence `tr_f7b2ba25b9a0`:

```
<tool_result id="tr_f7b2ba25b9a0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f7b2ba25b9a0>
```

> Evidence `tr_9ee9d491d4c3`:

```
<tool_result id="tr_9ee9d491d4c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T14:52:30.583000+00:00..2026-08-26T15:07:30.583000+00:00">
no changes recorded for shippingservice over this window
</tool_result:tr_9ee9d491d4c3>
```
