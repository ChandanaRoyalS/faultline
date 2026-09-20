# Deploying Faultline (T5.5)

T5.5's task text: *"Deploy the MVP: the same images CI builds, running continuously on a single
small VM — demo environment plus platform, TLS in front, basic auth on the UI."* Its deliverable:
*"Live instance at a stable URL + documented deploy procedure."*

**What goes up is the MVP, whole.** The OpenTelemetry demo world under load, its telemetry stack,
the platform, and the orchestrator that investigates what the world does — behind one hostname, one
certificate and one credential. Phase 5 opens by defining the MVP as *"a complete story: world,
investigation, grounding, evaluation"*, and a deployment missing the middle two is a deployment of
something else.

**This replaced a smaller deployment that served only a snapshot.** Three containers, no world, no
orchestrator, \$5.49/month. It was defensible on its own terms and it was not either of the two
options T5.5 offers — the spec's size note is a choice between *sizes* (the full stack, or platform
plus a trimmed demo profile), not a choice about whether a demo environment is present. §5 keeps
the snapshot-only shape documented, because it is still the right answer for some purposes.

---

## 1. What it costs

Sized for the spec's own figure: *"the full stack (demo world + telemetry + platform) wants ~4 vCPU
/ 16 GB — the OTel demo alone needs ~6 GB."*

| | vCPU / RAM | monthly | notes |
|---|---|---|---|
| **IONOS VPS XL+** | 8 / 16 GB | **\$44, month-to-month** | 480 GB disk, US. **What is actually running** (T5.4c) — see below |
| **Hetzner CX43** | 8 / 16 GB | **€15.99** | 160 GB disk, 20 TB traffic. **What this is sized for**, sold only in Germany and Finland |
| Hetzner CX33 | 4 / 8 GB | €8.49 | §5's platform-only shape, or a trimmed demo profile |
| Hetzner CX23 | 2 / 4 GB | €5.49 | §5's snapshot-only shape. Will not hold the world |
| DigitalOcean General Purpose | 4 / 16 GB | ~\$126 | same shape, eight times the price |
| Hetzner CCX33 (dedicated vCPU) | 8 / 32 GB | €138.49 | only if the shared vCPUs prove too noisy |

Add **€0.50–1/month** for the IPv4 address on Hetzner, a domain (~\$10–15/year — Caddy needs a real
hostname to get a certificate for, so a bare IP does not work), and **the model spend of whatever
the orchestrator investigates**, which is the line item this shape has and the previous one did not.
At the measured \$0.74/run mean of the 2026-09-06 R=3 sweep, a world left alerting on its own is
open-ended; §3.8 caps it.

**Prices are from 2026-09-06 and are not automatically current.** Hetzner raised every cloud plan on
15 June 2026 — CX23 went €3.99 → €5.49, CX43 €11.99 → €15.99, and the CPX and CCX lines by up to
176%. This table's previous version quoted **\$6.49 for a CX23**, which was the *old CX33* price
attached to the wrong row: stale in the currency, the plan and the figure at once. Re-check before
committing.

**What is running is not the row it was sized for.** Hetzner's CX line is not sold in the US and its
account verification stalled on a payment method that was not the buyer's own, so on 2026-09-07 the
instance went to IONOS at **\$44/month with no term**, 2.75× the CX43 for the same shape. That is a
month-to-month decision: the contract ends on day 30 unless renewed, and moving to a CX43 is
`deploy/README.md` §3 run again from §3.1 against a new IP. **The \$11/month IONOS figure that was
briefly quoted was a three-month introductory rate on a twelve-month contract (\$429 in total)**,
caught at checkout; the same lesson as the row above, one vendor over.

**Day 30 is 2026-10-07.** The IONOS contract renews monthly unless cancelled; the decision - keep,
move to a CX43, or take the instance down - is due before then, and the rehearsal record in
`docs/PLAN.md` T5.4c says which findings depend on the platform if it moves.

---

## 1a. Rehearse it first

**Every file in this directory was written and committed without once being started.** No Docker
daemon was available where they were authored. That is the exact shape of defect this project has
now found fifteen times — built, green, never run — and the response is to make running it free
rather than to assert it is fine.

`compose.rehearsal.yml` moves the platform to :8001, stops Caddy, and stops the orchestrator — so a
rehearsal collides with neither `make ui` nor a development platform, and **cannot spend money**.
On any machine with Docker, from a clone:

```bash
cd faultline/deploy
cp env.example .env
$EDITOR .env
docker network create --internal faultline-deploy-net
docker compose config | grep FAULTLINE_API_PASSWORD_HASH     # must print a hash - see §3.1
docker compose -f compose.yml -f compose.rehearsal.yml up -d
docker compose -f compose.yml -f compose.rehearsal.yml exec faultline faultline-migrate
```

`docker network create` first, because `compose.yml` declares the network `external` — the world
joins it too, and neither project may own its lifetime (see the note in that file). Without it
`up` stops on *"network faultline-deploy-net declared as external, but could not be found"*. This
line was missing from the first version of this section and was found by reading the new
`compose.yml` against it, which is the second-cheapest way to find it; the cheapest is running it.

Filling in `.env` for a rehearsal: `SITE_ADDRESS` can be anything, since Caddy is not running.
`FAULTLINE_IMAGE` must be a real sha from the registry — that is half of what a rehearsal is for.
`ANTHROPIC_API_KEY` needs any non-empty placeholder: compose interpolates `${VAR:?...}` while
*reading* the file, before it decides how many replicas to start, so a mandatory variable is
mandatory even for a container scaled to zero. **Do not put your real key in it.** The one
container that would read it is not running, and a rehearsal that required a live credential is a
rehearsal people skip.

On an Apple Silicon Mac the pull is a `linux/amd64` image — CI builds on `ubuntu-latest` — so it
runs under emulation and is noticeably slow. That is a rehearsal annoyance only; the VM is x86-64
and runs it natively.

Then:

```bash
curl -sS localhost:8001/healthz                                             # {"status":"ok"}
curl -sS -o /dev/null -w '%{http_code}\n' localhost:8001/api/v1/incidents   # 401
curl -sS -u faultline:$FAULTLINE_API_PASSWORD localhost:8001/api/v1/incidents
```

The last returns an empty list until §3.5 loads a snapshot or the world produces one — that is
correct, and it is a different answer from a 404, which would mean the read surface never mounted.

