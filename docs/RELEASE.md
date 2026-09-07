# Cutting a release (T5.4)

**A tag is a claim that a stranger can get this working from nothing.** T5.4's deliverable is a
*reproducible* MVP, and the only thing that establishes reproducible is doing it — from a clone
that shares no image cache, no volume, no `.env` and no `~/.faultline-anthropic-key` with the
machine that wrote the code.

That has never been done here. `docs/GATES.md` §G5 records why the near-misses do not count: T7.48
rebuilt the world **reusing local images** and said so, and the demo has never been executed from a
cold clone. **A clean-clone rehearsal that reuses anything is a rehearsal of the machine it ran
on.**

---

## What a version number means here

`v0.1` is not "finished". It marks a repository whose demo runs from nothing and whose published
figures name the commands that produced them. **The benchmark is explicitly not settled at v0.1**:
`n` is small, R is 1 everywhere, no confidence interval appears anywhere, and README's *"What these
numbers are not"* says so. Tagging does not change that, and the release notes must not imply
otherwise.

---

## 1. The record is honest before anything is tagged

- [ ] **Every figure in README's results section carries the stamp it came from**, and that stamp
      is one a reader can reach. A results block quoting a superseded `prompt_digest` is the
      commonest way this goes wrong — it happened between dev sweeps 7 and 9, where README kept
      headlining sweep 7 through three stamp moves.
- [ ] `docs/GATES.md` says *"Not declared"* for every gate whose condition has not been
      demonstrated **from a clean clone**. A gate is not passed by the results looking good.
- [ ] `docs/QUEUE.md` has no entry whose digest lock is stale.
- [ ] No discarded run was deleted (ADR-0022 §3.3). Discards are part of the record.

## 2. The checks that run anywhere

```bash
make check          # ruff, mypy, pytest — what CI runs
```

- [ ] Green, on the branch about to be tagged, **and green on `main` after the merge**. Both,
      because a red `main` has twice been discovered only when the next PR's CI was unreadable.

## 3. The clean-clone rehearsal

**In a fresh directory, on a machine with no Faultline state.** If that machine is the development
one, at minimum stop its platform and world first so the fixed ports are free, and expect the image
reuse caveat to apply — say so in the notes rather than claiming a cold run.

```bash
git clone https://github.com/ChandanaRoyalS/faultline.git faultline-release-check
cd faultline-release-check
```

- [ ] `make install` succeeds from the committed lock file. **Not a bare `uv sync`** — that
      resolves the lock but leaves out the `agents` and `embeddings` extras, so `make check`
      passes and `make demo` cannot start. This checklist said `uv sync` until the first
      rehearsal ran it.
- [ ] `make check` passes **before any service is started** — this is what caught a schema defect
      that had been invisible for months, because no database had ever been built from nothing.
- [ ] `make world-up` brings the world up **pulling images rather than reusing local ones**.
      Note the wall-clock; a stranger pays it too.
- [ ] **On a Linux host, prove the world can reach the receiver before starting anything that
      spends money.** Alertmanager posts to `host.docker.internal:8000`; Docker Engine does not
      define that name, so `make world-up` layers `compose/linux-host-gateway.override.yml` on
      Linux to give it one. A default-deny firewall then still drops the packet at the bridge. Run
      the check from inside the world's network, and read the result:

      ```bash
      sudo ufw allow from "$(docker network inspect opentelemetry-demo -f '{{(index .IPAM.Config 0).Subnet}}')" to any port 8000 proto tcp
      docker run --rm --network opentelemetry-demo --add-host host.docker.internal:host-gateway \
        curlimages/curl:8.10.1 -s -o /dev/null -w '%{http_code}\n' --max-time 5 \
        http://host.docker.internal:8000/healthz
      ```

      `200` (with `faultline-ingest` running) is the only pass. `000` with exit 28 is the firewall;
      `could not resolve host` is the shim missing. The first fresh-machine rehearsal (T5.4c) had
      both, found them only after a `make demo` had waited its full thirty-minute correlate ceiling
      for an alert that had been sent and dropped, and recorded a `no-alert` discard against a world
      that had alerted correctly. The rule opens the port to the docker bridge, **not** to the
      internet: `ufw allow 8000` would expose the unauthenticated receiver on the public IP.
- [ ] Wait the documented ~5 minutes. The baseline gate refuses containers younger than 300s, and
      a stranger following README exactly hits that refusal first.
- [ ] `make up`, then `uv run faultline-migrate` — **in that order and not before**: `up` now
      waits for the healthcheck, because on a new volume Postgres runs initdb and the migration
      that used to follow immediately died on `server closed the connection unexpectedly`.
- [ ] **`uv run faultline-seed`.** Skipping it does not weaken a run, it **invalidates** it: the
      leave-one-out filter excludes nothing from an empty corpus, asserts nothing, and the run is
      marked `INVALID` however good its verdict. The first rehearsal lost a correct `bad_config`
      this way.
- [ ] **`uv run faultline-ingest` and `uv run faultline-orchestrate`, each left running in its own
      terminal.** Without the second, `make demo` refuses with `pipeline-down` — correctly, and
      having injected nothing. The rehearsal that added this line hit it twice.
- [ ] `make demo` completes end to end. Costs about $0.60 and needs `~/.faultline-anthropic-key`.
- [ ] `make eval SCENARIO=<id> INTENT=--single-run` produces a scored run directory.
- [ ] `FAULTLINE_API_PASSWORD=... make ui`, then open `/` — the list — and from it the incident from that run; the proposal card is on the page.
- [ ] The deployment rehearsal in [`deploy/README.md`](../deploy/README.md) §1a passes.
- [ ] **Every command above appears in README.** Guarded by
      `tests/test_readme_covers_the_commands.py`, which exists because the front door once named
      one console script of sixteen while publishing figures produced by the other fifteen.

**Record what failed, including what you fixed on the spot.** A rehearsal with no findings is
either the first flawless one in this project's history or one that was not really run; every
rehearsal so far has found something, and the deployment's first one found three defects in
fifteen minutes.

## 4. The tag

```bash
git checkout main && git pull
git tag -a v0.1 -m "Faultline v0.1 — <one line>"
git push origin v0.1
```

- [ ] Annotated (`-a`), not lightweight: a release should carry a message and a tagger date.
- [ ] On `main`, after the merge — never on a branch.
- [ ] The notes name **the stamp, the world generation and the capability digest** the release's
      figures were produced under. Without those three a figure cannot be placed, and a release
      that publishes numbers without them republishes the problem this project exists to solve.

## 5. After

- [ ] `docs/GATES.md` updated — but **only for gates whose condition the rehearsal actually
      demonstrated.** G5 needs both halves: the demo from a clean clone *and* a live deployment.
- [ ] `docs/PLAN.md` records the rehearsal's findings, including anything fixed on the spot.
