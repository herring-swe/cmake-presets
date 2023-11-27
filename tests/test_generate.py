#!/usr/bin/python3

import sys
from typing import Tuple, Set

from cmake_presets import (  # type: ignore
    GCCToolkit,
    MSVCToolkit,
    OneAPIToolkit,
    ToolkitChain,
    generate_presets_file,
)


def main(skip_bad: bool = False) -> Tuple[Set[str], Set[str], Set[str]]:
    static_presets = [
        {
            "name": "env_base",
            "hidden": True,
            "environment": {
                "POCO_GCC82": "/ansysdev/cmake_deps/gcc82/poco-current",
                "WX3_GCC82_DEBUG": "/ansysdev/cmake_deps/gcc82/wx3-current-debug",
                "WX3_GCC82_RELEASE": "/ansysdev/cmake_deps/gcc82/wx3-current-release",
                "POCO_VS2019": "C:/ansysdev/cmake_deps/vs2019/poco-current",
                "WX3_VS2019": "C:/ansysdev/cmake_deps/vs2019/wx3-current",
            },
        }
    ]

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
        static_presets=static_presets,
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

    logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)
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
