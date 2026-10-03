"""Change history over Kubernetes' own record, read-only (T7.2, ADR-0044).

ADR-0004 found that SREGym exposes *"no deploy or config-change surface"*. It does expose the
cluster, through its kubectl MCP server, and the cluster keeps a change record of its own:
a Deployment's ReplicaSets and a StatefulSet's ControllerRevisions are its revisions, each holding
the pod template it ran, and every object carries `managedFields` times. This reads that record,
through the existing `changes` seam of `Tools`, so the change analyst calls the same tool it
always did.

**The commands are fixed templates, and they are the only ones this module can send**
(adapter registration §3, as Addendum 4's F2 rewrote it). SREGym's kubectl server cuts every
answer at 10,000 characters and refuses pipes, and the pilot measured `-o json` answers of up to
328,279 characters, so every command asks for named fields only, in pieces that each fit:

1. `get replicasets -o jsonpath=...`: each ReplicaSet's name, owner, revision and creation time;
2. `get controllerrevisions -o jsonpath=...`: the same for a StatefulSet's revisions;
3. `get replicaset NAME` / `get controllerrevision NAME -o jsonpath=...`: one revision's pod
   spec, as compact JSON, sent only for revisions in the window and the ones they replaced, at
   most `MAX_SPECS` per call;
4. `get configmaps,secrets -o custom-columns=...`: names and times only. The registration says
   *"for metadata only. No value is ever read from a Secret"*, so the read itself is narrowed
   (ADR-0044);
5. `get services,networkpolicies,persistentvolumeclaims -o custom-columns=...`: names and times
   only, **the owner's decision of 2026-10-03**. Editing a Service writes no event, so as frozen
   a changed Service never showed;
6. `get events --field-selector involvedObject.name=NAME -o jsonpath=...`: kind, name and
   times. **Never the reason or the message.**

Every name in a command is checked against DNS-1123 and comes from the profile or an earlier
answer. **A cut answer is reported, never misparsed**: an index or table keeps the lines it holds
and marks the result truncated; a pod spec that was cut becomes a record saying its revision
could not be read.

**The leak guard.** A fault injector writes things an agent must not read as evidence: annotations,
labels, field-manager names, event reasons. **None of them reaches a record.** A summary is built
only from the paths and values of a pod-template diff, or names an object and that it changed.
`actor` is always the platform's. A record whose text still carries the harness's vocabulary
(`faultline.tools.changes.BANNED_VOCABULARY`, plus `sregym`) has that text withheld, not the
record: the change happened, and saying so is not a leak.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from faultline.sregym.mcp import McpClient
from faultline.sregym.profiles import Profile
from faultline.tools.changes import (
    BANNED_VOCABULARY,
    SYSTEM_ACTOR,
    Action,
    ChangeRecord,
    Resource,
)

LEAK_VOCABULARY = BANNED_VOCABULARY | frozenset({"sregym"})

NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
"""DNS-1123: what every object name sent in a command must be."""

SECRET_COLUMNS = (
    "KIND:.kind,NAME:.metadata.name,CREATED:.metadata.creationTimestamp,"
    "CHANGED:.metadata.managedFields[*].time"
)
"""Names and times. The same columns serve ConfigMaps and Secrets, and Services, NetworkPolicies
and claims."""

CUT = "... [truncated]"
"""What SREGym's kubectl server appends to an answer it cut at 10,000 characters
(`mcp_server/kubectl_server_helper/utils.py:9` at `46c853db`)."""

MAX_SPECS = 6
"""The most pod specs one `change_history` call reads."""

_INDEX = (
    '\'{range .items[*]}{.metadata.name}{"\\t"}{.metadata.ownerReferences[0].kind}{"\\t"}'
    '{.metadata.ownerReferences[0].name}{"\\t"}%s{"\\t"}{.metadata.creationTimestamp}'
    '{"\\n"}{end}\''
)
_EVENTS = (
    '\'{range .items[*]}{.involvedObject.kind}{"\\t"}{.involvedObject.name}{"\\t"}'
    '{.lastTimestamp}{"\\t"}{.eventTime}{"\\n"}{end}\''
)
_SPEC = {
    "replicaset": "'{.spec.template.spec}'",
    "controllerrevision": "'{.data.spec.template.spec}'",
}


def _checked(name: str, pattern: re.Pattern[str] = NAME) -> str:
    if not pattern.match(name):
        raise ValueError(f"not a Kubernetes name: {name!r}")
    return name


class Commands:
    """Every command this module can send, for one namespace. **Nothing else is ever sent.**"""

    def __init__(self, namespace: str) -> None:
        self.ns = _checked(namespace, NAMESPACE)

    def replicasets(self) -> str:
        revision = "{.metadata.annotations.deployment\\.kubernetes\\.io/revision}"
        return f"kubectl get replicasets -n {self.ns} -o jsonpath={_INDEX % revision}"

    def controllerrevisions(self) -> str:
        return f"kubectl get controllerrevisions -n {self.ns} -o jsonpath={_INDEX % '{.revision}'}"

    def spec(self, kind: str, name: str) -> str:
        return f"kubectl get {kind} {_checked(name)} -n {self.ns} -o jsonpath={_SPEC[kind]}"

    def config(self) -> str:
        return f"kubectl get configmaps,secrets -n {self.ns} -o custom-columns={SECRET_COLUMNS}"

    def objects(self) -> str:
        return (
            "kubectl get services,networkpolicies,persistentvolumeclaims "
            f"-n {self.ns} -o custom-columns={SECRET_COLUMNS}"
        )

    def events(self, name: str) -> str:
        return (
            f"kubectl get events -n {self.ns} "
            f"--field-selector involvedObject.name={_checked(name)} -o jsonpath={_EVENTS}"
        )


def commands(namespace: str) -> tuple[str, ...]:
    """The fixed commands, for one namespace. The per-object ones are `Commands`' methods."""
    sent = Commands(namespace)
    return (sent.replicasets(), sent.controllerrevisions(), sent.config(), sent.objects())


