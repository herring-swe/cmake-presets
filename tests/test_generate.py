#!/usr/bin/python3

import sys
from typing import List, Set, Tuple

from cmake_presets import (  # type: ignore
    GCCToolkit,
    MSVCToolkit,
    OneAPIToolkit,
    Toolkit,
    ToolkitChain,
    generate_presets_file,
)

# TODO System dependent tests. Need to make mockup data


def main(skip_bad: bool = False) -> Tuple[Set[str], Set[str], Set[str]]:
    msvc = MSVCToolkit(name="vs2019", ver="2019", tools="v142")
    gcc = GCCToolkit(name="gcc820", ver="8.2.0", fortran=False)
    oneapi = OneAPIToolkit(
        name="oneapi2021", ver="2021.3.0", fortran="ifort", components=["mkl"]
    )

    output_file = "user_presets.json"
    toolkits = [
        msvc,
        gcc,
        oneapi,
        ToolkitChain([gcc.copy(), oneapi.copy()]),
        ToolkitChain([msvc.copy(), oneapi.copy()]),
    ]
    added, skipped, errors = generate_presets_file(
        output_file,
        toolkits,
        skip_bad=skip_bad,
    )
    return (added, skipped, errors)


if __name__ == "__main__":
    import logging
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument(
        "-s",
        "--skip",
        action="store_true",
        help="skip a toolkit with errors instead of halting",
    )
    log = parser.add_mutually_exclusive_group()
    log.add_argument(
        "-v", "--verbose", action="store", dest="loglevel", help="write more info"
    )
    log.add_argument(
        "-q", "--quiet", action="store", dest="loglevel", help="write less info"
    )

    loglevel = logging.INFO
    args = parser.parse_args()
    if args.loglevel == "verbose":
        loglevel = logging.DEBUG
    if args.loglevel == "quiet":
        loglevel = logging.ERROR

    # logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)
    main(args.skip)


def test_generate_main() -> None:
    added, skipped, errors = main(skip_bad=False)

    assert len(errors) == 0
    assert len(added) + len(skipped) == 5
    if sys.platform == "win32":
        assert len(added) == 2
    elif sys.platform == "linux":
        assert len(added) == 3
    else:
        raise AssertionError("Unsupported OS")


def test_dual_chain() -> None:
    static_presets = [
        {
            "name": "env_base",
            "hidden": True,
            "environment": {
                "COMMON_DEP1": "/users/path/to/dep1",
                "COMMON_DEP2": "/users/path/to/dep2",
            },
        }
    ]

    output_file = "user_presets.json"
    toolkits: List[Toolkit] = [
        ToolkitChain(
            name="vs2019_oneapi2021_3",
            toolkits=[
                MSVCToolkit(ver="2019"),
                OneAPIToolkit(ver="2021.3.0", fortran="ifort", components=["mkl"]),
            ],
        ),
        ToolkitChain(
            name="gcc820_oneapi2021_3",
            toolkits=[
                GCCToolkit(ver="8.2.0"),
                OneAPIToolkit(ver="2021.3.0", fortran="ifort", components=["mkl"]),
            ],
        ),
    ]
    added, skipped, errors = generate_presets_file(
        output_file, toolkits, static_presets=static_presets, detailed_kit_info=False
    )

    assert len(errors) == 0
    assert len(added) + len(skipped) == 2
    if sys.platform == "win32":
        assert len(added) == 1
    elif sys.platform == "linux":
        assert len(added) == 1
