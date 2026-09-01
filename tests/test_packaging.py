"""Repository data the runtime resolves at run time must exist in the image.

`faultline.context.allowlist.catalog_path()` and `faultline.migrate.ini_path()` both walk up
from the installed package looking for a repository directory. That resolves in a clone and in
an editable install, and resolved in *nothing* inside the container image, which copied only
`src`. Neither loader had a caller yet, so the failure was waiting for a deployment.

The rule this file enforces: if the runtime finds a file by walking up, the image ships it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_DATA = {
    "alembic.ini": "faultline.migrate.ini_path()",
    "migrations": "the revision history alembic.ini points at",
    "knowledge": "faultline.context.allowlist.catalog_path()",
}


def test_the_image_ships_every_file_the_runtime_walks_up_to_find() -> None:
    dockerfile = Path("Dockerfile").read_text()
    for name, resolver in REPO_DATA.items():
        assert re.search(rf"^COPY .*\b{re.escape(name)}\b", dockerfile, re.MULTILINE), (
            f"{name} is resolved at run time by {resolver} and is not copied into the image, "
            "so it exists in a clone and not in a container"
        )