CONTAINER_FIELDS: dict[str, Resource] = {
    "image": Resource.IMAGE,
    "env": Resource.ENVIRONMENT,
    "envFrom": Resource.ENVIRONMENT,
    "resources": Resource.RESOURCE_LIMITS,
}
"""A container field's resource; every other container or pod-spec field is `container`."""

VALUE_CHARS = 200


def _when(text: Any) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _value(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return text if len(text) <= VALUE_CHARS else text[: VALUE_CHARS - 1] + "…"


def _env_value(entry: dict[str, Any]) -> Any:
    """An env var's value, or the reference it reads: a secret's value is never resolved."""
    return entry["value"] if "value" in entry else entry.get("valueFrom")


def diff_templates(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[Resource, str, str | None, str | None]]:
    """What changed between two pod specs, as `(resource, path, before, after)`.

    Only `spec` is compared, never the template's `metadata`, which is where labels and
    annotations live: the leak guard's first half.
    """
    changes: list[tuple[Resource, str, str | None, str | None]] = []
    old_containers = {c.get("name"): c for c in before.get("containers") or []}
    new_containers = {c.get("name"): c for c in after.get("containers") or []}
    for name in sorted(set(old_containers) | set(new_containers), key=str):
        old, new = old_containers.get(name), new_containers.get(name)
        if old is None or new is None:
            changes.append(
                (
                    Resource.CONTAINER,
                    f"containers[{name}]",
                    None if old is None else "present",
                    None if new is None else "present",
                )
            )
            continue
        for key in sorted(set(old) | set(new)):
            if key == "name" or old.get(key) == new.get(key):
                continue
            resource = CONTAINER_FIELDS.get(key, Resource.CONTAINER)
            if key == "env":
                old_env = {e.get("name"): _env_value(e) for e in old.get("env") or []}
                new_env = {e.get("name"): _env_value(e) for e in new.get("env") or []}
                for var in sorted(set(old_env) | set(new_env), key=str):
                    if old_env.get(var) != new_env.get(var):
                        changes.append(
                            (
                                resource,
                                f"containers[{name}].env[{var}]",
                                _value(old_env.get(var)),
                                _value(new_env.get(var)),
                            )
                        )
                continue
            changes.append(
                (resource, f"containers[{name}].{key}", _value(old.get(key)), _value(new.get(key)))
            )
    for key in sorted(set(before) | set(after)):
        if key == "containers" or before.get(key) == after.get(key):
            continue
        changes.append((Resource.CONTAINER, key, _value(before.get(key)), _value(after.get(key))))
    return changes


LEAK_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(sorted((re.escape(w) for w in LEAK_VOCABULARY), key=len, reverse=True))
    + r")(?:s|es|d|ed|ing)?(?![a-z0-9])"
)
"""The vocabulary on alphanumeric boundaries. `matched_words` treats a hyphen as part of a word,
which is right for image tags in the world's own change log and wrong here: a Kubernetes value
like `chaos-injected` must match. The head stays strict, so `Default` (a real `dnsPolicy`) never
matches `fault`; over-matching would withhold the very value a DNS-policy problem turns on."""


