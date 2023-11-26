import logging
from inspect import isabstract
from argparse import ArgumentParser

from .toolkit import ToolkitError, get_toolkits
#from .util import merge_presets
#from .presets import generate_presets_file

def main() -> int:
    print(__package__)
    log = logging.getLogger("cmake_package")


    parser = ArgumentParser()
    parser.add_argument(
        "command",
        choices=["generate", "list", "scan", "select"],
        default="scan",
        nargs="?",
        help="command (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-bad", action="store_true", help="Report toolkit error but continue"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Write verbose messages"
    )

    for cls in get_toolkits().values():
        if isabstract(cls):
            continue
        if not cls.IsSupported():
            continue
        prefix = cls.WithArguments()
        if prefix:
            group = parser.add_argument_group(cls.GetToolkitName() + " options")
            # TODO Wrap group in a Callable that interfers and force prefix
            cls.AddArguments(prefix, group)
    args = parser.parse_args()

    # print("command: " + args.command)

    if args.command == "list":
        log.info("Toolkits:")
        for cls in get_toolkits().values():
            if args.verbose or cls.IsSupported():
                suffix = (
                    "" if cls.IsSupported() else " - not supported on this platform"
                )
                log.info(" * %s%s", cls.GetToolkitName(), suffix)
    elif args.command == "scan" or args.command == "select":
        select = args.command == "select"
        for name, cls in get_toolkits().items():
            if not cls.IsSupported():
                continue
            prefix = cls.WithArguments()
            if not prefix:
                continue
            # TODO extract args only for this toolkit according to prefix
            try:
                toolkit = cls.FromArgs(prefix, args)
                toolkit.Scan(select=select, verbose=args.verbose)
            except ToolkitError as e:
                if args.skip_bad:
                    log.warning("Skipping toolkit %s due to error:\n{%s}", name, str(e))
                else:
                    raise e

if __name__ == "__main__":
    main()
