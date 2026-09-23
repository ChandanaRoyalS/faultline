"""Colour for the attempt helpers' output, and nothing else.

Firing alerts, error ratios over the rule's 5 %, p95s over its 250 ms and containers that are not
running are painted red or yellow; a quiet poll is green. Only when stdout is a terminal and
`NO_COLOR` is unset, so a `| tee transcript.txt` or a paste stays plain text. 3.9-safe, stdlib only.
"""

from __future__ import annotations

import os
import sys

_ON = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _wrap(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ON else text


def red(text: str) -> str:
    return _wrap("31;1", text)


def yellow(text: str) -> str:
    return _wrap("33", text)


def green(text: str) -> str:
    return _wrap("32", text)


def dim(text: str) -> str:
    return _wrap("2", text)