Tear down with `docker compose -f compose.yml -f compose.rehearsal.yml down -v`, then
`docker network rm faultline-deploy-net` — `down` does not remove an external network, by design.
That `-v` is safe **because the deployment is compose project `faultline-deploy`**, a different
project from the repository's own `faultline` — see the note at the top of `compose.yml` for what
happened the first time it was not.

**The first rehearsal found a real defect, which is the argument for this section.** `compose.yml`
declared `name: faultline`, the same project compose derives for the repository's own
`docker-compose.yml`, so it attached to the running development Postgres and pointed the
deployment's DSN at the developer's database. It failed safe by luck rather than design — an
existing volume keeps its original password — and against an empty one it would have handed the
deployment live development data. Cost of finding it here: four minutes. Cost of finding it on a
public VM: a published database.

**What a rehearsal covers:** the image pull, the DSN, the credential refusal, the migration, and
the read surface. **What it cannot:** the certificate, the DNS record, the firewall, and the world.
Those stay first-run risks on the VM, and §3.6 is where they are checked.

---

## 2. Prerequisites

- A VM with **8 vCPU / 16 GB** (see §1), Docker and the compose plugin.
- A domain or subdomain with an **A record pointing at the VM's IP**, resolving before you start —
  Caddy asks Let's Encrypt for a certificate on the first request and the challenge fails if DNS
  has not propagated.
- The repository cloned on the VM. **Only for its compose files and the world clone** — the image
  itself comes from the registry, never from this checkout.
- An `ANTHROPIC_API_KEY`. The orchestrator holds it and nothing else on the VM does.

---

## 3. The procedure

### 3.1 Configure

```bash
cd faultline/deploy
cp env.example .env
$EDITOR .env
```

Every variable is mandatory except the Slack webhook. `compose.yml` uses `${VAR:?...}` so a missing
one stops the deployment with a named error instead of starting something half-configured.

Two need generating rather than choosing:

```bash
openssl rand -base64 24                                          # POSTGRES_PASSWORD
openssl rand -base64 18                                          # FAULTLINE_API_PASSWORD
docker run --rm caddy:2-alpine caddy hash-password --plaintext '<that password>'
```

The third is `FAULTLINE_API_PASSWORD_HASH` — the same credential in the form Caddy takes. Two
things check it and they need different forms: Faultline checks the plaintext itself in
`faultline.api.auth`, and Caddy guards Grafana and Jaeger, which ship with no authentication of
their own.

**Paste that hash inside single quotes.** A bcrypt hash is mostly dollar signs, and Compose's
dotenv parser expands `$VAR` in an unquoted value — so `$2a$14$xyz…` arrives at Caddy with pieces
missing, and every request to `/grafana` returns 401 with a correct password. The failure is
indistinguishable from a typo, so check rather than assume:

```bash
docker compose config | grep FAULTLINE_API_PASSWORD_HASH
```

`FAULTLINE_IMAGE` names a commit:
`ghcr.io/chandanaroyals/faultline:<40-character sha>`. **Never `:latest`** — a moving tag means the
VM changes what it runs on the next `up -d`, and §3.7's rollback stops having anything to point at.

`FAULTLINE_API_PASSWORD` is not optional in a different sense either: `faultline.api.app.assemble`
**raises before it connects to the database** if it is unset. The read surface mounts behind a
credential or it does not mount.

**Three more since T6.2 (2026-09-11), for the executor container** — the action plane, ADR-0038:

```bash
openssl rand -hex 32                                             # FAULTLINE_EXECUTOR_TOKEN_KEY
stat -c %g /var/run/docker.sock                                  # DOCKER_SOCKET_GID
echo $HOME/faultline                                             # FAULTLINE_CHECKOUT, absolute, no trailing slash
```

The key signs approval tokens and has the standing of the API password. The group id lets the
executor container reach the Docker socket as `appuser` instead of as root. The checkout path is
mounted into the container **at the same path**, so the world's compose files and the injector's
override files resolve inside exactly as they do outside. `compose.yml` refuses to start without
any of the three. The same key is passed to the `faultline` container too, because **T6.3's approve
button mints the token** and the web process is where the button is - one secret, two containers.

**One file beside `.env`, since T6.8 (2026-09-20): the receiver's credential as Alertmanager
reads it.** `POST /api/v1/alerts` demands the API pair on this deployment
(`FAULTLINE_INGEST_REQUIRE_CREDENTIAL` in `compose.yml`), and Alertmanager sends it from a file it
mounts, because its config is committed and expands no variables:

```bash
grep '^FAULTLINE_API_PASSWORD=' .env | cut -d= -f2- | tr -d "\"'" > alertmanager.password
chmod 600 alertmanager.password
wc -c alertmanager.password                                      # the password's length + 1, never 0
```

Gitignored like `.env`. Without it the alertmanager container refuses to start (a missing mount
source), which is the right failure: a world that cannot alert is visible, a receiver answering 401
to every delivery is not. If the API password is ever rotated, this file is rotated with it.

**The kill switch is off since T6.3** (`FAULTLINE_EXECUTOR_KILL_SWITCH: "0"`). Until 2026-09-12 it
was on and nothing could mint; now an approval on the screen executes an allowlisted action against
this VM's world. §3.11 is the drill for turning it back on.

### 3.2 Close the ports the world opens

**Not optional, and it comes before anything is started.**

The OpenTelemetry demo's own compose files publish a dozen host ports — 8080, 3000, 3100, 9090,
9093 and more, and this repository's `compose/telemetry.yml` adds 3200 (Tempo, T6.1). A compose overlay can add a published port and cannot remove one, so
`compose.world.yml` does not try. On a public VM every one of those is reachable on the IP,
which means Grafana, Prometheus and Alertmanager are on the internet with no credential and Caddy
in front of nothing.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Docker publishes ports by writing DOCKER-USER iptables rules that bypass ufw's INPUT chain on some
configurations. Verify from **another machine** rather than trusting the status output:

```bash
curl -sS --max-time 5 http://<the VM's IP>:3000/ ; echo "exit $?"   # must not return a page
```

An exit of 28 (timeout) or 7 (refused) is the answer you want. A Grafana login page is a finding,
and the fix is `iptables -I DOCKER-USER -p tcp --dport 3000 -j DROP` per port, or binding the
demo's publishes to `127.0.0.1` in a further overlay.

### 3.3 The network, then the platform

