#!/usr/bin/python3

import pytest

from typing import Set
# from cmake_presets.toolkit import get_toolkits


@pytest.fixture
def toolkit_names() -> Set[str]:
    return {
        "MSVCToolkit",
        "GCCToolkit",
        "OneAPIToolkit",
        "BatScriptToolkit",
        "ShellScriptToolkit",
    }


def test_toolkits_register(toolkit_names: Set[str]) -> None:
    import cmake_presets as cmp

    toolkits = cmp.get_toolkits()
    for t in toolkits.keys():
        assert t in toolkit_names
    assert len(toolkits) == len(toolkit_names)


if __name__ == "__main__":
    import logging
    import os
    import sys

    sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..", "src")))
    logging.basicConfig(
        format="Testing-%(levelname)s: %(message)s", level=logging.DEBUG
    )

    import cmake_presets as cmp

    for t in cmp.get_toolkits():
        print(t)
