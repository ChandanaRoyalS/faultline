# A4 first run — VOID, and why

**Nothing paged in twelve minutes, and that is not the registered "does not page" outcome, because
the corruption was never shown to have happened.**

`world-v2/src/cart/src/cartstore/ValkeyCartStore.cs` stores each cart as a **hash**: field `cart`
holds the protobuf, read with `HashGetAsync(userId, "cart")` and parsed with `Cart.Parser.ParseFrom`;
any exception in that path is rethrown as `RpcException(FailedPrecondition)`, which is an error
span. The loop ran `SET k 't70-corrupt'`, which would have replaced every hash with a string and
made every subsequent `HGET` throw `WRONGTYPE` — an error on every cart access. **There were zero
errors**, the cart's log shows ordinary `GetCartAsync` / `AddItemAsync` lines throughout, and its
p95 was 5 ms. The only reading consistent with that is that the `EVAL` did nothing, and its output
was sent to `/dev/null`, so the transcript cannot say why.

Two design errors, both mine: the wrong command for the store's data model (`SET` on a hash, where
the registration's own words were *"bytes the cart cannot parse"*, which is a corrupted hash
field), and a suppressed return value on the one command whose success the whole attempt depended
on. This is the `adFailure` mistake of 2026-09-22 again — an attempt underpowered by its own
design and nearly read as a result.

**The re-run verifies before it observes**: it shows a key's type and contents, runs one corrupting
`EVAL` with its return value visible, reads the key back, and only then starts the loop — which
prints the number of keys it corrupted on every iteration.

---

## Addendum, 2026-09-23 — the reasoning above was too strong

The verdict stands: a run whose injection was never shown to have happened is void. But *"the only
reading consistent with [zero errors] is that the `EVAL` did nothing"* was wrong. The second run
(`RESULT.md`) verified its injection and still produced zero errors, and the reason is the load
generator's access pattern — a cart is written and read within milliseconds and never read again,
so a sweep of the keys that exist at any instant almost never touches a cart that will be read.
Zero errors was the expected outcome of the first run whether or not its loop ran. What made the
first run void was not the zero; it was that nothing in its transcript could say what happened.