```bash
cd faultline/deploy
docker network create --internal faultline-deploy-net    # once; fails loudly if it exists
docker compose up -d --wait
docker compose exec faultline faultline-migrate
docker compose exec faultline faultline-seed --import-acceptances
```

**`--internal`, since T6.8 (2026-09-20).** Nothing on the platform's network has a route off the
host. The one container that needs one - the orchestrator, for the model provider and Slack -
reaches them through `egress`, a forward proxy on a second network (`faultline-deploy-egress`,
compose-managed) whose access list is exactly two hostnames (`deploy/squid.conf`); Caddy joins that
second network too, for ACME and for its published ports. A deployment created before that date
has an ordinary bridge under this name and §3.12 is the window that replaces it.

`--wait` and not bare `up -d`: on a new volume Postgres runs initdb, so the port is bound before
the server is listening and the migration that used to follow immediately died on `server closed
the connection unexpectedly`. Found by T5.4's first clean-clone rehearsal.

**`faultline-seed` is not optional.** The leave-one-out filter (ADR-0008) excludes nothing from an
empty corpus, asserts nothing, and marks the run `INVALID` however good its verdict. T5.4's first
rehearsal lost a correct `bad_config` exactly this way.

**`--import-acceptances`, since T6.5's postmortems (2026-09-18).** Ten accepted postmortems are in
the dev tree and the seeder admits a postmortem only when the ledger holds a row for its exact
words. A fresh deployment's `postmortem_acceptances` is empty, so without the flag the seed refuses
all ten and exits 2 - which is the gate working, on a database that has not heard the decision. The
flag replicates the committed ledger (`evals/scenarios/artifacts/dev/ACCEPTANCES.json`) into the
table first, verbatim: the rows keep the caller and the date of the original acceptance, so the
deployment's ledger says who decided and when rather than that the deployment did. Idempotent;
re-running the procedure imports nothing the second time.

### 3.4 The world

Two commands. The first is the repository's own target and does everything a development machine
does — clones the demo at `v1.2.1` (ADR-0026), builds the feature-flag stub, layers the override and
the telemetry stack, and pushes the shop-health dashboard into Grafana. The second re-applies the
same three files with the deploy overlay as a fourth, which is idempotent: it recreates Alertmanager
with the deploy config and attaches four services to the platform's network, and touches nothing
else.

```bash
cd ~/faultline
make world-up
cd world
docker compose \
  -f docker-compose.yml \
  -f ../compose/world-arm64.override.yml \
  -f ../compose/telemetry.yml \
  -f ../deploy/compose.world.yml \
  up -d --no-build
cd ~/faultline && uv run python scripts/provision_dashboards.py --self-metrics-url http://prometheus-self:9090
```

The last line is T6.6 / Q73's: `make world-up` pushed the dashboards with the *development*
address for the platform's own Prometheus (`host.docker.internal:9091`, which resolves to nothing
on the VM), and this re-pushes the `faultline-self-metrics` datasource with the container's name
on the shared network. Idempotent, like the dashboards. `compose.world.yml` puts Grafana on that
network for exactly this read; `prometheus-self` itself is in `compose.yml` and came up in §3.3.

**`world-arm64.override.yml` stays, and the first version of this section said to drop it.** Its
name is misleading. Kafka's heap cap and `MALLOC_ARENA_MAX` fix a glibc arena problem on any Linux
(T7.27); redis-cart's eviction policy is not about the CPU (T7.19); a dozen memory limits were
raised because containers sat at 95%+ idle and tripped the baseline gate; and `featureflagservice`
is the stub every recorded scenario ran against (ADR-0005, ADR-0006). **It is also one of the three
files the world generation is hashed from.** Without it, the VM runs a world that is not
`f5bd108f4f70`, wearing the same image tag — the exact defect `compose_digest` exists to make
visible. The deploy overlay is a fourth layer outside that hash, so applying it changes nothing a
manifest would record.

Expect ~5 minutes before the world is worth looking at, and remember the baseline gate refuses
containers younger than 300s.

### 3.5 Optionally, past investigations

The deployment now produces its own incidents, so this is no longer required — but a URL that
opens on an empty list is a poor first impression, and the incidents already in `evals/runs/` are
better than whatever the world happens to be doing at that moment.

**Why a database dump rather than something in the repository.** The committed run directories
carry the manifest and the verdict, but **not the trajectory** — no steps, no tool calls, no
`request` fields. The timeline and every citation deep-link are built from
`trajectory_tool_calls.request`, read from Postgres. So the two things that make this screen worth
deploying are exactly the two a repo-only loader cannot reconstruct.

```bash
make deploy-snapshot            # on the machine with the incidents; writes deploy/snapshot.sql.gz
scp deploy/snapshot.sql.gz you@your-vm:/tmp/
ssh you@your-vm 'cd faultline/deploy && gunzip -c /tmp/snapshot.sql.gz | docker compose exec -T postgres psql -U faultline faultline'
```

**The snapshot carries the monitored world's telemetry** — every log line an agent quoted and every
query it ran. It is a demo world and not anyone's production data, but it is the reason the
credential in §3.1 exists, and the reason `deploy/snapshot.sql*` is gitignored.

### 3.6 Check it

```bash
curl -sS https://$SITE_ADDRESS/healthz                                              # {"status":"ok"}
curl -sS -o /dev/null -w '%{http_code}\n' https://$SITE_ADDRESS/api/v1/incidents    # 401
curl -sS -o /dev/null -w '%{http_code}\n' https://$SITE_ADDRESS/api/v1/alerts       # 404
curl -sS -o /dev/null -w '%{http_code}\n' https://$SITE_ADDRESS/grafana/            # 401
curl -sS -o /dev/null -w '%{http_code}\n' https://$SITE_ADDRESS/metrics             # 404
docker compose exec executor curl -fsS localhost:8100/healthz                      # {"status":"ok","kill_switch":true}
curl -sS -u faultline:$FAULTLINE_API_PASSWORD https://$SITE_ADDRESS/api/v1/incidents | head -c 200
```

**Lines two to five are the checks that matter** — they are the ones that fail open. The
401s mean the credential is doing its job; the **404 on `/api/v1/alerts` means the receiver is not
on the internet**, which is what stops a stranger from opening incidents that bill your key; the
**404 on `/metrics` means the platform's own spend and outcome counters are not either** (T6.6 —
that surface has no credential of its own, because its reader is Prometheus on the compose network).

