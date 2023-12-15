#!/usr/bin/python3

# import cmake_presets as cmp  # type: ignore
import logging
import sys

from cmake_presets.util import EnvDict, execute_env_script

log = logging.getLogger(__name__)


def _ml_script():
    if sys.platform == "win32":
        return """setlocal EnableDelayedExpansion
set LF=^


rem two blank lines needed above
set MULTI=Line 1!LF!Line 2!LF!Last line
"""
    return ""


def test_env_multiline() -> None:
    script = _ml_script()
    if script:
        runenv = EnvDict.os()
        runenv["AAA_BEGIN"] = "Begin"
        runenv["ZZZ_END"] = "End"
        outenv = execute_env_script(script, runenv=runenv)
        # log.debug(outenv)
        assert outenv
        assert outenv["AAA_BEGIN"] == "Begin"
        assert outenv["ZZZ_END"] == "End"

        lines = outenv["MULTI"].splitlines()
        assert lines[0] == "Line 1"
        assert lines[1] == "Line 2"
        assert lines[2] == "Last line"
