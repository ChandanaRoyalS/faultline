"""The committed acceptance ledger (Q67 closed, and CI's integration job un-reddened).

An acceptance is a person's decision, recorded in one Postgres. Every other place that seeds the
dev tree had none of those rows and refused all ten postmortems: CI's integration fixture, on
twenty-five consecutive main commits; `faultline-seed --dry-run` (Q67); a fresh deployment. The
rows now travel with the bundles they admit, verbatim, and these tests hold the file to the tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.context import acceptance
from faultline.context.acceptance import (
    InMemoryAcceptanceStore,
    digest_of,
    import_ledger,
    ledger_path,
    ledger_store,
    read_ledger,
)
from faultline.context.postmortem import parse_postmortem
from faultline.context.seed import POSTMORTEM, dev_bundles

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV = REPO_ROOT / "evals" / "scenarios" / "artifacts" / "dev"
LEDGER = ledger_path(DEV)


def test_the_ledger_is_committed_beside_the_bundles_it_admits() -> None:
    assert LEDGER.is_file(), f"{acceptance.LEDGER_FILE} is what CI and --dry-run seed with"
    rows = read_ledger(LEDGER)
    assert rows, "an empty ledger refuses every postmortem, which is the state this file ended"
    assert all(row.caller for row in rows), "a row without a caller is nobody's decision"
    assert all(row.at.tzinfo is not None for row in rows), "timestamps carry their zone"


def test_every_dev_postmortem_s_current_words_have_a_row_and_every_row_has_a_postmortem() -> None:
    """**The tripwire, and where it fires.** A postmortem edited after acceptance has a new
    digest and no row, and `postmortem_chunks` refuses it - in CI's integration job, an hour
    after the merge, on a runner. This asserts the same thing in `make check`, before the
    commit: the words on disk are the words that were accepted, for all ten, and the ledger
    names no postmortem the tree does not have."""
    ledger = ledger_store(LEDGER)
    on_disk: dict[str, str] = {}
    for bundle, skip in dev_bundles(DEV):
        path = bundle / POSTMORTEM
        if skip is not None or not path.exists():
            continue
        postmortem = parse_postmortem(path)
        on_disk[postmortem.scenario_id] = digest_of(postmortem)

    assert len(on_disk) == 10, sorted(on_disk)
    unaccepted = {sid for sid, digest in on_disk.items() if ledger.accepted(sid, digest) is None}
    assert not unaccepted, (
        f"{sorted(unaccepted)}: postmortem.md differs from the accepted text. An edit after "
        "acceptance needs accepting - through the approval surface, which appends a row; then "
        "re-export the ledger. Do not edit the digest in the file to match."
    )
    named = {row.scenario_id for row in read_ledger(LEDGER)}
    assert named <= set(on_disk), f"rows for postmortems the tree lacks: {named - set(on_disk)}"


def test_the_file_is_the_export_the_table_would_give_and_nothing_defaulted(tmp_path: Path) -> None:
    """Every field required. A loader that defaulted `at` or `caller` would be this process
    claiming the decision, which is the thing the file exists not to do."""
    good = json.loads(LEDGER.read_text())[0]
    for missing in ("id", "at", "scenario_id", "body_digest", "caller"):
        row = {k: v for k, v in good.items() if k != missing}
        path = tmp_path / f"no-{missing}.json"
        path.write_text(json.dumps([row]))
        with pytest.raises(ValueError, match=missing):
            read_ledger(path)
    (tmp_path / "not-a-list.json").write_text(json.dumps(good))
    with pytest.raises(ValueError, match="list"):
        read_ledger(tmp_path / "not-a-list.json")


def test_import_replicates_rows_verbatim_and_a_second_import_appends_nothing() -> None:
    """What `faultline-seed --import-acceptances` does to a deployment's ledger: the original
    ids, callers and dates, so the table says who decided and when; and idempotent by the
    question the seeder asks, so re-running the deploy procedure is running it once."""
    rows = read_ledger(LEDGER)
    table = InMemoryAcceptanceStore()

    first = import_ledger(rows, table)
    second = import_ledger(rows, table)

    assert first == len(rows) and second == 0
    for row in rows:
        held = table.accepted(row.scenario_id, row.body_digest)
        assert held is not None
        assert (held.id, held.at, held.caller) == (row.id, row.at, row.caller)
    assert table.callers() == sorted({row.caller for row in rows})


def test_import_leaves_a_row_that_already_admits_the_words_alone() -> None:
    """A deployment whose ledger already has its own row for the same words keeps that row -
    the first decision stands, and the import does not overwrite whose it was."""
    rows = read_ledger(LEDGER)
    table = InMemoryAcceptanceStore()
    theirs = acceptance.Acceptance(
        scenario_id=rows[0].scenario_id,
        body_digest=rows[0].body_digest,
        caller="operator-on-the-vm",
    )
    table.append(theirs)

    appended = import_ledger(rows, table)

    assert appended == len(rows) - 1
    assert table.accepted(rows[0].scenario_id, rows[0].body_digest) is theirs


def test_the_integration_fixture_seeds_with_the_committed_ledger() -> None:
    """The fixture that was red for twenty-five commits. Held in source, because the fixture
    itself needs Docker and a model download and runs only in CI."""
    source = (REPO_ROOT / "tests" / "test_integration_retrieval_gate.py").read_text()

    assert "seed(store, DEV_ROOT, ledger_store(ledger_path(DEV_ROOT)))" in source
    assert "seed(store, DEV_ROOT)\n" not in source, "the empty-ledger call is the red one"
