"""T6.5's accept gate: the ledger, the route, and the seeder's refusal.

The registration's §3 names the failure this has to avoid - *a boolean nobody sets* - so the
tests that matter are the ones that try to get a postmortem into the corpus without a person,
and fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from faultline.api import postmortems
from faultline.context.acceptance import (
    Acceptance,
    InMemoryAcceptanceStore,
    digest_of,
)
from faultline.context.embedding import HashingEmbedder
from faultline.context.postmortem import SECTIONS, parse_postmortem_text
from faultline.context.seed import UnacceptedError, seed
from faultline.context.store import InMemoryPastIncidentStore

SCENARIO = "cart-bad-image-tag"

FRONT = f"""---
scenario_id: {SCENARIO}
origin: scenario:{SCENARIO}
split: dev
incident_id: inc-0007
recorded_from: 2026-09-01T03:11:37Z
---
"""

BODIES = {
    "What the investigation concluded": "The checkout path stopped answering at 03:12.",
    "What ruled the alternatives out": (
        "Repeated boot banners with no request handling. Downstream leaves answered normally."
    ),
    "What the proposal rested on": (
        "A prior container reference was in the change log, inside the window."
    ),
    "What happened at the approval boundary": "Refused - the target sat outside scoped topology.",
    "What was never measured": "Whether the caller retried, and with what timeout.",
}


def document(**overrides: str) -> str:
    bodies = {**BODIES, **overrides}
    lines = [FRONT, "# Checkout stopped answering at 03:12", ""]
    for section in SECTIONS:
        lines += [f"## {section}", "", bodies[section], ""]
    return "\n".join(lines)


def bundle(tmp_path: Path, *, postmortem: str | None = None) -> Path:
    """A dev root with one complete bundle, and optionally a postmortem in it."""
    root = tmp_path / "dev"
    scenario = root / SCENARIO
    scenario.mkdir(parents=True)
    narrative = "\n".join(
        [
            "---",
            f"origin: scenario:{SCENARIO}",
            "split: dev",
            "recorded_from: 2026-09-01T03:11:37Z",
            "---",
            "",
            "# Checkout stopped answering",
            "",
            "## What was observed",
            "",
            "Orders stopped completing at 03:12.",
            "",
        ]
    )
    (scenario / "incident.md").write_text(narrative)
    (scenario / "manifest.json").write_text(
        json.dumps(
            {
                "origin": f"scenario:{SCENARIO}",
                "scenario_fingerprint": "abc123",
                "fault_class": "bad_deploy",
            }
        )
    )
    if postmortem is not None:
        (scenario / "postmortem.md").write_text(postmortem)
    return root


def store() -> InMemoryPastIncidentStore:
    return InMemoryPastIncidentStore(HashingEmbedder())


def accepted_ledger(text: str, caller: str = "chandana") -> InMemoryAcceptanceStore:
    ledger = InMemoryAcceptanceStore()
    parsed = parse_postmortem_text(text)
    ledger.append(
        Acceptance(scenario_id=parsed.scenario_id, body_digest=digest_of(parsed), caller=caller)
    )
    return ledger


# --- the seeder's refusal -----------------------------------------------------------------------


def test_a_bundle_with_no_postmortem_seeds_exactly_as_before(tmp_path: Path) -> None:
    """The gate costs nothing where there is nothing to gate. Every bundle in the repository is
    this case today."""
    result = seed(store(), bundle(tmp_path), InMemoryAcceptanceStore())

    assert result.seeded == [SCENARIO]
    assert result.documents == 1


def test_an_unaccepted_postmortem_stops_the_seed(tmp_path: Path) -> None:
    """**The gate.** A document somebody wrote and nobody approved, sitting in the path the
    seeder reads, does not reach the corpus."""
    root = bundle(tmp_path, postmortem=document())

    with pytest.raises(UnacceptedError, match="no acceptance"):
        seed(store(), root, InMemoryAcceptanceStore())


def test_an_accepted_postmortem_seeds_beside_its_narrative(tmp_path: Path) -> None:
    text = document()
    result = seed(store(), bundle(tmp_path, postmortem=text), accepted_ledger(text))

    assert result.seeded == [SCENARIO, f"{SCENARIO} (postmortem)"]
    assert result.documents == 2


def test_editing_an_accepted_postmortem_un_accepts_it(tmp_path: Path) -> None:
    """**Why the row pins a digest and not a scenario id.** Accepting is accepting *these
    words*. An acceptance keyed on the scenario alone would be the boolean §3 warns about
    wearing a timestamp: a person accepts a draft, someone edits it, and the corpus takes the
    edit on the strength of a row about a document that no longer exists."""
    ledger = accepted_ledger(document())
    edited = document(**{"What was never measured": "Nothing. Everything was measured."})

    with pytest.raises(UnacceptedError, match="no acceptance"):
        seed(store(), bundle(tmp_path, postmortem=edited), ledger)


def test_correcting_front_matter_does_not_un_accept_it(tmp_path: Path) -> None:
    """The digest is over title and sections, so the metadata a person did not read can be
    fixed without asking them to read the prose again."""
    text = document()
    ledger = accepted_ledger(text)
    corrected = text.replace("incident_id: inc-0007", "incident_id: inc-0008")

    result = seed(store(), bundle(tmp_path, postmortem=corrected), ledger)

    assert f"{SCENARIO} (postmortem)" in result.seeded


def test_the_default_ledger_refuses_rather_than_admits(tmp_path: Path) -> None:
    """**The safe default, not the convenient one.** A caller who has not wired the ledger is a
    caller who cannot check the gate, and the other default - *no ledger means no check* - would
    let a `faultline-seed` invocation publish an unaccepted document by omitting an argument."""
    root = bundle(tmp_path, postmortem=document())

    with pytest.raises(UnacceptedError):
        seed(store(), root)


def test_a_postmortem_from_the_wrong_split_is_refused_before_the_ledger(tmp_path: Path) -> None:
    """ADR-0008's quarantine applies to the new document class too, and it is checked first: a
    holdout postmortem with a valid acceptance row is still a holdout postmortem."""
    from faultline.context.seed import QuarantineError

    text = document().replace("split: dev", "split: holdout")

    with pytest.raises(QuarantineError, match="quarantine"):
        seed(store(), bundle(tmp_path, postmortem=text), accepted_ledger(text))


def test_a_leaking_postmortem_is_refused_even_with_an_acceptance(tmp_path: Path) -> None:
    """A person can accept anything; they cannot accept a leak into the corpus. The parse runs
    before the ledger is consulted, so an accepted document that names its remediation still
    stops the seed."""
    from faultline.context.postmortem import PostmortemLeakError

    text = document(**{"What the proposal rested on": "We proposed rollback_image."})
    ledger = InMemoryAcceptanceStore()
    ledger.append(Acceptance(scenario_id=SCENARIO, body_digest="whatever", caller="chandana"))

    with pytest.raises(PostmortemLeakError):
        seed(store(), bundle(tmp_path, postmortem=text), ledger)


# --- the route ----------------------------------------------------------------------------------


def client(ledger: InMemoryAcceptanceStore, caller: str = "chandana") -> TestClient:
    app = FastAPI()
    app.include_router(postmortems.build(acceptances=ledger, caller=caller))
    return TestClient(app)


def test_accepting_records_a_row_and_returns_the_digest() -> None:
    ledger = InMemoryAcceptanceStore()
    text = document()

    response = client(ledger).post(
        f"/api/v1/postmortems/{SCENARIO}/accept", json={"document": text}
    )

    assert response.status_code == 200
    row = response.json()["accepted"]
    assert row["scenario_id"] == SCENARIO
    assert row["body_digest"] == digest_of(parse_postmortem_text(text))
    assert ledger.accepted(SCENARIO, row["body_digest"]) is not None


def test_the_caller_is_the_authenticated_username_not_a_body_field() -> None:
    """`api/approvals.py`'s rule, and the reason the ledger is worth having: an audit row that
    says *who accepted* is the point of the row. There is no field a request can set."""
    ledger = InMemoryAcceptanceStore()

    response = client(ledger, caller="alice").post(
        f"/api/v1/postmortems/{SCENARIO}/accept",
        json={"document": document(), "who": "bob", "caller": "bob"},
    )

    assert response.status_code == 200
    assert response.json()["accepted"]["caller"] == "alice"
    assert ledger.callers() == ["alice"]


def test_the_route_runs_the_document_class_s_guards_and_writes_no_row() -> None:
    """**Where prediction 6 is scored.** The registration predicts no postmortem trips the leak
    guard on its first draft and says it expects that to fail; this is the surface where a
    human's edit meets the rule. A leak is a 422 and not a row."""
    ledger = InMemoryAcceptanceStore()
    leaking = document(**{"What the proposal rested on": "We proposed rollback_image."})

    response = client(ledger).post(
        f"/api/v1/postmortems/{SCENARIO}/accept", json={"document": leaking}
    )

    assert response.status_code == 422
    assert "rollback_image" in response.json()["detail"]
    assert ledger.callers() == [], "a refused document leaves no trace of having been accepted"


