import logging
import sys
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from inspect import isabstract
from typing import Dict, Union

from .toolkit import ToolkitError, get_toolkits


class CLIFormatter(logging.Formatter):
    # Windows 10 added ANSI color support so let's assume this is okay.
    # 256 color should be perfectly fine as well
    # fmt: off
    WHITE       = "\x1b[0;37m"
    YELLOW      = "\x1b[0;33m"
    RED         = "\x1b[0;31m"
    BOLD_RED    = "\x1b[1;31m"
    RESET       = "\x1b[0m"
    CYAN        = "\x1b[0;36m"
    SEP         = WHITE + ":" + RESET
    # fmt: on

    DEBUG = logging.Formatter(
        f"{WHITE}%(levelname)s - {CYAN}%(name)s{RESET}{SEP} %(message)s"
    )
    INFO = logging.Formatter("%(message)s")
    WARNING = logging.Formatter(f"{YELLOW}%(levelname)s{RESET}{SEP} %(message)s")
    ERROR = logging.Formatter(f"{RED}%(levelname)s{RESET}{SEP} %(message)s")
    CRITICAL = logging.Formatter(f"{BOLD_RED}%(levelname)s{RESET}{SEP} %(message)s")

    def __init__(self) -> None:
        super().__init__(style="%")

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno <= logging.DEBUG:
            return CLIFormatter.DEBUG.format(record)
        elif record.levelno <= logging.INFO:
            return CLIFormatter.INFO.format(record)
        elif record.levelno <= logging.WARNING:
            return CLIFormatter.WARNING.format(record)
        elif record.levelno <= logging.ERROR:
            return CLIFormatter.ERROR.format(record)
        else:
            return CLIFormatter.CRITICAL.format(record)


def setup_cli_logging() -> logging.Logger:
    ch = logging.StreamHandler(sys.stdout)
    # ch.setLevel(logging.DEBUG)
    ch.setFormatter(CLIFormatter())

    log = logging.getLogger(__package__)
    log.addHandler(ch)
    log.setLevel(logging.INFO)

    return log


def _scan_common(log: logging.Logger, args: Namespace) -> None:
    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.cmd == "list":
        log.info("Toolkits:")
        for cls in get_toolkits().values():
            if args.verbose or cls.is_supported():
                suffix = (
                    "" if cls.is_supported() else " - not supported on this platform"
                )
                log.info(" * %s%s", cls.get_toolkit_name(), suffix)
    elif args.cmd in ["scan", "filter", "select"]:
        for name, cls in get_toolkits().items():
            if not cls.is_supported():
                continue
            prefix = cls._get_argument_prefix()
            if not prefix:
                continue
            try:
                # TODO extract args only for this toolkit according to prefix
                if args.cmd == "select":
                    toolkit = cls._from_args(prefix, args)
                    okay = toolkit.scan_select() > 0
                elif args.cmd == "filter":
                    toolkit = cls._from_args(prefix, args)
                    okay = toolkit.scan_filter() > 0
                else:
                    toolkit = cls._from_args(prefix, None)
                    okay = toolkit.scan() > 0
                if okay:
                    toolkit.print(detailed=args.verbose)
                else:
                    log.info("No instances found for %s", toolkit.get_toolkit_name())
            except ToolkitError as e:
                if args.skip_bad:
                    log.warning("Skipping toolkit %s due to error:\n{%s}", name, str(e))
                else:
                    raise e


def main() -> None:
    log = setup_cli_logging()

    help_sections = {
        "version": """Arguments that takes VER argument.

Version specification can be in the following forms (V = Version):
    V or =V or eqV      equal to V
    <V or ltV           less than V
    <= or lteV          less or equal to V
    >V or gtV           greater than V
    >=V or gteV         greater or equal to V

Ranges:
    VER1,VER2           two specifications of above which both needs to match.
                        can be used to define a range
    rangeV              A version range based on smallest number
                        range2.3  becomes >=2.3,<2.4

Version is defined in form major.minor.patch.revision, where major is required,
all parts are non-negative and at least one part is non-zero.

Version comparison will pad the shortest version with zeroes so that comparison
of 2.5 and 2.5.1 will be the comparison of 2.5.0 and 2.5.1. This means that 2.5
is not equal to 2.5.1. If the intent is to match a range 2.5 - 2.6, then the range
specifier range2.5 will accept all version 2.5.0 up to, but excluding, 2.6.0
"""
    }
    help_cmds: Dict["str", Union[None, ArgumentParser]] = {
        "scan": None,
        "filter": None,
        "select": None,
        "generate": None,
    }
    all_sections = help_sections.keys() | help_cmds.keys()

    parser = ArgumentParser(prog=__package__)
    sub = parser.add_subparsers(required=True, dest="cmd")

    sub.add_parser("list", aliases="l")
    help = sub.add_parser("help", help="show help section", add_help=False)
    help.add_argument(
        "section",
        metavar="SECTION",
        nargs="?",
        default=None,
        choices=[str(key) for key in all_sections],
        help=f"show help and exit. possible sections: {', '.join(all_sections)}",
    )
    scan = sub.add_parser("scan", aliases=["s"], help="scan and list all toolkits")
    filter = sub.add_parser(
        "filter", aliases=["f"], help="scan and list filtered toolkits"
    )
    select = sub.add_parser(
        "select", aliases=["sel"], help="scan and list best toolkit"
    )
    generate = sub.add_parser("generate", aliases=["gen"], help="generate presets")

    help_cmds["scan"] = scan
    help_cmds["filter"] = filter
    help_cmds["select"] = select
    help_cmds["generate"] = generate

    for p in [scan, filter, select, generate]:
        p.add_argument(
            "--skip-bad", action="store_true", help="report toolkit error but continue"
        )
        p.add_argument(
            "-v", "--verbose", action="store_true", help="show more information"
        )
        p.add_argument("--debug", action="store_true", help="show debug messages")

        if p == scan:
            continue

        for cls in get_toolkits().values():
            if isabstract(cls) or not cls.is_supported():
                continue
            prefix = cls._get_argument_prefix()
            if prefix:
                group = p.add_argument_group(cls.get_toolkit_name() + " options")
                # TODO Wrap group in a Callable that interfers and force prefix
                cls._add_arguments(prefix, group)

    args = parser.parse_args()

    if "cmd" not in args:
        if args.help_version:
            print(help_sections["version"])
            sys.exit(0)

    if args.cmd == "help":
        if args.section:
            if args.section in help_sections:
                print(help_sections[args.section])
            elif help_cmds[args.section] is not None:
                help_cmds[args.section].print_help()  # type: ignore
            else:
                log.error("unhandled section: %s", args.section)
        else:
            help.print_help()
        sys.exit(0)

    if args.cmd in ["scan", "filter", "select"]:
        _scan_common(log, args)
    else:
        log.error("generate not implemented")


if __name__ == "__main__":
    main()