def _guarded(text: str | None) -> str | None:
    if text is None:
        return None
    return "[withheld: names the benchmark]" if LEAK_PATTERN.search(text.lower()) else text


def _record(
    service: str,
    at: datetime,
    resource: Resource,
    action: Action,
    summary: str,
    before: str | None = None,
    after: str | None = None,
) -> ChangeRecord:
    key = f"{service}|{at.isoformat()}|{resource.value}|{summary}"
    return ChangeRecord(
        id="k8s-" + hashlib.sha256(key.encode()).hexdigest()[:12],
        service=service,
        at=at,
        actor=SYSTEM_ACTOR,
        resource=resource,
        action=action,
        summary=_guarded(summary) or "",
        before=_guarded(before),
        after=_guarded(after),
    )


def revision_records(
    service: str, revisions: list[dict[str, Any]], start: datetime, end: datetime
) -> list[ChangeRecord]:
    """A workload's revisions as records, for the revisions made in the window.

    Each revision is `{"revision", "created", "spec"}`. `spec` is the pod spec, or a string saying
    why it could not be read, or `None` if it was not read (more than `MAX_SPECS` in the window).
    The revision number orders them and is never rendered. **Only the pod spec is ever compared**,
    never the template's metadata, where labels and annotations live: the leak guard's first half.
    """
    ordered = sorted(revisions, key=lambda r: r["revision"])
    records: list[ChangeRecord] = []
    for index, item in enumerate(ordered):
        at = _when(item["created"])
        if at is None or not (start <= at <= end):
            continue
        if index == 0:
            records.append(
                _record(service, at, Resource.CONTAINER, Action.CREATED, "workload first created")
            )
            continue
        current, previous = item.get("spec"), ordered[index - 1].get("spec")
        if current is None or previous is None:
            summary = (
                f"a new revision was made; not read (more than {MAX_SPECS} pod specs "
                "in this window)"
            )
            records.append(_record(service, at, Resource.CONTAINER, Action.UPDATED, summary))
            continue
        unreadable = next((x for x in (current, previous) if isinstance(x, str)), None)
        if unreadable is not None:
            summary = f"a new revision was made; it could not be compared: {unreadable}"
            records.append(_record(service, at, Resource.CONTAINER, Action.UPDATED, summary))
            continue
        for resource, path, old, new in diff_templates(previous, current):
            records.append(
                _record(service, at, resource, Action.UPDATED, f"{path} changed", old, new)
            )
    return records


