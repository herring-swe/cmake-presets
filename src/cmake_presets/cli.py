import logging
import sys
from argparse import ArgumentParser
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

    parser = ArgumentParser()
    parser.add_argument(
        "command",
        choices=["generate", "list", "scan", "select"],
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
    elif args.command == "scan" or args.command == "select":
        select = args.command == "select"
        for name, cls in get_toolkits().items():
            if not cls.is_supported():
                continue
            prefix = cls._get_argument_prefix()
            if not prefix:
                continue
            try:
                # TODO extract args only for this toolkit according to prefix
                toolkit = cls._from_args(prefix, args)
                if toolkit.scan(select=select):
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
