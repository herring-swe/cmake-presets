import sys
import logging
from inspect import isabstract
from argparse import ArgumentParser

from .toolkit import ToolkitError, get_toolkits


class CLIFormatter(logging.Formatter):
    GREY = "\x1b[38;21m"
    YELLOW = "\x1b[33;21m"
    RED = "\x1b[31;21m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    DEBUG = logging.Formatter(f"{GREY}%(levelname)s - %(name)s{RESET}: %(message)s")
    INFO = logging.Formatter("%(message)s")
    WARNING = logging.Formatter(f"{YELLOW}%(levelname)s{RESET}: %(message)s")
    ERROR = logging.Formatter(f"{RED}%(levelname)s{RESET}: %(message)s")
    CRITICAL = logging.Formatter(f"{BOLD_RED}%(levelname)s{RESET}: %(message)s")

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
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(CLIFormatter())

    log = logging.getLogger(__package__)
    log.addHandler(ch)
    log.setLevel(logging.DEBUG)

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
        "--skip-bad", action="store_true", help="Report toolkit error but continue"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Write verbose messages"
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

    # print("command: " + args.command)

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
                if not toolkit.scan(select=select):
                    log.info("No instances found for %s", toolkit.get_toolkit_name())
            except ToolkitError as e:
                if args.skip_bad:
                    log.warning("Skipping toolkit %s due to error:\n{%s}", name, str(e))
                else:
                    raise e


if __name__ == "__main__":
    main()
