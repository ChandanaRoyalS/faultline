"""Gate 0's walking skeleton: the packages import and carry a version."""

import faultline


def test_version() -> None:
    assert faultline.__version__ == "0.0.1"
