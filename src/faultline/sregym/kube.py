"""Change history over Kubernetes' own record, read-only (T7.2, ADR-0044).

ADR-0004 found that SREGym exposes *"no deploy or config-change surface"*. It does expose the
cluster, through its kubectl MCP server, and the cluster keeps a change record of its own:
a Deployment's ReplicaSets and a StatefulSet's ControllerRevisions are its revisions, each holding
the pod template it ran, and every object carries `managedFields` times. This reads that record,
through the existing `changes` seam of `Tools`, so the change analyst calls the same tool it
always did.

**The commands are fixed, and they are the only ones this module can send**
(adapter registration §3):

1. `kubectl get replicasets -n NS -o json`
2. `kubectl get statefulsets,controllerrevisions -n NS -o json`
3. `kubectl get configmaps,secrets -n NS -o custom-columns=...`: names and times only. The
   registration says *"for metadata only. No value is ever read from a Secret"*; `-o json` would
   have returned the values to this process, so the read itself is narrowed (ADR-0044).
4. `kubectl get events -n NS -o json`

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

SECRET_COLUMNS = (
    "KIND:.kind,NAME:.metadata.name,CREATED:.metadata.creationTimestamp,"
    "CHANGED:.metadata.managedFields[*].time"
)


def commands(namespace: str) -> tuple[str, str, str, str]:
    """The four commands, for one namespace. **Nothing else is ever sent to kubectl.**"""
    if not NAMESPACE.match(namespace):
        raise ValueError(f"not a Kubernetes namespace name: {namespace!r}")
    return (
        f"kubectl get replicasets -n {namespace} -o json",
        f"kubectl get statefulsets,controllerrevisions -n {namespace} -o json",
        f"kubectl get configmaps,secrets -n {namespace} -o custom-columns={SECRET_COLUMNS}",
        f"kubectl get events -n {namespace} -o json",
    )


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


def _owned_by(item: dict[str, Any], kind: str, name: str) -> bool:
    return any(
        ref.get("kind") == kind and ref.get("name") == name
        for ref in (item.get("metadata") or {}).get("ownerReferences") or []
    )


def _revision(item: dict[str, Any]) -> int:
    """A ReplicaSet's revision is an annotation, read for ordering only and never rendered; a
    ControllerRevision carries its own `revision`."""
    if "revision" in item:
        return int(item.get("revision") or 0)
    annotations = (item.get("metadata") or {}).get("annotations") or {}
    try:
        return int(annotations.get("deployment.kubernetes.io/revision") or 0)
    except ValueError:
        return 0


def _template_spec(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("kind") == "ControllerRevision":
        data = item.get("data") or {}
        return ((data.get("spec") or {}).get("template") or {}).get("spec") or {}
    return (((item.get("spec") or {}).get("template") or {}).get("spec")) or {}


def revision_records(
    service: str, revisions: list[dict[str, Any]], start: datetime, end: datetime
) -> list[ChangeRecord]:
    """A workload's revisions, oldest first, as records for the revisions made in the window."""
    ordered = sorted(revisions, key=_revision)
    records: list[ChangeRecord] = []
    for index, item in enumerate(ordered):
        at = _when((item.get("metadata") or {}).get("creationTimestamp"))
        if at is None or not (start <= at <= end):
            continue
        if index == 0:
            records.append(
                _record(service, at, Resource.CONTAINER, Action.CREATED, "workload first created")
            )
            continue
        previous = _template_spec(ordered[index - 1])
        current = _template_spec(item)
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


class KubernetesChangeLog:
    """`ChangeLog` over one namespace, through SREGym's kubectl server."""

    def __init__(self, client: McpClient, profile: Profile, namespace: str) -> None:
        self._client = client
        self._profile = profile
        self._commands = commands(namespace)

    def _get(self, command: str) -> str:
        if command not in self._commands:  # pragma: no cover - the guard the tests assert
            raise ValueError(f"not one of the four registered commands: {command!r}")
        text = self._client.call("kubectl", "exec_kubectl_cmd_safely", {"cmd": command})
        if text.startswith(("Command Rejected", "Error", "error:")):
            raise RuntimeError(f"kubectl refused or failed: {text[:300]}")
        return text

    def _json(self, command: str) -> list[dict[str, Any]]:
        payload = json.loads(self._get(command))
        return [item for item in payload.get("items") or [] if isinstance(item, dict)]

    def records_for(self, service: str, start: datetime, end: datetime) -> list[ChangeRecord]:
        replicasets_cmd, revisions_cmd, config_cmd, events_cmd = self._commands
        workload = self._profile.deployment(service)
        replicasets = [
            r for r in self._json(replicasets_cmd) if _owned_by(r, "Deployment", workload)
        ]
        revisions = [
            r
            for r in self._json(revisions_cmd)
            if r.get("kind") == "ControllerRevision" and _owned_by(r, "StatefulSet", workload)
        ]
        history = replicasets or revisions
        records = revision_records(service, history, start, end)
        latest = _template_spec(max(history, key=_revision)) if history else {}
        records += config_records(
            service, self._get(config_cmd), referenced_config(latest), start, end
        )
        records += event_records(service, {service, workload}, self._json(events_cmd), start, end)
        return sorted(records, key=lambda r: (r.at, r.summary))