def referenced_config(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """The ConfigMaps and Secrets a pod spec reads, as `(kind, name)`."""
    found: set[tuple[str, str]] = set()
    for volume in spec.get("volumes") or []:
        if (volume.get("configMap") or {}).get("name"):
            found.add(("ConfigMap", volume["configMap"]["name"]))
        if (volume.get("secret") or {}).get("secretName"):
            found.add(("Secret", volume["secret"]["secretName"]))
    for container in (spec.get("containers") or []) + (spec.get("initContainers") or []):
        for source in container.get("envFrom") or []:
            if (source.get("configMapRef") or {}).get("name"):
                found.add(("ConfigMap", source["configMapRef"]["name"]))
            if (source.get("secretRef") or {}).get("name"):
                found.add(("Secret", source["secretRef"]["name"]))
        for entry in container.get("env") or []:
            ref = entry.get("valueFrom") or {}
            if (ref.get("configMapKeyRef") or {}).get("name"):
                found.add(("ConfigMap", ref["configMapKeyRef"]["name"]))
            if (ref.get("secretKeyRef") or {}).get("name"):
                found.add(("Secret", ref["secretKeyRef"]["name"]))
    return found


def config_records(
    service: str,
    table: str,
    referenced: set[tuple[str, str]],
    start: datetime,
    end: datetime,
) -> list[ChangeRecord]:
    """ConfigMaps and Secrets the service reads, changed in the window. Names and times only."""
    records: list[ChangeRecord] = []
    for line in table.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3 or (parts[0], parts[1]) not in referenced:
            continue
        kind, name, created = parts[0], parts[1], _when(parts[2])
        times = sorted(
            t for t in (_when(x) for x in (parts[3] if len(parts) > 3 else "").split(",")) if t
        )
        if created is not None and start <= created <= end:
            records.append(
                _record(service, created, Resource.CONFIG, Action.CREATED, f"{kind} {name} created")
            )
        for at in times:
            if start <= at <= end and at != created:
                records.append(
                    _record(service, at, Resource.CONFIG, Action.UPDATED, f"{kind} {name} changed")
                )
    return records


WORKLOAD_KINDS = frozenset({"Pod", "ReplicaSet", "Deployment", "StatefulSet", "ControllerRevision"})


def event_records(
    service: str, names: set[str], events: list[dict[str, Any]], start: datetime, end: datetime
) -> list[ChangeRecord]:
    """An event on a non-workload object named for the service (a Service, a NetworkPolicy, a
    webhook). **The event's reason and message are never read**: only that it happened."""
    records: list[ChangeRecord] = []
    seen: set[tuple[str, str, datetime]] = set()
    for event in events:
        involved = event.get("involvedObject") or {}
        kind, name = str(involved.get("kind") or ""), str(involved.get("name") or "")
        if kind in WORKLOAD_KINDS or name not in names:
            continue
        at = _when(event.get("lastTimestamp") or event.get("eventTime"))
        if at is None or not (start <= at <= end) or (kind, name, at) in seen:
            continue
        seen.add((kind, name, at))
        records.append(
            _record(service, at, Resource.CONFIG, Action.UPDATED, f"{kind} {name}: event recorded")
        )
    return records


def referenced_claims(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """The PersistentVolumeClaims a pod spec mounts, as `(kind, name)`."""
    return {
        ("PersistentVolumeClaim", volume["persistentVolumeClaim"]["claimName"])
        for volume in spec.get("volumes") or []
        if (volume.get("persistentVolumeClaim") or {}).get("claimName")
    }


def object_records(
    service: str,
    table: str,
    services: set[str],
    claims: set[tuple[str, str]],
    start: datetime,
    end: datetime,
) -> list[ChangeRecord]:
    """Services named for the service, claims it mounts, and every NetworkPolicy, changed in the
    window. **Names and times only** (the owner's decision of 2026-10-03)."""
    wanted = {("Service", name) for name in services} | claims
    records = config_records(service, table, wanted, start, end)
    policies = {
        ("NetworkPolicy", parts[1])
        for parts in (line.split() for line in table.splitlines()[1:])
        if len(parts) >= 2 and parts[0] == "NetworkPolicy"
    }
    for record in config_records(service, table, policies, start, end):
        note = "; namespace-wide, and the pods it selects are not read"
        records.append(record.model_copy(update={"summary": record.summary + note}))
    return records


def _cut(text: str) -> tuple[str, bool]:
    """An answer without SREGym's cut marker, and whether it was cut. A cut table loses its last,
    partial line."""
    stripped = text.rstrip()
    if not stripped.endswith(CUT):
        return text, False
    body = stripped[: -len(CUT)]
    return body[: body.rfind("\n")] if "\n" in body else "", True


def index_rows(text: str) -> list[dict[str, Any]]:
    """`name  owner-kind  owner  revision  created`, one revision per line."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not parts[0]:
            continue
        try:
            revision = int(parts[3] or 0)
        except ValueError:
            revision = 0
        rows.append(
            {
                "name": parts[0],
                "owner_kind": parts[1],
                "owner": parts[2],
                "revision": revision,
                "created": parts[4],
            }
        )
    return rows


def event_rows(text: str) -> list[dict[str, Any]]:
    """`kind  name  lastTimestamp  eventTime`, as the event dicts `event_records` reads."""
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        events.append(
            {
                "involvedObject": {"kind": parts[0], "name": parts[1]},
                "lastTimestamp": parts[2] or None,
                "eventTime": parts[3] or None,
            }
        )
    return events


class KubernetesChangeLog:
    """`ChangeLog` over one namespace, through SREGym's kubectl server."""

    def __init__(self, client: McpClient, profile: Profile, namespace: str) -> None:
        self._client = client
        self._profile = profile
        self._commands = Commands(namespace)
        self.cut: list[str] = []
        """The answers the last `records_for` found cut, named. `McpToolSet` marks the result
        truncated when any was."""

    def _get(self, command: str) -> str:
        text = self._client.call("kubectl", "exec_kubectl_cmd_safely", {"cmd": command})
        if text.startswith(("Command Rejected", "Error", "error:")):
            raise RuntimeError(f"kubectl refused or failed: {text[:300]}")
        return text

    def _table(self, command: str, what: str) -> str:
        text, was_cut = _cut(self._get(command))
        if was_cut:
            self.cut.append(what)
        return text

    def _spec(self, kind: str, name: str) -> dict[str, Any] | str:
        """One revision's pod spec, or why it could not be read."""
        try:
            text = self._get(self._commands.spec(kind, name))
        except (RuntimeError, ValueError) as exc:
            return str(exc).splitlines()[0][:200]
        _, was_cut = _cut(text)
        if was_cut:
            self.cut.append(f"{kind} {name}")
            return "its pod spec was cut at 10,000 characters"
        try:
            spec = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            return "its pod spec was not readable JSON"
        return spec if isinstance(spec, dict) else {}

    def _revision_records(
        self, service: str, kind: str, rows: list[dict[str, Any]], start: datetime, end: datetime
    ) -> tuple[list[ChangeRecord], dict[str, Any]]:
        """Records for the revisions made in the window, and the latest revision's pod spec.

        Pod specs are read only for the revisions in the window and the ones they replaced,
        newest first, and the latest revision's (its config and claims are what the service
        reads now): at most `MAX_SPECS`.
        """
        ordered = sorted(rows, key=lambda r: r["revision"])
        in_window = [
            i for i, r in enumerate(ordered) if (at := _when(r["created"])) and start <= at <= end
        ]
        needed: list[int] = [len(ordered) - 1] if ordered else []
        for i in sorted(in_window, reverse=True):
            needed += [j for j in (i, i - 1) if j >= 0 and j not in needed]
        specs = {j: self._spec(kind, ordered[j]["name"]) for j in needed[:MAX_SPECS]}
        revisions = [
            {"revision": r["revision"], "created": r["created"], "spec": specs.get(j)}
            for j, r in enumerate(ordered)
        ]
        latest = specs.get(len(ordered) - 1)
        records = revision_records(service, revisions, start, end)
        return records, latest if isinstance(latest, dict) else {}

    def records_for(self, service: str, start: datetime, end: datetime) -> list[ChangeRecord]:
        self.cut = []
        workload = self._profile.deployment(service)
        sent = self._commands
        rows = [
            r
            for r in index_rows(self._table(sent.replicasets(), "the ReplicaSet index"))
            if r["owner_kind"] == "Deployment" and r["owner"] == workload
        ]
        kind = "replicaset"
        if not rows:
            kind = "controllerrevision"
            rows = [
                r
                for r in index_rows(
                    self._table(sent.controllerrevisions(), "the ControllerRevision index")
                )
                if r["owner_kind"] == "StatefulSet" and r["owner"] == workload
            ]
        records, latest = self._revision_records(service, kind, rows, start, end)
        records += config_records(
            service,
            self._table(sent.config(), "the ConfigMap and Secret table"),
            referenced_config(latest),
            start,
            end,
        )
        records += object_records(
            service,
            self._table(sent.objects(), "the Service, NetworkPolicy and claim table"),
            {service, workload},
            referenced_claims(latest),
            start,
            end,
        )
        for name in sorted({service, workload}):
            events = event_rows(self._table(sent.events(name), f"the events on {name}"))
            records += event_records(service, {service, workload}, events, start, end)
        return sorted(records, key=lambda r: (r.at, r.summary))