def test_a_document_cannot_be_accepted_under_another_scenario_s_name() -> None:
    """`origin` is the exclusion key. Accepting this under the wrong scenario would admit it to
    the corpus of the incident it is about."""
    response = client(InMemoryAcceptanceStore()).post(
        "/api/v1/postmortems/ad-memory-squeeze/accept", json={"document": document()}
    )

    assert response.status_code == 409
    assert "exclusion key" in response.json()["detail"]


def test_re_accepting_the_same_words_is_recorded_and_changes_nothing() -> None:
    """Migration 0007's rule: the first row is the gate, a second is a fact worth keeping. Two
    people reading the same draft is what a review looks like."""
    ledger = InMemoryAcceptanceStore()
    text = document()

    for who in ("alice", "bob"):
        assert (
            client(ledger, caller=who)
            .post(f"/api/v1/postmortems/{SCENARIO}/accept", json={"document": text})
            .status_code
            == 200
        )

    assert ledger.callers() == ["alice", "bob"]


def test_the_ledger_can_answer_whether_the_only_caller_is_a_script() -> None:
    """**§3's failure mode as a query rather than a suspicion.** Nothing here can make the
    caller a person - an automation holding the credential produces rows exactly as a person
    does - so what the ledger buys is that the question is answerable."""
    ledger = InMemoryAcceptanceStore()
    client(ledger, caller="ci-bot").post(
        f"/api/v1/postmortems/{SCENARIO}/accept", json={"document": document()}
    )

    assert ledger.callers() == ["ci-bot"]


