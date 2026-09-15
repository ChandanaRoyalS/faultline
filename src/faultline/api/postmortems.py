"""The postmortem accept route (T6.5, piece 2).

`evals/runs/PREREGISTRATION-T6.5.md` §3: **a person, through the approval surface** - ADR-0039's
shape reused rather than re-invented. A route behind T5.5's credential, the caller recorded as
the authenticated username, an append-only ledger row, and the seeder refusing any postmortem
without one.

## The submitted text is the accepted text

`POST /api/v1/postmortems/{scenario_id}/accept` takes the **document** in its body, not a
reference to one. The plan's clause is *"post-resolution draft for human edit"*, so the thing a
person accepts is what they finished editing - and a route that accepted by id would be
accepting whatever was on a disk it could not see, which is the gate's failure mode with extra
steps.

Every guard in `context/postmortem.py` runs here before any row is written: the closed section
list, the origin check, the remediation ban, ADR-0036's scenario-name ban. A leaking postmortem
is a **422**, not a row. That makes this route the place where the leak guard is actually
enforced against a human's edit, which is where the registration's prediction 6 - *no postmortem
trips the leak guard on its first draft*, registered as the one expected to fail - gets scored.

## It does not write the file, and that is on purpose

The row pins a digest; the document reaches the corpus as a file in the dev bundle, committed to
git like every narrative and every runbook. **Two reasons.** The API process would otherwise need
write access to repository data, which `knowledge/`'s read-only-by-construction rule (ADR-0032)
exists to avoid - and a corpus document that appeared on a server's disk without a commit would
be the one class of document in this system with no review history.

So: accept produces a row, a person commits the file, and `faultline-seed` refuses if the two
disagree by a single word.

## Mounted with the read surface, not with the write surface

`app.write_surface` returns early when the executor's token key is unset, because approve and
reject are useless without an executor. Accepting a postmortem has nothing to do with the
executor, and gating it on that key would make a deployment that never executes anything unable
to accept a document either.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from faultline.context.acceptance import NOTE_LIMIT, Acceptance, AcceptanceStore, digest_of
from faultline.context.postmortem import PostmortemError, parse_postmortem_text

log = logging.getLogger(__name__)


class AcceptBody(BaseModel):
    document: str = Field(min_length=1)
    """The finished postmortem, front matter and all - the text a person just edited."""

    note: str = Field(default="", max_length=NOTE_LIMIT)


def build(
    *,
    acceptances: AcceptanceStore,
    caller: Any,
    scenario_ids: set[str] | None = None,
) -> APIRouter:
    """The accept route.

    `caller` is the `params.Depends` `auth.guard()` returns, used as the default of `who`, so the
    name in the ledger is the name the credential proved and no request body can set it.

    `scenario_ids` is the catalog, passed in for ADR-0036's ban. `None` means the check does not
    run, which is right for a unit test and wrong for a deployment - `app.py` passes the catalog.
    """
    router = APIRouter(prefix="/api/v1/postmortems")

    @router.post("/{scenario_id}/accept")
    def accept(
        scenario_id: str,
        body: AcceptBody,
        who: str = caller,
    ) -> dict[str, Any]:
        try:
            postmortem = parse_postmortem_text(body.document, scenario_ids=scenario_ids)
        except PostmortemError as refusal:
            # 422 rather than 400: the document is well-formed input that fails the rules this
            # corpus imposes on it, and the message says which rule. A leak is not a typo.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refusal)) from refusal

        if postmortem.scenario_id != scenario_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"the document is for {postmortem.scenario_id!r} and the route named "
                f"{scenario_id!r}. `origin` is the exclusion key, so accepting this under the "
                "wrong scenario would admit it to the corpus of the incident it is about.",
            )

        row = Acceptance(
            scenario_id=postmortem.scenario_id,
            body_digest=digest_of(postmortem),
            caller=who,
            note=body.note,
        )
        acceptances.append(row)
        log.info(
            "postmortem for %s accepted by %s (%s)",
            row.scenario_id,
            who,
            row.body_digest[:12],
        )
        # **The digest is returned.** A person who accepted a draft needs to be able to tell
        # whether the file they commit is the one they accepted, and this is the only number
        # that answers it.
        return {"accepted": row.as_dict()}

    return router