Then open `https://$SITE_ADDRESS/` in a browser — the credential prompt, then the incident list —
and pick one, or take an `incident_id` from the last line and open
`https://$SITE_ADDRESS/ui/incidents/<id>` directly. On the incident, read the **Proposed remediation**
card down to its buttons (*approve and execute*, *reject* - since T6.3; until 2026-09-20 this
sentence still said the card ended *"not executed - no executor exists"*), and **click a
citation** — it should land you in Grafana's explore view with the agent's own query already
filled in. That link was broken until T5.1's fix and clicking it is the only way to know.

**Then prove the deployment investigates, not only remembers.** The orchestrator runs
`faultline-investigate` itself 90 seconds after an incident opens (`FAULTLINE_ORCH_INVESTIGATE=1`
in `compose.yml`; nowhere else, because on a development machine the harness does it). The first
live deployment did not have this and its first real incident sat in `triaging` with *"not yet
investigated"* on the public page (T5.5c). To see it work, inject one fault against the world from
the VM's checkout and watch the state move:

```bash
cd ~/faultline && uv run faultline-inject start cart-redis-misconfig
# ~4 minutes later - the alert, the settle window, the first dispatch:
cd deploy && docker compose exec -T postgres psql -U faultline faultline -tAc "select id, state from incidents order by opened_at desc limit 1"
docker compose logs orchestrator --since 10m | grep -E "investigating|states:"
cd ~/faultline && uv run faultline-inject stop --all        # the world does not put itself back
```

**Read the `investigating` line and the trajectory row, not the state.** The incident reads
`triaging` for the whole of a healthy run - the runner writes its state transitions after
`faultline-investigate` returns (Q78) - so `triaging` at four minutes is *not* the defect this
paragraph used to call it. The defect is no `investigating … (attempt 1)` line ninety seconds
after the incident opened, or no `states:` line within about five minutes of that. A row in
`trajectories` with `outcome` NULL is a run in progress (or, past twenty minutes, one that was
killed - the runner names those `orphaned` on its next poll). About \$0.70 of model spend, once.

**The `investigating` line in that grep had never been printed before T6.6.** It is `log.info`,
and nothing in the platform configured logging until piece 4, so the root logger sat at `WARNING`
and dropped it in every deployment that ran this check — the grep matched `states:` alone. It
comes out now, as one JSON object per line with `"component": "orchestrator"`.

**Then prove the deployment can watch itself** (T6.6). Each daemon prints one line at start for
each surface, on stdout, so an operator who expected traces and sees none has one line to read:

```bash
docker compose logs faultline orchestrator --since 1h | grep -E "tracing:|metrics:"
# tracing: exporting to http://tempo:4317          (all three containers; `otelcol:4317` before Q77, 2026-09-19)
# metrics: /metrics mounted                        (faultline)
docker compose exec faultline python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/metrics').read()[:300].decode())"
```

