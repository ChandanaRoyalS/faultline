# Critical edge degradation across eight services, investigated through change history alone

## What paged, and what the responder saw first

The page came from the edge: frontend and frontend-proxy both alerted. Nothing else paged directly, but the eventual blast radius covered eight services, and the path from the edge symptom inward crossed seven edges that were never measured — no latency, error-rate or saturation signal was collected on any of them.

The responder's first and, as it turned out, only instrument was the change log. The working assumption at T+0 was the usual one for a sudden critical edge symptom with no prior warning: something shipped. That assumption shaped the entire investigation, and it is the main thing a future reader should second-guess.

## The order the investigation actually went

Four change-history queries were run, in sequence, against frontend, flagd, product-catalog and cart. That consumed the whole change-tool budget. No logs were pulled, no metrics were charted, no traces were opened. The verdict below therefore rests on a single class of evidence looked at from four angles.

The first three queries all came back empty. Frontend: no deployments, no config edits, no flag flips anywhere in the ~24h window. flagd: no flag-definition edits, no configuration pushes, no rollouts. product-catalog: likewise nothing of any change type. Three empty answers in a row is informative but also seductive — it pushed the responder toward whichever service *did* have activity, rather than toward asking whether change history was the right instrument at all.

> Evidence `tr_3ee9f1d9c2d0`:

```
<tool_result id="tr_3ee9f1d9c2d0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_3ee9f1d9c2d0>
```

> Evidence `tr_e43b450c79ab`:

```
<tool_result id="tr_e43b450c79ab" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="outside_radius">
no changes recorded for flagd over this window
</tool_result:tr_e43b450c79ab>
```

> Evidence `tr_a0fba146a838`:

```
<tool_result id="tr_a0fba146a838" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_a0fba146a838>
```

## The one service with activity

Cart was the exception. Its change log held eight entries, every one attributed to platform-automation, none to a human. They form four identical cycles: a 2.2.0 cart hotfix container image reference applied, then reverted back to unset, each cycle lasting roughly nine to thirteen minutes. The oscillation itself is a real finding — it reads like a reconciliation loop or a rollout that could not hold — and it is worth a ticket regardless of this incident.

The timing, however, does not cooperate. The entries span a window ending about 2.4 hours before onset, and the last action in that sequence was a revert, not an apply. The hotfix image was therefore *not* live when the symptom began; cart was running its prior reference for the preceding 2.4 hours. Nothing in the cart log lands near the onset time.

> Evidence `tr_6e9458b3abec`:

```
<tool_result id="tr_6e9458b3abec" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="candidate_cause" hops="1">
service: cart
8 changes, ranked by suspicion
  #1  2.4h before onset  2026-10-14T00:15:38.172165+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  2.5h before onset  2026-10-14T00:06:53.846025+00:00  platform-automation  image updated: image reference updated on cart
```

## The leading hypothesis, and why confidence is low

The hypothesis the investigation settled on: the reconciliation loop on cart left the service's image reference unset or indeterminate, meaning the running artifact was not the one that should have been running, and that mismatch surfaced at the edge as the frontend and frontend-proxy alerts.

This is a hypothesis, not a finding. Two things weigh directly against it: the 2.4-hour gap between the last cart action and onset, and the fact that the hotfix build was explicitly not deployed at onset. If the reader takes one thing from this record, take that — the proposed fix class is rollback, but the evidence already shows there is nothing newer to roll back to. Treat 'rollback' here as shorthand for 'stabilise the reconciliation loop', not as a ready action.

> Evidence `tr_6e9458b3abec`:

```
<tool_result id="tr_6e9458b3abec" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="candidate_cause" hops="1">
service: cart
8 changes, ranked by suspicion
  #1  2.4h before onset  2026-10-14T00:15:38.172165+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  2.5h before onset  2026-10-14T00:06:53.846025+00:00  platform-automation  image updated: image reference updated on cart
```

## Dead ends, and the one that was not really a dead end

Four lines were closed out and are worth recording so nobody re-walks them:

A frontend release, config edit or flag flip as trigger — excluded; the log is empty for the whole window, and for the same reason a frontend rollback is not an available remedy. A flagd flag push, a flapping sequence of flag updates, or an operator remediation on flagd during the event — all excluded by the same emptiness. A product-catalog deploy, config change or rollback — excluded. On cart specifically: a human-pushed risky change (all entries are automation), a non-image change such as an env var or scaling edit (every entry is an image reference update or revert), and the clean story that the hotfix was live and simply needs reverting (it was already reverted).

The important caveat, and the reason one of these is softer than it looks: all three empty-log queries *began* at the onset timestamp and ran forward ~24 hours. They do not cover the minutes before onset. So 'no frontend change caused this' really means 'no frontend change at or after onset caused this'. A change landing five minutes before the page would be invisible to every one of those three queries. That is the single most correctable gap in this record.

> Evidence `tr_3ee9f1d9c2d0`:

```
<tool_result id="tr_3ee9f1d9c2d0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_3ee9f1d9c2d0>
```

> Evidence `tr_e43b450c79ab`:

```
<tool_result id="tr_e43b450c79ab" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="outside_radius">
no changes recorded for flagd over this window
</tool_result:tr_e43b450c79ab>
```

> Evidence `tr_a0fba146a838`:

```
<tool_result id="tr_a0fba146a838" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="candidate_cause" hops="1">
no changes recorded for product-catalog over this window
</tool_result:tr_a0fba146a838>
```

> Evidence `tr_6e9458b3abec`:

```
<tool_result id="tr_6e9458b3abec" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T02:38:31.664000+00:00..2026-10-14T02:40:22.778042+00:00" radius="candidate_cause" hops="1">
service: cart
8 changes, ranked by suspicion
  #1  2.4h before onset  2026-10-14T00:15:38.172165+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  2.5h before onset  2026-10-14T00:06:53.846025+00:00  platform-automation  image updated: image reference updated on cart
```

## What a responder picking this up should do first

Re-run the frontend, flagd and product-catalog change queries with the window shifted to *start* well before onset — an hour prior is enough — because the existing answers simply do not cover that interval.

Then break out of change history entirely. The actual signature of the failure at onset is unknown: nobody established whether services were hanging, returning errors, or restarting. Any one of those points at a different cause and would immediately raise or collapse the cart hypothesis.

Finally, four of the eight services in the blast radius were never queried at all, including frontend-proxy — which paged — and cart's own downstream dependencies. A dependency-side cause, whether slow responses, exhausted capacity, or a stalled process, remains completely untested. The investigation never reached a position to rule it out; it just never looked.

