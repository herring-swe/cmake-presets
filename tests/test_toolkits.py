#!/usr/bin/python3

import pytest

from typing import Set
import cmake_presets as cmp
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
    toolkits = cmp.get_toolkits()
    for t in toolkits.keys():
        assert t in toolkit_names
    assert len(toolkits) == len(toolkit_names)