`tracing: exporting` missing means the image predates T6.6 piece 6 or the endpoint is unset;
`metrics: prometheus_client not installed` means the image was built without the `observability`
extra. After the injected fault above, the incident page carries a `trace …` link in its header
that opens the investigation's waterfall in Grafana with the run's own range set. The dashboard
`/grafana/d/faultline-self` shows the same numbers, read from the platform's own Prometheus
(`prometheus-self`, §3.4's last line) - never from the world's, whose config is digest-locked and
whose queries the agent can see (Q73). `up{job="faultline"}` in Explore on the
`Faultline self-metrics` datasource is 1 when the scrape is reaching the API.

**An empty Tempo is not yet a missing trace - wait ten minutes before debugging it** (Q76). A
trace leaves Tempo's ingester about 2.5 minutes after it arrives and is then reachable only
through a block index rewritten every ten minutes, so between the two it answers 404 by id and
nothing by search while Jaeger (`/jaeger/ui`, same collector) already shows it. On 2026-09-18 the
first `action.execute` span spent twenty minutes there. To see that span for yourself after the
injected fault above: reject the abstention if there is one (`POST /api/v1/incidents/<id>/reject`
with a reason), then `…/acknowledge` if the incident is critical and `…/approve`; the token is
minted and presented inside the API process and never reaches you. The world does not recover from
a `restart_service` while the override is applied - `stop --all` is still yours to run.

### 3.6a Changing the Caddyfile

`Caddyfile` is bind-mounted **as a single file**, and `git pull` replaces a changed file with a new
inode rather than editing it in place — so the container keeps seeing the old one, and `caddy reload`
reloads exactly that. Found on 2026-09-07 when a fix reloaded cleanly and changed nothing. After any
change to the Caddyfile:

```bash
docker compose up -d --force-recreate caddy
docker compose exec caddy grep -c header_up /etc/caddy/Caddyfile     # confirm the container sees the new file
```

Two seconds of downtime; the certificate lives in a volume and survives.

### 3.7 Rolling back

T5.5 names *"a documented deploy-and-rollback procedure"*. This is the second half.

**The platform rolls back by naming a different commit.** That is the entire reason
`FAULTLINE_IMAGE` is a mandatory sha rather than `:latest`:

```bash
cd faultline/deploy
$EDITOR .env                      # FAULTLINE_IMAGE=ghcr.io/chandanaroyals/faultline:<previous sha>
docker compose up -d --wait       # pulls the old image, recreates faultline and orchestrator
docker compose ps                 # both running, from the tag you named
curl -sS https://$SITE_ADDRESS/healthz
```

Seconds, and no rebuild, because the previous image is still in the registry and probably still in
the VM's local cache.

**`--wait` means serving, not started — since the rollback rehearsal.** The first time this
procedure was run, `up -d --wait` returned and the very next `curl` got *connection reset by peer*:
`faultline` had no healthcheck, so compose considered it ready the moment its process existed. It
has one now, so `--wait` blocks until `/healthz` answers from inside the container, and Caddy does
not send a visitor to it until then either. If `--wait` ever returns and the curl still fails, the
healthcheck is what to look at first.

**The schema does not roll back with it, and that is the constraint to plan around.** Alembic
migrations here are forward-only; `faultline-migrate` has no `downgrade` path exercised by any
test. So a rollback across a migration boundary means the old code meets a newer schema. Additive
migrations — a new table, a nullable column — are safe. A migration that drops or renames anything
is not, and the honest procedure for one is:

```bash
cd ~/faultline/deploy
docker compose stop faultline orchestrator executor prometheus-self   # the writers and readers; NOT `down`
gunzip -c ~/snapshots/faultline-<stamp>.sql.gz \
  | docker compose exec -T postgres psql -U faultline -v ON_ERROR_STOP=1 -q faultline
$EDITOR .env                                                          # the previous sha, if rolling back
docker compose up -d --wait
docker compose exec faultline faultline-migrate                       # says `schema at NNNN`; applies nothing
docker compose exec faultline curl -fsS localhost:8000/healthz        # not from the host: 8000 is not published
```

**Drilled 2026-09-19 21:23 UTC, over the live database** (T6.7 piece 2; the evidence note is
`docs/evidence/t6.7-reliability/2026-09-19-restore-drill.md`). Snapshot 979 KB, seventeen tables,
1,155 rows. `stop` took 10.3 s (the orchestrator's graceful exit is the ten seconds); the restore
took **0.48 s** with `ON_ERROR_STOP` and exit 0; `up -d --wait` 7.1 s; **18 seconds from the first
command to every container healthy**, `schema at 0010`, and every table at exactly the count it
had before. Caddy stays up throughout and answers 502 for the platform's paths while the readers
are stopped; the world is untouched.

**What the drill found: this procedure used to begin with `docker compose down`**, which removes
the Postgres container along with the rest, so its second line - `exec` into Postgres - could
never have run. The runbook had never been executed and was wrong in its first word. `stop`, and
only the services that read or write the database, is the shape that works, and it is what the
block above now says. `-v ON_ERROR_STOP=1` is there so that a restore that fails half-way exits
non-zero instead of leaving a database that is partly the snapshot; `-q` so the log is the errors.

**Where snapshots live, and when they are taken.** `~/snapshots/` on the VM, dated to the minute
in UTC, **nightly by `deploy/snapshot.sh` from cron** (T6.7) with a seven-day window:

```bash
mkdir -p ~/snapshots
( crontab -l 2>/dev/null; echo '17 3 * * * /home/deploy/faultline/deploy/snapshot.sh >> /home/deploy/snapshots/cron.log 2>&1' ) | crontab -
~/faultline/deploy/snapshot.sh            # once by hand, to see it work
```

The script refuses to keep a dump under 10 KB (a half-failed dump restores to nothing) and prints
one line per run. **Still take one by hand before a deploy that carries a destructive migration**
- the nightly one is up to a day old - with the same script, which is the same command. Before
this, the only snapshot lived in `/tmp` and would not have survived the reboot the VM keeps asking
for. The snapshots are on the same disk as the database: this is a backup against a bad migration
or a bad deploy, not against the disk (§4).

**The world does not roll back at all**, and does not need to: it is pinned at `v1.2.1` and nothing
here changes it. If it wedges, `docker compose ... down && ... up -d --no-build` from §3.4 is the
whole recovery, and the platform keeps serving the record while it happens.

### 3.8 The uptime check

T5.5 names *"an uptime check"* as a deliverable, and `.github/workflows/uptime.yml` is it — a
scheduled workflow that polls `https://$SITE_ADDRESS/healthz` and fails loudly when it stops
answering.

**In the repository rather than in a monitoring vendor's account**, for three reasons: it is a
committed, reviewable artifact rather than a setting in somebody's dashboard; it costs nothing; and
a reader of this repository can see that the claim "there is an uptime check" is true without being
given a login. It runs from GitHub's infrastructure, so it is genuinely off the box — a check
running on the VM cannot detect the VM being down.

Set it up by adding one repository variable:

```bash
gh variable set FAULTLINE_SITE_ADDRESS --body 'faultline.example.com'
```

Unset, the workflow skips rather than failing, so this file is committable before the VM exists.
The workflow's own comments carry the rest.

**What it does not do:** page anyone. A failed scheduled workflow emails the repository owner,
which is the correct amount of alerting for a portfolio deployment and would be wrong for anything
carrying traffic.

### 3.9 What is running, and what ran before it

§3.7 rolls back by naming *"the previous sha"*, and until this section nothing wrote that sha down:
it lived in the VM's `.env`, which is gitignored and overwritten by every forward deploy, and in the
VM's image cache, which is not a record. Found by doing a forward deploy (2026-09-07) and realising
that the thing §3.7 needs as its argument existed only as the first seven characters in somebody's
memory. **Every forward deploy adds a row here, in the same PR that changes what CI builds.** The
times are the image's CI build time (`docker images --format '{{.CreatedAt}}'`); deploy times were not
recorded before this table existed and are not invented for it.

**What a sha in this table promises, from 2026-09-18 (Q75):** every CI job on that commit passed -
lint, types, unit tests *and* the integration job that seeds the corpus and holds the retrieval
gate - because `docker` now `needs` both. Before that date the `docker` job ran on any push to
`main`, so every row below was published whether or not the rest of the workflow was green, and
`a1a6c412` was preceded by twenty-five commits whose images existed while their integration job
was red. A red integration job now means no image, and a deploy waits for the fix.

| image sha (`FAULTLINE_IMAGE`) | built (UTC) | what it carried | status |
|---|---|---|---|
| `a07344d6bfa6736b3953f1a568a0847a1590483a` | 2026-09-19 (CI, #389) | **T6.7, the reliability pass**: the timeout audit's three fixes (model calls 180 s and actually wired, no SDK retries inside `Resilient`, the approve route outliving the executor's command, `statement_timeout` on the read surface); the trajectory row written at a run's first second and the orphan reconciler in the orchestrator's poll; the breakers - per model, across runs, per backend - with exit code 6 and the `provider_unavailable` outcome; **the deployment's $5/24h spend ceiling** (`FAULTLINE_ORCH_MAX_USD_PER_DAY`, in `compose.yml`). Deployed 2026-09-19 23:47 UTC by §3.7's shape (`compose.yml` pulled first; no migration, `schema at 0010`), `--wait` 18.9 s. **On the new orchestrator's first poll, 23:48:12: `orphaned 1 trajectory row(s) from killed investigations: 7d230673…`** - the crash drill's killed run, named by the deployment itself. Found on the same read: the daemons' startup `print`s (the ceiling, the settle window, `metrics: … mounted`) had never reached the log on any deployment - stdout is block-buffered without a tty - fixed by `PYTHONUNBUFFERED=1` on the three daemons in `compose.yml`, applied after this row was written | **running** |
| `d89876ccb8ce681ce8b880556a1acf39237cc603` | 2026-09-18 (CI, #377) | **The first image the workflow could not have published red** (Q75: `docker` needs `checks` and `integration`). Q74: the executor configures logs and tracing and gets the collector's endpoint - the fourth daemon exporting; Q72: `faultline-sweep` and `faultline-eval-db orphans` close a killed run's trajectory row as `orphaned`; Q37, Q63, Q65 closed as decisions. Deployed 2026-09-18 11:38 UTC by §3.7's shape - `compose.yml` pulled first for the executor's endpoint line, no migration (`schema at 0010` before and after), `--wait` 18.7 s. Read back within the minute: `executor-1 | tracing: exporting to http://otelcol:4317`, uvicorn's startup lines as JSON with `"component": "executor"`, `0` sessions idle in transaction, and **no trajectory row on the VM with a NULL outcome** - the deployment has never had a killed run to reconcile. **12:15 UTC: the first action the deployment ever executed on its world** (`restart_service → cartservice`, approved through the API after an operator rejection; the `action.execute` span in Jaeger at once and in Tempo twenty minutes later - Q76; evidence: *the first action on the deployment*) | previous - §3.7's argument |
| `adbb136f2c88b3d91c1687e72dc1b7ba672d0636` | 2026-09-18 (CI, #374) | `faultline.pgread`: every Postgres read ends its own transaction, so the platform no longer holds share locks against its own migrations between reads - the defect the row below found. Deployed 2026-09-18 ~10:50 UTC by §3.7's shape (no migration: `schema at 0010` before and after); **thirty seconds after start, with `/metrics` scraped and the queue polled, `pg_stat_activity` showed 0 sessions idle in transaction** - the number that was 2 for the whole life of the previous image | superseded |
| `a1a6c4123d50e03002cbd8bad394b546f16e787e` | 2026-09-18 09:44:53 | T6.6 self-observability, whole: spans at six seams exporting to the world's collector, `/metrics` with `prometheus-self` scraping it, JSON logs, the self dashboard and its datasource, `/metrics` closed at the edge; T6.5's ten postmortems and the committed acceptance ledger (`--import-acceptances`); migrations 0008-0010 (0009 renames a column - snapshot taken first, §3.7). **Deployed 2026-09-18 ~10:40 UTC, and the migration waited 46 minutes for a lock** the platform itself held: the API's `/metrics` snapshot and the orchestrator's `queued()` poll each sat idle in transaction since their process started. Released by terminating both backends; fixed in the next image (`faultline.pgread`). The first image after the T6.6 recheck; CI was red on the integration job for every commit before it (Q67, Q75) | superseded |
| `2e097dc9bd6085f6119646ae74175a64ffab508e` | 2026-09-11 (CI, #262) | T6.3's last piece - the rejection loop's driver. **Deployed without a row here**, found on 2026-09-18 when the next deploy read what was running; the date is the image's, the deploy time was not recorded. The rule at the top of this table was skipped once, and this row is the correction, not a replacement of the rule | superseded |
| `7f2edff48b13ae7924ca6a9035cd1db34e2e4f20` | 2026-09-11 (CI, #255) | T6.2: the executor container — the only one with the Docker socket, joining the docker group by id, **kill switch on** — plus the repair replay's write-up and the running-state drift fix. Deployed 2026-09-11 22:07 UTC with three new `.env` values (§3.1); prediction 9 measured against it: `/healthz` reports `kill_switch: true`, a token is refused as `kill_switch` and recorded in the VM's `action_audit`, the orchestrator unaffected | superseded |
| `4dfcc53e0fc6877ab3c5404a2aafc4012ac12753` | 2026-09-11 04:46 | T6.1: the trace analyst and Tempo — the VM's first world with traces; the orchestrator's terminal-state guard (ADR-0016 Addendum 3); dev sweep 12's write-up; T4.5's Actions work (#247–#249). Deployed 2026-09-11 ~05:15 UTC, after the reboot below, with the world re-applied from the current three files | superseded |
| `28fcaf7f3bd14eeceeffe8d0ce7c8063c14fca93` | 2026-09-07 22:57 | T5.6's audit: the proposal card and open questions on the incident screen, `GET /ui/incidents` and the `/` redirect, the demo's `remediation_class` fix; T5.7's visibility reporting; sweep 11's table | superseded |
| `b310bd9f2b1adfb69cb3016a60371314421dca0e` | 2026-09-07 08:43 | the image the video's part 3 shows: the first incident the deployment opened and investigated itself (T5.5c) | superseded |
| `eb486066f99dadd30cad3ea9c1beed2d1a8abdef` | 2026-09-07 08:16 | T5.5c's forward deploys while findings twenty-three to thirty-one were being closed on the machine the procedure was written for | superseded |
| `691caef6ebf1b8aa3a3d68d5f729dd20b0060620` | 2026-09-07 07:25 | ″ | superseded |
| `4ff5e0f170e1a021afd335da51fc7b3607bdc852` | 2026-09-07 07:12 | ″ | superseded |
| `25ad0a08f4295098bc682ad115d2c996977b7c5c` | 2026-09-07 06:01 | the first image ever deployed: the snapshot-only deployment, before the orchestrator ran investigations (T5.5b/c) | superseded |

All thirteen are still in the registry and in the VM's cache, so any row is a §3.7 target in seconds.
The schema constraint in §3.7 applies across rows: no migration between `25ad0a08` and `7f2edff4`
dropped or renamed anything (0005 adds `action_audit`; nothing is dropped) (`faultline-migrate`
reported `schema at 0004` before and after the 2026-09-11 deploy). **`a1a6c412` carried 0009, which
renames `trajectory_retrievals.exclude_origin` to `exclude_origins` and changes its type**, so a
rollback from it to any earlier row crosses a destructive boundary: restore
`/tmp/snapshot-before-deploy-2026-09-18.sql.gz` first, per §3.7.

**A migration that hangs is waiting for a lock, and the holder is probably this platform.** On
2026-09-18 `faultline-migrate` sat 46 minutes on `ALTER TABLE trajectories`; `pg_stat_activity`
showed the API's and the orchestrator's connections *idle in transaction* since they started -
every read opened a transaction and nothing closed it. Read paths now roll back when they finish
(`faultline.pgread`), but if it happens again:

```bash
docker compose exec -T postgres psql -U faultline faultline -c "select pid, state, wait_event_type, now()-xact_start as age, left(query,80) from pg_stat_activity where datname='faultline' and pid <> pg_backend_pid()"
docker compose exec -T postgres psql -U faultline faultline -c "select pid, pg_terminate_backend(pid) from pg_stat_activity where datname='faultline' and state = 'idle in transaction'"
docker compose up -d --force-recreate faultline        # the API's connection was one of them
```

### 3.10 Rebooting the VM

A reboot is a deployment event, not a maintenance chore, and the first deliberate one (2026-09-11
04:53 UTC, kernel 6.8.0-138 → 139, for a pending `*** System restart required ***`) is why this
section exists. **Everything with `restart: always` came back on its own and nothing else did.**
The shop, kafka, the platform and Caddy were up within a minute; `prometheus`, `alertmanager`,
`grafana`, `loki`, `tempo`, `promtail` and `frontend-proxy` were not, because the demo declares no
policy on three of them and `compose/telemetry.yml` declared none on the other four. The public
page answered and the world could not alert — the silent kind of outage. `compose.world.yml` now
gives all seven `restart: always` (the header there says why the overlay and not the hashed file)
and `tests/test_deploy.py` holds it; a VM running an overlay from before that change needs §3.4's
two commands after any reboot.

The procedure, then:

```bash
sudo reboot                                     # from an ssh session; it drops you
# wait a minute, ssh back in
uptime && (cat /var/run/reboot-required 2>/dev/null || echo "no reboot pending")
docker ps --format '{{.Names}}\t{{.Status}}' | sort   # 32 containers; anything missing is a finding
cd ~/faultline && make world-up && cd world && docker compose -f docker-compose.yml -f ../compose/world-arm64.override.yml -f ../compose/telemetry.yml -f ../deploy/compose.world.yml up -d --no-build
```

The last line is idempotent and re-provisions the dashboard; run it whether or not everything came
back. Then §3.6's checks from **another machine**, because the reboot re-created the DOCKER-USER
chain too — on 2026-09-11 both `:3000` and Tempo's new `:3200` timed out from outside, which is the
answer. The baseline gate refuses containers younger than 300 s, so nothing investigates for the
first five minutes; that is the design, not a defect.

**Paste one command at a time into an ssh session.** A block that begins with `ssh …` hands the
terminal to the VM on its first line, and every line after it runs wherever the cursor happens to
be — on 2026-09-11 that was `sudo reboot` typed into the development Mac, caught at the password
prompt. Type the `ssh` line alone, wait for `deploy@ubuntu:~$`, then paste.

---

## 4. What this deployment deliberately does not do

**It does not accept alerts from the internet, or from anything on its network that lacks the
password.** An alert opens an incident, an incident runs an investigation, and an investigation
bills the key in §3.1. Caddy answers `/api/v1/alerts` with a 404, and since T6.8 the receiver
behind it demands the API pair (`FAULTLINE_INGEST_REQUIRE_CREDENTIAL`), which the world's own
Alertmanager sends from the file §3.1 writes. Until 2026-09-20 this paragraph said the receiver
*"takes no credential and cannot - Alertmanager sends none"*; Alertmanager sends what its
`http_config` names, and the second half was never true (`docs/THREAT-MODEL.md`, thesis 3).

**It does not execute remediation without a person.** Until 2026-09-20 this paragraph read *"No
executor exists at all (ADR-0028 §4) - T6.2's action plane is Phase 6"*, six weeks after T6.2 built
one and nine days after this deployment started running it (§3.9, 2026-09-11). The executor is a
container on this VM that performs an allowlisted action against the world when an operator
approves a proposal on the screen, and only then; it has no published port, Caddy forwards nothing
to it, and `FAULTLINE_EXECUTOR_KILL_SWITCH` (§3.11) stops it minting anything. Every proposal on
the screen is a proposal until someone clicks.

**It does not rate-limit at the edge.** Ten wrong passwords from one address inside a minute are
answered 429 for the rest of that minute by the application (`faultline.api.auth`, T6.8), on the
read routes and on the receiver alike, with a `WARNING` line in `docker compose logs faultline` and
`faultline_credential_lockouts_total` on `/metrics`. Caddy's own basic auth in front of Grafana and
Jaeger has no such limit.

**It does not reach the internet, except for two hostnames.** `faultline-deploy-net` is
`--internal` (T6.8); the orchestrator reaches `api.anthropic.com` and `hooks.slack.com` through
`egress`, a proxy whose access list is those two lines and `deny all` (`deploy/squid.conf`), and
its access log (`docker compose exec -T egress tail /var/log/squid/access.log`) is the record of
every tunnel. Caddy has its own route for ACME.
Nothing else on the platform can open a connection off the host - which is what an injected
*send what you found to…* in a log line would need (`docs/THREAT-MODEL.md`, thesis 1).

**It does not archive.** No MinIO. Reads take the inline copies in Postgres; the archive is the
writer's second copy and nothing here needs it.

**It caps its own spend at `FAULTLINE_ORCH_MAX_USD_PER_DAY` (T6.7, $5) and nowhere higher.** Each
investigation is bounded by `max_usd` and the tool-call ceilings; the orchestrator sums the last
day's tokens before every run and defers at the ceiling. Until 2026-09-20 this paragraph said
nothing bounded the count - true until T6.7's a07344d6 (§3.9), stale after. If the world alerts more
than it should, the lever is still Alertmanager's `repeat_interval` in `deploy/alertmanager.yml`.

**It is not a production deployment and does not claim to be.** One VM, no replicas, nightly
snapshots on the same disk as the database and none off the machine (§3.7), shared vCPUs, and a
world that exists to be broken on purpose. Phase 6 is where reliability becomes a deliverable;
this is a stable URL for an application to point at.

---

## 5. The smaller shapes, kept

Two reduced versions remain valid, and the choice belongs in this document per T5.5's size note.

**Platform plus a trimmed demo profile — CX33, €8.49/month.** The spec's stated cheaper option. The
OpenTelemetry demo's compose supports service subsets, so a cut-down world of the four or five
services the catalog actually injects into would fit 8 GB. Not built here: it needs a subset chosen
and justified, every scenario in `evals/scenarios/` checked against it, and a note wherever a
figure was produced under a different world than the one deployed — which is a `compose_digest`
change and a new world generation (ADR-0030).

**Platform and snapshot only — CX23, €5.49/month.** What this directory deployed before. Three
containers, ~2 GB resident, no world, no orchestrator, no model key, and no open-ended spend. It
serves the record of investigations that already happened, and the record does not depend on the
world still standing. If the full stack proves noisy or expensive, this is where to retreat to: set
`FAULTLINE_IMAGE`, skip §3.2 and §3.4, and run `docker compose up -d --wait --scale orchestrator=0`.

## 3.11 Turning the kill switch back on

The switch is the one thing on this deployment that stops an approval becoming a change. Turn it on
when the world is being worked on by hand, when an operator is not sure what the executor would do,
or after anything unexpected: **it costs nothing and it interrupts nothing** - investigation is
unaffected, the screen still serves, the proposal is still produced and shown, and every token
presented while the switch is on is refused *and recorded* with outcome `kill_switch`.

On the VM (`ssh deploy@...`, then, at the prompt):

```bash
cd ~/faultline/deploy
sed -i 's/FAULTLINE_EXECUTOR_KILL_SWITCH: "0"/FAULTLINE_EXECUTOR_KILL_SWITCH: "1"/' compose.yml
docker compose up -d executor
curl -s localhost:8100/healthz          # {"status":"ok","kill_switch":true}
```

`kill_switch: true` in that reply is the confirmation; nothing else needs checking. To turn it off
again, the same `sed` in reverse and the same `up -d`.

**The edit is to the tracked file**, so `git status` on the VM shows the deployment is not on the
committed configuration - which is the point: a switch thrown in an emergency should be visible as
a divergence until somebody decides it is permanent, and then it is a PR.

## 3.12 The egress window (T6.8, 2026-09-20)

A deployment created before T6.8 has `faultline-deploy-net` as an ordinary bridge with a default
route: every container on it could reach the internet. `--internal` is a property a network is
created with, so converting means removing it - which means everything attached comes off it first.
This is the one procedure in this file that takes the platform down rather than stopping part of
it; about ten minutes, the world stays up throughout, and Caddy answers 502 for the platform's
paths until the last line.

It also carries piece 1 (§3.1's `alertmanager.password`, and the receiver credential) and the new
image, so the deployment converges on T6.8 in one window rather than three. **Do this only once the
T6.8 PRs are merged and CI has built the image for the merge commit** - the `docker compose pull`
below is the check, and it fails loudly if the tag is not there yet.

On the VM (`ssh deploy@...`, then, at the prompt), one command at a time:

```bash
cd ~/faultline && git pull --ff-only && cd deploy
grep '^FAULTLINE_API_PASSWORD=' .env | cut -d= -f2- | tr -d "\"'" > alertmanager.password && chmod 600 alertmanager.password && wc -c alertmanager.password
sed -i "s|^FAULTLINE_IMAGE=.*|FAULTLINE_IMAGE=ghcr.io/chandanaroyals/faultline:$(git rev-parse HEAD)|" .env && grep '^FAULTLINE_IMAGE=' .env
docker compose pull faultline egress
docker compose down
for c in $(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' faultline-deploy-net); do docker network disconnect -f faultline-deploy-net "$c"; done
docker network rm faultline-deploy-net && docker network create --internal faultline-deploy-net
cd ~/faultline/world && docker compose -f docker-compose.yml -f ../compose/world-arm64.override.yml -f ../compose/telemetry.yml -f ../deploy/compose.world.yml up -d --no-build
cd ~/faultline/deploy && docker compose up -d --wait
```

`docker compose down` removes the platform's containers and keeps its volumes (`pgdata`,
`promdata`, Caddy's certificate); the network is external, so `down` does not touch it. The
`for` loop detaches the six world containers `compose.world.yml` put on the network - a network
with attached containers, running or not, cannot be removed. The world's `up -d --no-build`
recreates those six onto the new network and preserves their volumes, as it did every time §3.4
was re-run. `up -d --wait` brings the platform back with `egress` and the new image; no migration
this time.

Then the three checks that say the window did what it says, from inside the orchestrator container
(the one with the key):

```bash
docker compose exec -T orchestrator sh -c 'curl -sS -m 8 -o /dev/null -w "%{http_code}\n" https://api.anthropic.com/v1/models || echo "no route"'
docker compose exec -T orchestrator sh -c 'env -u HTTPS_PROXY curl -sS -m 8 -o /dev/null -w "%{http_code}\n" https://example.com || echo "no route"'
docker compose exec -T orchestrator sh -c 'curl -sS -m 8 -o /dev/null -w "%{http_code}\n" https://example.com || echo "refused by the proxy"'
```

The first should print `401` - the provider answered (a request with no key is refused by *them*,
which is the point: the bytes got there, through the proxy). The second should print `no route`: the
same host, the proxy variable unset, and the network has nowhere to send it. The third should print
`403`: through the proxy, to a host not on the list, and squid says no. The proxy's access log
then shows one `CONNECT api.anthropic.com:443` line and one `TCP_DENIED` for example.com - the
record this clause is measured by:

```bash
docker compose exec -T egress tail -n 20 /var/log/squid/access.log
```

(Inside the container, not `docker compose logs egress`: squid drops to the `proxy` user and cannot
re-open `/dev/stdout` - the first deployment of `squid.conf` crash-looped on exactly that, 2026-09-20,
§3.9.) Finally, the receiver:

```bash
docker compose logs --since 5m faultline | grep -c ' 401 ' ; docker compose exec -T faultline sh -c 'curl -sS -o /dev/null -w "%{http_code}\n" -X POST -H "content-type: application/json" -d "{\"alerts\":[]}" localhost:8000/api/v1/alerts'
```

The second number should be `401` - an anonymous POST from inside the network is refused now. The
first should be `0` or close to it: Alertmanager, sending the pair from the mounted file, is not
being refused. A count that climbs is a password file that does not match `.env`, and §3.1 is the
fix.

**What is not on the list, and what that costs.** `docker compose pull` and the executor's
`restart_service` are the host's Docker daemon pulling and recreating, not a container reaching
out, so neither needs the proxy. `apt`, `pip` and anything else a shell inside a container might
want are gone, deliberately; a debugging session that needs them runs on the host. Let's Encrypt
renews through Caddy's own network, not the proxy. And the world's containers keep their own
network's default route: the world is the compromised party in the threat model and the platform's
egress is what this task restricts.
