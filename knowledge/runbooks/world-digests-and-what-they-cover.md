---
id: world-digests-and-what-they-cover
title: What each digest covers, and what nothing covers
origin: authored
applies_to: [any]
signals: []
actions: []
---

Several hashes in this project answer *is this the same thing as last time*. They cover different
things on purpose, and the boundaries between them are decisions rather than accidents.

## The world

**`compose_digest`** - a hash over the layered compose files, in the order compose loads them,
read from the injector's own file list rather than a hardcoded one so it covers exactly what is
actually layered. It exists because raising one container's memory limit altered every container's
environment and no manifest could show it: **a recording made before that edit and one made after
described different worlds and said they described the same one.**

**`observability_digest`** - a **sibling** of that, not an extension of it, over the files that
decide what a recording can see: the alert rules first of all, the Prometheus configuration, the
log-shipping configuration. **None of these were under any digest at first.** The compose files
name them as mounts and say nothing about what is inside them, so editing a threshold changed every
future recording's alert set and no manifest field moved. Each file also gets its own hash, so a
mismatch can say *which* file changed.

**Why a sibling rather than an extension**: adding a file to a digest's input set changes the value
it computes, so the recorded values stop being reproducible *and* the digest moves for something
that is not a world change - and it does both silently.

**`ffs_stub_source_digest`** - over the stub's build context, **the source and not the image**. An
image id was tried and changed overnight with no source change at all. An image id answers *was
this byte-identical*, which is not the question; this answers *was it built from the same code*,
which is.

**`otel_demo_image_digest`** - the immutable half of a mutable tag, and deliberately the opposite
choice from the stub: prefer content over build artifact, reaching the other conclusion because
the situation is the other way round. Its honest limit is that one image stands as a proxy for a
release rather than as proof of the other fifteen.

## The agent

**`runtime_version`** - the package version plus a digest over every role's system prompt and the
JSON schema of every contract those prompts promise the model. Order-independent, and computed
without shelling out to git, because a product that shells out to describe itself does not work
from a wheel.

**Budget bounds are deliberately outside it.** The stamp answers *which agent is this*; a bound
answers *how much was it allowed to spend*. Both belong in a manifest, and **a figure quoted
without its bounds is as misleading as one quoted without its model.**

**`capability_version`** - the tool surface, the capture set, and a behaviour revision. It covers
none of the above by design. Prompts belong to the stamp. The world belongs to the world digests,
and this one deliberately does not cover the world, **because a second digest over the same thing
would double-fire on every world change and teach a reader to ignore both.**

## The corpus

**`sha256`** over `document_id|section`, and **`body_sha256`** over the bodies as well. The first
answers whether the corpus has the same **shape**; the second whether it says the same **things**.
The second was added rather than folded in, because redefining the first would have made every
recorded manifest incomparable with every future one without saying so.

`holdout_chunks` is reported as a number rather than folded into either, because **a number that
must be zero deserves to be read as a number.**

## What nothing covers

- **Whether a tool works well.** A tool that returns the wrong answer has the same capability
  version as one that returns the right answer.
- **Grafana's provisioning**, and the world's own service source, which the image tag and digest
  stand in for.
- **An image id that churns on a rebuild from unchanged source.** It is recorded and never
  compared: **freezing a field that moves on its own trains a reader to ignore the manifest.**
- **Two conditional compose files** - a Linux host-gateway shim and a CI-only JVM flag - which sit
  outside the digest and are *recorded* anyway, because a manifest silent about a file that
  changed a container's command line is not a complete record of what ran.
- **Observability differences inside one world generation.** A generation is still named by
  `compose_digest` alone, so two worlds differing only in what the agent can observe are one
  generation by name. Closed for pooling, open for naming.

## Two rules that decide all of this

**Absence is reported as `unverifiable`, never as unchanged.** A check that answers *no difference*
to a question it cannot see is worse than one that answers *I cannot see it*.

**A field may be backfilled if it reads what a recording contains, and may not if it asserts
something outside it.** An observability digest is decisively the second kind - a recording does
not contain the alert rules - so its absence means unknown.

The same principle outside the digests: the dependency-graph drift guard compares the edge set and
excludes the call counts, because those move on every capture with no change to the world, and **a
field that produces false positives and cannot produce true ones is worse than absent.**
