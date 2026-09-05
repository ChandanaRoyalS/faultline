# Deploying Faultline (T5.5)

**What goes up: the platform and the record of investigations that already happened.** Real
verdicts, real citations, real Grafana deep-links, restored from a snapshot of a machine that ran
them. Three containers — Postgres, the platform, Caddy for TLS.

**What does not go up: the world.** The OpenTelemetry demo is ~20 containers and wants 16 GB, it
exists to be broken on purpose, and a thing whose job is to fail is a poor foundation for the one
URL a stranger is given. §5 prices the version that includes it, for anyone who wants to demo a
live injection.

---

## 1. What it costs

Measured against the trimmed shape below — three containers, ~2 GB resident, a database whose
whole content is a few hundred incidents.

| | vCPU / RAM | monthly | notes |
|---|---|---|---|
| **Hetzner CX23** | 2 / 4 GB | **$6.49** | 40 GB disk, 20 TB traffic. What this was sized for |
| Hetzner CX33 | 4 / 8 GB | $9.99 | headroom for §5's world profile |
| DigitalOcean Basic | 2 / 4 GB | $24.00 | same shape, four times the price |
| Hetzner CCX23 (dedicated) | 4 / 16 GB | $101.49 | the plan's original sizing, for the full world |
| DigitalOcean General Purpose | 4 / 16 GB | $126.00 | as above |

Add **$0.50–1/month** for the IPv4 address on Hetzner, and a domain (~$10–15/year) — Caddy needs a
real hostname to get a certificate for, so a bare IP does not work.

Prices checked 2026-09-05 and **not automatically current**: Hetzner raised CCX and CPX by up to
176% in June 2026, so the dedicated row in particular is worth re-checking before committing to it.

---

## 1a. Rehearse it first — it has never been run

**Every file in this directory was written and committed without once being started.** No Docker
daemon was available where they were authored. That is the exact shape of defect this project has
now found nine times — built, green, never run — and the response is to make running it free
rather than to assert it is fine.

On any machine with Docker, from a clone:

```bash
cd faultline/deploy
cp env.example .env
$EDITOR .env                  # SITE_ADDRESS can be anything here; the other two must be set
docker compose -f compose.yml -f compose.rehearsal.yml up -d --build
docker compose -f compose.yml -f compose.rehearsal.yml exec faultline faultline-migrate
```

Then:

```bash
curl -sS localhost:8001/healthz                                         # {"status":"ok"}
curl -sS -o /dev/null -w '%{http_code}\n' localhost:8001/api/v1/incidents   # 401
curl -sS -u faultline:$FAULTLINE_API_PASSWORD localhost:8001/api/v1/incidents
```

The last returns an empty list until §3.3 loads a snapshot — that is correct, and it is a different
answer from a 404, which would mean the read surface never mounted.

Tear down with `docker compose -f compose.yml -f compose.rehearsal.yml down -v`. That `-v` is
safe **because the deployment is compose project `faultline-deploy`**, a different project from the
repository's own `faultline` — see the note at the top of `compose.yml` for what happened the first
time it was not.

**The first rehearsal found a real defect, which is the argument for this section.** `compose.yml`
declared `name: faultline`, the same project compose derives for the repository's own
`docker-compose.yml`, so it attached to the running development Postgres and pointed the
deployment's DSN at the developer's database. It failed safe by luck rather than design — an
existing volume keeps its original password — and against an empty one it would have handed the
deployment live development data. Cost of finding it here: four minutes. Cost of finding it on a
public VM: a published database.

**What a rehearsal covers:** the image, its `CMD`, the DSN, the credential refusal, the migration,
and the read surface. **What it cannot:** the certificate and the DNS record. Those stay first-run
risks on the VM, and §3.4 is where they are checked.

---

## 2. Prerequisites

- A VM with Docker and the compose plugin, and ports 80 and 443 open.
- A domain or subdomain with an **A record pointing at the VM's IP**, resolving before you start —
  Caddy asks Let's Encrypt for a certificate on the first request and the challenge fails if DNS
  has not propagated.
- The repository cloned on the VM.

---

## 3. The procedure

### 3.1 Configure

```bash
cd faultline/deploy
cp env.example .env
$EDITOR .env          # SITE_ADDRESS, POSTGRES_PASSWORD, FAULTLINE_API_PASSWORD
```

