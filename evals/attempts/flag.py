"""Set one flagd flag's default variant, in place, and say what it was.

    python3 evals/attempts/flag.py productCatalogFailure on
    python3 evals/attempts/flag.py productCatalogFailure off

Edits world-v2/src/flagd/demo.flagd.json by truncate-and-write so the inode is kept. flagd mounts
the DIRECTORY (`./src/flagd:/etc/flagd`) so a rename would have been safe too; this is belt and
braces after 2026-09-22's single-file bind mount cost a baseline.
"""

from __future__ import annotations

import json
import pathlib
import sys

FLAGS = (
    pathlib.Path(__file__).resolve().parents[2] / "world-v2" / "src" / "flagd" / "demo.flagd.json"
)


def main() -> None:
    name, variant = sys.argv[1], sys.argv[2]
    doc = json.loads(FLAGS.read_text())
    flag = doc["flags"][name]
    if variant not in flag["variants"]:
        sys.exit(f"{name}: no variant {variant!r}; it has {sorted(flag['variants'])}")
    previous = flag["defaultVariant"]
    flag["defaultVariant"] = variant
    with FLAGS.open("w") as handle:  # truncate in place; the inode does not change
        json.dump(doc, handle, indent=2)
        handle.write("\n")
    print(f"{name}: {previous} -> {variant}  ({FLAGS.relative_to(FLAGS.parents[3])})")


if __name__ == "__main__":
    main()
