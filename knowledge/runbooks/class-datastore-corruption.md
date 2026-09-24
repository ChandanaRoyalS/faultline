---
id: class-datastore-corruption
title: Fault class - datastore_corruption
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate]
actions: [restore_store]
---

The service's datastore is reachable and healthy, and what it holds cannot be read. The
connection succeeds, the read succeeds, and decoding what came back fails.

**Resolves by `restore_data`.** The wrong thing is the stored contents, so the fix is to discard
or restore them - `restore_store`. Recreating the service changes nothing: it reads the same bad
bytes on its next request. Reverting configuration changes nothing: the address was right all
along.

## What the target shows, measured

**Parse failures, with the connection fine.** The service's own log names the decoder and the
failure - a protocol-buffer parse error reporting that the input ended in the middle of a field -
wrapped in the service's own "cannot access storage" message and returned to the caller as a
failed-precondition status. That is the (c) evidence and it separates the class from a
misconfigured store address, which logs *connection* failures.

**Only reads of corrupted state fail.** Writes succeed, reads of state that does not yet exist
return an empty result, and the service's own error ratio is diluted by both. Measured: the
store's owner sat at 7% while its caller - which reads the store exactly once per request and
fails the whole request on that read - sat at 19% and paged first. **The page lands on the caller
that depends on one read**, and the culprit's own ratio crosses the line late or not at all.

**Cadence matters to whether it is seen at all.** State that is written and read within
milliseconds and then abandoned is only ever seen corrupted if the corruption lands inside that
window. A corruption applied every few seconds touched almost no live state and produced nothing;
applied continuously it produced the page above. A store that "is corrupted" and a service that
"reads corrupted data" are different claims.

## What the change record holds

**Nothing.** No artifact, no configuration, no flag changed; the store's contents did. An empty
change log with a datastore-shaped error in the culprit's log is this class.

## The downstream picture

A service that fails one request in a chain stops the rest of the chain: every service behind the
failed step goes quiet by starvation rather than by fault. Measured: the payment, email and
shipping services halved with nothing wrong with them.

## Recovery is clean

Discarding the corrupted contents clears every alert within four minutes with no second wave,
because nothing was hanging - failures were fast.
