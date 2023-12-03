import logging
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from inspect import isabstract

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

    # parser = ArgumentParser(epilog=epilog, formatter_class=RawTextHelpFormatter)
    parser = ArgumentParser(add_help=False)
    parser.add_argument(
        "command",
        choices=["generate", "list", "scan", "filter", "select"],
        default="scan",
        nargs="?",
        help="command (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-bad", action="store_true", help="report toolkit error but continue"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show more information"
    )
    parser.add_argument("--debug", action="store_true", help="show debug messages")
    parser.add_argument(
        "-h",
        "--help",
        action="store",
        metavar="SECTION",
        nargs="?",
        default="_nospec",
        choices=[None] + [str(key) for key in help_sections.keys()],
        help=f"show help message and exit. possible sub-sections: {', '.join(help_sections.keys())}",
    )

    for cls in get_toolkits().values():
        if isabstract(cls):
            continue
        if not cls.is_supported():
            continue
        prefix = cls._get_argument_prefix()
        if prefix:
            group = parser.add_argument_group(cls.get_toolkit_name() + " options")
            # TODO Wrap group in a Callable that interfers and force prefix
            cls._add_arguments(prefix, group)
    args = parser.parse_args()

    if args.help != "_nospec":
        if args.help in help_sections:
            print(help_sections[args.help])
        else:
            parser.print_help()
        sys.exit(0)

    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.command == "list":
        log.info("Toolkits:")
        for cls in get_toolkits().values():
            if args.verbose or cls.is_supported():
                suffix = (
                    "" if cls.is_supported() else " - not supported on this platform"
                )
                log.info(" * %s%s", cls.get_toolkit_name(), suffix)
    elif args.command in ["scan", "filter", "select"]:
        for name, cls in get_toolkits().items():
            if not cls.is_supported():
                continue
            prefix = cls._get_argument_prefix()
            if not prefix:
                continue
            try:
                # TODO extract args only for this toolkit according to prefix
                toolkit = cls._from_args(prefix, args)
                if args.command == "select":
                    okay = toolkit.scan_select() > 0
                elif args.command == "filter":
                    okay = toolkit.scan_filter() > 0
                else:
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


if __name__ == "__main__":
    main()
