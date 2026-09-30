# Q120's audit: the traces behind six labels and R6, re-read whole

**2026-09-30, $0, read-only, no model call.** From 2026-09-28 14:55 until the repair at
2026-09-30 06:39 UTC, Tempo's search could not see its stored blocks (**Q120**). Every trace
read in that span came from the ingester's last five to seven minutes. Six labels and R6's
read-back had read their traces that way, so Q120 listed them for audit once the search could
reach every stored minute again. This directory holds the audit. There are five scripts, all
read-only against the running world, each run once on the owner's machine, and each run's output
is kept verbatim beside it (`docs/evidence` is excluded from the formatting hooks). The
scripts are kept byte for byte as they ran, with `.txt` appended so the repository's Python
linter and formatter, which do reach this directory, leave them as they were.

| file | run at (UTC) | what it read |
|---|---|---|
| `pass_1.py.txt` → `pass-1.txt` | 07:54:58 | each window: trace counts per minute, and trees from the fault's start, middle and end |
| `pass_2.py.txt` → `pass-2.txt` | 08:00:33 | search completeness, the 131 email traces placed, the failing POST's durations |
| `pass_3.py.txt` → `pass-3.txt` | 08:06:29 | whole-window negatives with structural TraceQL, results filtered by the search's start times |
| `pass_4.py.txt` → `pass-4.txt` | 08:18:32 | every matched trace fetched whole, each matched span placed by its own timestamps |
| `skew_probe.py.txt` → `skew-probe.txt` | 08:21:37 | which spans carry old timestamps, from which process, since when |

## The outcome

**Four labels could not be re-read.** Their windows were more than 24 h old when the search
was repaired. They were past Tempo's `block_retention`, and retention deleted them when the
poll came back. The first pass found nothing in Tempo for any of them. Their trace items stand
as read: real traces, from the fault's last minutes. Each label's header now says so. They are
`v2-cart-store-corruption` (00:20:23-00:31:39 on 2026-09-29), `v2-kafka-disk-fill`
(02:30:05-02:41:20), `v2-inj-kafka-disk-fill-log-checkout` (03:46:50-03:57:21) and
`v2-inj-cart-flag-failure-log-checkout` (05:56:09-06:07:25).

**Two labels and R6 were re-read across the whole fault, and every trace claim held.** Pass 4 is
the reading of record: each matched span was placed by its own start time, not by the start
time the search reported (see below for why that matters).

| window | claim | the whole fault, re-read |
|---|---|---|
| `v2-inj-payment-dependency-latency-log-checkout` (01:24:16-01:34:36, 2026-09-30) | every slow order: checkout's Charge about 301 ms over payment's own span of 0.3 ms | 92 slow Charges, all inside the fault (01:24:22-01:34:19), 300.7 to 304.3 ms, median 301.2; payment's server span beneath each 0.2 to 1.3 ms, median 0.3 |
| | PlaceOrder about 310 ms | 309.3 to 329.1 ms, median 313.5 |
| | no span in error | no slow trace holds a span in error (a search over the window and after it returned none) |
| | the gap is the fault | every Charge inside the fault was slow (92 of 92); the 200 after the fix took 0.6 to 6.2 ms |
| `v2-inj-email-wrong-image-log-checkout` (02:32:57-02:43:29) | checkout's POST to email fails in about 2 ms, "no such host" | 88 failing POSTs inside the fault (02:33:04-02:43:18), 1.7 to 106.2 ms, median 2.4, p90 3.8; two over 10 ms (106.2 ms in the first minute, 16.4 ms near the end); one more at 02:43:30, a second after the fix, 0.4 ms |
| | nothing beneath the failing POST | none has any span beneath it |
| | PlaceOrder above it not in error | none in error; 8.2 to 132.1 ms, median 14.1 |
| | email produces no span of any kind | none inside the fault; its first span after it at 02:43:36, 7 s after the fix, as its log's first confirmation line |
| R6 (05:04:02-05:15:34) | (d): catalog spans in error over database spans that are not | 947 catalog server spans in error, 0.2 to 3.7 ms, median 0.5; all 947 over a `sql.conn.query` not in error, none over one in error |

**No label is corrected.** The email label's "about 2 ms" stays: the median is 2.4 ms and the
p90 3.8 ms, and the two slow ones are named here. R6's RESULT gains an addendum with the
re-read.

## How the audit read its own numbers wrong twice, and why

**Pass 1's "per minute" counts were not per minute.** On the payment and email windows they fell
steadily (92 → 7, 89 → 5) while the bundles' rates held. Pass 2 showed each minute's search
returning every matching trace that ended after the minute began, however much later that was. The search ending at the email
fix returned 131 email traces, and all of them began after it. The search from the onset's minute
found exactly seven more, the seven confirmations email's log shows between 02:32:00 and the
onset.

**Pass 3 then filtered by the start time the search reports, and on those two windows it removed
every trace**, including all 89 failing POSTs, which exist only during the fault.

**The cause is one service's clock** (pass 4 and the skew probe). Every span quote sends is
stamped **18h37m07s in the past**. Read to the second against each trace's median span, the offset is the same in the payment window, the
email window, R6's window and the last half hour. No other service is off, across 450 traces and
7,411 spans: Go, Node, .NET, Python, Ruby, Rust, C++ and Envoy are all consistent. Tempo takes a
trace's start from its earliest span, and every order calls quote through shipping. So every
order trace "starts" 18h37m07s early and overlaps every search window back to that time.
R6's matched traces held no quote span: they were product pages, recommendations and orders
that failed at their product lookups, before the shipping quote. That is why R6's per-minute
counts summed to its whole and pass 3 kept all 947.

**The mechanism is not established.** One hypothesis fits the evidence: quote's SDK stamps
spans with a wall-clock reference taken once at process start, plus monotonic time. The Docker
VM's monotonic clock does not advance while the Mac sleeps. quote's container started 2026-09-28
22:20:23, and in the traces read it is the only service whose spans come from the PHP SDK. That predicts an offset that
grows with each sleep and resets when quote restarts. Neither prediction has been measured.
This is **Q121**, with what it does to the agent's trace tool.