Every variable is mandatory. `compose.yml` uses `${VAR:?...}` so a missing one stops the
deployment with a named error instead of starting something half-configured.

`FAULTLINE_API_PASSWORD` is not optional in a different sense too: `faultline.api.app.assemble`
**raises before it connects to the database** if it is unset. The read surface mounts behind a
credential or it does not mount.

### 3.2 Bring it up

```bash
docker compose up -d --build
docker compose exec faultline faultline-migrate
```

`faultline-migrate` applies the schema to an empty database. Nothing is in it yet — §3.3 fills it.

### 3.3 Load a snapshot

The deployment has no world, so it produces no incidents of its own. It serves what a machine that
*did* have a world produced.

**Why a database dump rather than something in the repository.** The committed run directories
(`evals/runs/<id>/`) carry the manifest and the verdict, but **not the trajectory** — no steps, no
tool calls, no `request` fields. The timeline and every citation deep-link are built from
`trajectory_tool_calls.request`, read from Postgres. So the two things that make this screen worth
deploying are exactly the two a repo-only loader cannot reconstruct.

On the machine that has the incidents, with its platform running:

```bash
make deploy-snapshot            # writes deploy/snapshot.sql.gz, gitignored
```

Then copy it up and restore:

```bash
scp deploy/snapshot.sql.gz you@your-vm:/tmp/
ssh you@your-vm
cd faultline/deploy
gunzip -c /tmp/snapshot.sql.gz | docker compose exec -T postgres psql -U faultline faultline
```

**The snapshot carries the monitored world's telemetry** — every log line an agent quoted and every
query it ran. It is a demo world and not anyone's production data, but it is the reason the
credential in §3.1 exists, and the reason `deploy/snapshot.sql*` is gitignored.

### 3.4 Check it

```bash
curl -sS https://$SITE_ADDRESS/healthz                       # {"status":"ok"}
curl -sS -o /dev/null -w '%{http_code}\n' https://$SITE_ADDRESS/api/v1/incidents   # 401
curl -sS -u faultline:$FAULTLINE_API_PASSWORD https://$SITE_ADDRESS/api/v1/incidents | head -c 200
```

The **401 on the second line is the check that matters** — it is the one that fails open. Then
take an `incident_id` from the third and open

```
https://$SITE_ADDRESS/ui/incidents/<incident_id>
```

---

## 4. What this deployment deliberately does not do

**It does not investigate.** No orchestrator, no agents, no model key on the VM. Nothing here
makes a model call, which is why it costs $6.49/month and not $6.49/month plus whatever a stranger
clicking a button costs. `faultline.api.incidents`' routes are structurally read-only: the router
never imports a writer and cannot advance a state machine.

**It does not receive alerts.** `POST /api/v1/alerts` is routed and reachable — the receiver is
mounted the same as anywhere — but no Alertmanager exists to post to it. It is left rather than
blocked so a deployment that later grows a world needs no different Caddyfile. **It is
unauthenticated**, as it is everywhere: Alertmanager sends no credential of any kind, so a password
there would stop alerts rather than attackers (`docs/THREAT-MODEL.md`, thesis 3). The consequence
here is that anything reaching the URL can fabricate an incident row, which on a read-only demo is
noise rather than exposure — but it is noise, and it is on the record.

**It does not stay in sync.** The snapshot is a point in time. A new sweep on the development
machine does not appear until §3.3 is run again.

**It does not archive.** No MinIO. Reads take the inline copies in Postgres; the archive is the
writer's second copy and this deployment never writes.

---

## 5. If you want the live world too

Not recommended as the stable URL, and priced here rather than argued about.

Bring the demo up alongside on a 4 vCPU / 8 GB box (CX33, $9.99/month) using the repository's own
`make world-up`, then run the orchestrator and point `FAULTLINE_NOTIFY_PUBLIC_BASE_URL` at
`https://$SITE_ADDRESS`. Three things change and each is a real cost:

1. **A model key lives on the VM**, and anything that can trigger an investigation can spend it.
2. **The world falls over.** Kafka's JDK already fails on GitHub's runners
   (`CgroupV2Subsystem.getInstance`, see `docs/PLAN.md`); a VM you are not watching is worse.
3. **The URL stops being stable**, which was the deliverable.

The trimmed deployment keeps its meaning either way: it serves the record, and the record does not
depend on the world still standing.