# --- the seams this piece leaves -----------------------------------------------------------------


def test_the_drift_check_accounts_for_every_postmortem_on_disk() -> None:
    """**The tripwire this replaces has fired, and this is what it was guarding.**

    It asserted that no bundle carried a `postmortem.md`, because
    `evalharness.corpusdrift.working_tree_rows` did not know about them and would have
    under-reported the corpus from the day one landed. Ten landed on 2026-09-15.

    `working_tree_rows` now calls the seeder's own `postmortem_rows`, so what it reports is what
    the seeder would write - minus the ledger, which it cannot read and does not need to: a
    postmortem in the tree and not in the store is a real disagreement either way.
    """
    from evalharness.corpusdrift import working_tree_rows

    root = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "artifacts" / "dev"
    if not root.is_dir():
        return
    on_disk = sorted(p.parent.name for p in root.glob("*/postmortem.md"))
    reported = {
        d.removeprefix("postmortem:")
        for d, _, _ in working_tree_rows()
        if d.startswith("postmortem:")
    }

    assert reported == set(on_disk), (
        f"the drift check reports {sorted(reported)} and the tree holds {on_disk}; a corpus "
        "document the check cannot see is a corpus it silently under-reports"
    )


def test_a_postmortem_is_chunked_the_same_way_on_both_paths() -> None:
    """One implementation of *what the corpus should contain*. The seeder applies the ledger on
    top; the rows themselves come from the same function, so the check cannot form its own
    opinion of the corpus."""
    from evalharness.corpusdrift import working_tree_rows
    from faultline.context.seed import postmortem_rows

    root = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "artifacts" / "dev"
    if not root.is_dir():
        return
    bundles = sorted(p.parent for p in root.glob("*/postmortem.md"))
    if not bundles:
        return
    direct = {(c.document_id, c.section, c.text) for c in postmortem_rows(bundles[0])}
    through_check = {r for r in working_tree_rows() if r[0] == f"postmortem:{bundles[0].name}"}

    assert direct == through_check and direct
