import os
import platform
import re
import subprocess
import logging
from functools import total_ordering
from typing import List, Set, Dict, Union, TypeVar, Sequence
from argparse import _ArgumentGroup

from .toolkit import Toolkit
from .util import Version, EnvDict, ScanError, expand_dirs
from .util import override  # Compatibility imports

log = logging.getLogger(__name__)
GCCType = TypeVar("GCCType", bound="GCC")
GCCToolkitType = TypeVar("GCCToolkitType", bound="GCCToolkit")


def gcc_version(val: str) -> Union[Version, None]:
    return Version.make(val, minlen=1, maxlen=3)


# --------------------------- Scan worker function --------------------------- #
# Support naming styles:
# * NAME
# * NAME-7
# * x86_64-pc-linux-gnu-NAME
# * x86_64-pc-linux-gnu-NAME-8.2.0
# * x86_64-redhat-linux-NAME
# so:
# * (NAME)(-VER)?
# * (TARGET-MACHINE-)?(NAME)(-VER)?
#
# Where NAME is exactly any of gcc, g++ or gfortran
#
# Suffix may only be (-[0-9\.]+)?
# Some suffix -ar, -nm or -ranlib should only possibly be
# considered to determine a "complete" gcc pack
#
# TODO Also, only executables and not symlinks are considered.
#      Result may look strange to users... We might reconsider
# ---------------------------------------------------------------------------- #

_SYSTEM = r"^([a-zA-Z0-9_]+-[a-zA-Z0-9_\-]+-)?"
_NAME = r"(gcc|g\+\+|gfortran)"
_VERSION = r"(-[0-9\.]+)?$"
re_bin = re.compile(_SYSTEM + _NAME + _VERSION)

# Construct map of findings
# dir -> fn_id -> [gcc_fn, gxx_fn, gfortran_fn]
# Where: fn_id = '_' + machine + ver (from filename only)
GccCollection = Dict[str, Dict[str, List[str]]]


def _scandir(path: str, dest: GccCollection) -> None:
    try:
        in_bin = os.path.basename(path) == "bin"
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    _scandir(entry.path, dest)
                elif in_bin and entry.is_file(follow_symlinks=False):
                    m = re_bin.match(entry.name)
                    if not m:
                        continue
                    machine = m.group(1)
                    name = m.group(2)
                    version = m.group(3)

                    fn_id = str(machine) + str(version)  # OK with "NoneNone"
                    if path not in dest:
                        dest[path] = {}
                    if fn_id not in dest[path]:
                        dest[path][fn_id] = ["", "", ""]
                    idx = ["gcc", "g++", "gfortran"].index(name)
                    if idx < 0:
                        log.debug("Unexpected binary matched: %s", entry.name)
                    else:
                        dest[path][fn_id][idx] = entry.name

    except PermissionError:
        log.warning("No permissions to scan: %s", path)


@total_ordering
class GCC:
    def __init__(self, dir: str) -> None:
        self.dir: str = dir
        self.gcc: str = ""
        self.gxx: str = ""
        self.gfortran: str = ""
        self.machine: str = ""
        self.version: Version = Version(None)

    def gcc_path(self) -> str:
        if self.gcc:
            return os.path.join(self.dir, self.gcc)
        return ""

    def gxx_path(self) -> str:
        if self.gcc:
            return os.path.join(self.dir, self.gxx)
        return ""

    def gfortran_path(self) -> str:
        if self.gcc:
            return os.path.join(self.dir, self.gfortran)
        return ""

    def __lt__(self, other: GCCType) -> bool:
        if self.version != other.version:
            return self.version < other.version
        if self.machine != other.machine:
            return self.machine < other.machine
        if bool(self.gfortran) != bool(other.gfortran):
            if other.gfortran:
                return True
            return False
        return False  # Equal

    def __eq__(self, other: GCCType) -> bool:
        return (
            self.version == other.version
            and self.machine == other.machine
            and bool(self.gfortran) == bool(other.gfortran)
        )

    def string(self, detailed: bool = False, fortran: bool = True) -> None:
        if not log.isEnabledFor(logging.INFO):
            return
        if detailed:
            log.info(" Product: GNU Compiler Collection %s", self.version.major)
            log.info(" Version: %s", self.version)
            log.info(" Machine: %s", self.machine)
            log.info("      cc: %s", self.gcc_path())
            log.info("     g++: %s", self.gxx_path())
            if fortran:
                log.info("gfortran: %s", self.gfortran_path())
        else:
            lang = "C/C++"
            if fortran and self.gfortran:
                lang += " and Fortran"
            log.info(" * Product: GNU Compiler Collection %s", self.version.major)
            log.info("       Version: %s", self.version)
            log.info("     Languages: %s", lang)

    def set_binaries(
        self, gcc: str, gxx: str, gfortran: Union[str, None], test: bool = False
    ) -> bool:
        if test:
            if not self.test_bin(gcc):
                return False
            if not self.test_bin(gxx):
                return False
            if not self.test_bin(gfortran):
                # Remove it and continue
                gfortran = None
        self.gcc = gcc
        self.gxx = gxx
        self.gfortran = gfortran if gfortran else ""
        return True

    def test_bin(self, name: str) -> bool:
        # Any binary (since tested 4.8.5) outputs:
        # XXX -dumpversion      -> major version or full version
        # XXX -dumpfullversion  -> full version, if flag is supported
        # XXX -dumpmachine      -> target arch + system like prefixed above
        # XXX --version         -> First line contains full version but varying formats...
        #                       -> Second line always contains copyright "Free Software Foundation"
        # NOTE: -dumpfullversion -dumpversion  # Seem to properly report full version for all GCC

        if not name:
            return False
        try:
            debug = log.isEnabledFor(logging.DEBUG)
            fn = os.path.join(self.dir, name)
            cmd = [fn, "--version"]
            lines = subprocess.check_output(cmd).decode().splitlines()  # noqa: S603
            if len(lines) < 2:
                if debug:
                    log.debug("INFO: Could not read version of %s", fn)
                return False
            l2 = lines[1].strip()
            if "Free Software Foundation" not in l2:
                if debug:
                    s = (
                        "Could not read copyright of %s. Expected 'Free Software foundation' on line 2:\n"
                        "    " + l2
                    )
                    log.debug(s, fn)
                return False

            if debug:
                log.debug("%s version reports:", fn)

            cmd = [fn, "-dumpfullversion", "-dumpversion"]
            lines = subprocess.check_output(cmd).decode().splitlines()  # noqa: S603
            if len(lines) != 1:
                return False
            verstr = lines[0].strip()
            ver = Version.make_safe(verstr, minlen=3)
            if not ver and debug:
                log.debug(
                    "Could not read version of %s. Expected full 3 digit version: %s",
                    fn,
                    verstr,
                )
                return False

            if not self.version:
                self.version = ver
            elif self.version != ver:
                if debug:
                    log.debug(
                        "ERROR: %s version mismatch: %s != %s", fn, self.version, ver
                    )
                return False

            if self.machine:
                return True

            # Only consider machine from one binary
            cmd = [fn, "-dumpmachine"]
            lines = subprocess.check_output(cmd).decode().splitlines()
            if len(lines) != 1:
                return False
            self.machine = lines[0].strip()
            return True

        except subprocess.CalledProcessError:
            return False
        except ValueError:
            return False

    def is_meta_equal(self, other: GCCType) -> bool:
        return (
            self.dir == other.dir
            and self.version == other.version
            and self.machine == other.machine
        )

    def keep_meta(self, other: GCCType) -> GCCType:
        # Both must have gcc and g++
        if not self.gfortran or not other.gfortran:
            if self.gfortran:
                return self  # type: ignore
            return other
        # Keep the one with shortest path... :')
        mlen = len(self.gcc) + len(self.gxx) + len(self.gfortran)
        olen = len(other.gcc) + len(other.gxx) + len(other.gfortran)
        if mlen < olen:
            return self  # type: ignore
        return other

    @classmethod
    def scan(
        cls, dirs: List[str] = None, extra_dirs: List[str] = None
    ) -> List[GCCType]:
        if not dirs:
            dirs = [
                "/bin",
                "/usr/bin",
                "/usr/local",  # check for any folder named 'bin'
                "/opt",
                "$HOME",
            ]

        scan_dirs = expand_dirs(dirs)
        if extra_dirs:
            os.scandir()
            scan_dirs.extend(expand_dirs(extra_dirs))
        scan_dirs = list(set(scan_dirs))  # remove duplicates, don't care for order

        log.debug("GCC Scan directories:")
        for dir in scan_dirs:
            log.debug(dir)

        found: GccCollection = {}
        for dir in scan_dirs:
            if os.path.isdir(dir):
                _scandir(dir, dest=found)

        products = []
        for dir in found:
            for vals in found[dir].values():
                # Keep only those where gcc and g++ is paired
                # gfortran may be missing as this is filtered out later
                if not (vals[0] and vals[1]):
                    continue

                obj = GCC(dir)
                if not obj.set_binaries(
                    gcc=vals[0],
                    gxx=vals[1],
                    gfortran=vals[2],
                    test=True,
                ):
                    continue

                idx_match = -1
                for idx, other in enumerate(products):
                    if obj.is_meta_equal(other):
                        idx_match = idx
                        break
                if idx_match == -1:
                    products.append(obj)
                else:
                    other = products[idx_match]
                    keep = obj.keep_meta(other)
                    if keep == obj:
                        products[idx_match] = obj  # Replace

        products.sort(reverse=True)
        return products


class GCCToolkit(Toolkit):
    def __init__(
        self,
        name: str = "",
        ver: str = "",
        fortran: bool=False,
        scan_dirs: List[str] = None,
        scan_extradirs: List[str] = None,
    ) -> None:
        self.version: Version = gcc_version(ver)
        self.with_fortran: bool = fortran
        self.scan_dirs: List[str] = scan_dirs
        self.scan_extradirs: List[str] = scan_extradirs

        self._found: List[GCC] = []

        required_vars: Set[str] = {"CC", "CXX"}
        if fortran:
            required_vars.add("FC")

        if not name:
            parts: List[str] = []
            if self.version:
                parts.append(f"gcc{self.version.joined()}")
            else:
                parts.append("gcc_latest")
            name = "_".join(parts)

        super().__init__(name, required_vars)

    @override
    @staticmethod
    def is_supported() -> bool:
        return platform.system() == "Linux"

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "GCC"

    @override
    @staticmethod
    def _get_argument_prefix() -> str:
        return "gcc_"

    @override
    @staticmethod
    def _add_arguments(prefix: str, parser: _ArgumentGroup) -> None:
        parser.add_argument(
            f"--{prefix}ver",
            default=None,
            metavar="VER",
            type=gcc_version,
            help="GCC Version. Can be in form 8, 8.2 or 8.2.0",
        )
        parser.add_argument(
            f"--{prefix}fortran",
            action="store_true",
            help="Flag to specify if GNU Fortran is needed",
        )
        parser.add_argument(
            f"--{prefix}dir",
            default=[],
            metavar="DIR",
            type=str,
            action="append",
            help="Search dir to override default search. Multiple allowed",
        )
        parser.add_argument(
            f"--{prefix}extradir",
            default=[],
            metavar="DIR",
            type=str,
            action="append",
            help="Search dir to extend default search. Multiple allowed",
        )

    @override
    @classmethod
    def _from_args(cls, prefix: str, args: Sequence[str]) -> GCCToolkitType:
        ver = getattr(args, prefix + "ver")
        fortran = getattr(args, prefix + "fortran")
        dirs = getattr(args, prefix + "dir")
        extra_dirs = getattr(args, prefix + "extradir")
        return cls(ver=ver, fortran=fortran, scan_dirs=dirs, scan_extradirs=extra_dirs)

    @override
    def scan(self, select: bool=False, verbose: bool=False) -> bool:
        try:
            products: List[GCC] = self.filter(
                GCC.scan(dirs=self.scan_dirs, extra_dirs=self.scan_extradirs)
            )
            if select:
                best = self.select(products)
                products = []
                if best:
                    products.append(best)
            for product in products:
                s = product.string(fortran=self.with_fortran)
                if s:
                    print(s)
        except ScanError as e:
            if verbose:
                print(str(e))
            return False
        self._found = products
        return bool(products)

    def filter(self, products: List[GCC]) -> List[GCC]:
        if not self.version or self.with_fortran:
            return products

        left = []
        for product in products:
            if self.with_fortran and not product.gfortran:
                continue
            if not self.version.parts_equal(product.version):
                continue
            left.append(product)
        return left

    def select(self, products: List[GCC]) -> Union[GCC, None]:
        # Already filtered and sorted
        if products:
            return products[0]
        return None

    @override
    def _add_post_env_vars(self, env: EnvDict) -> None:
        product = self._found[0]
        env.prepend_path("PATH", product.dir)
        env["CC"] = product.gcc_path()
        env["CXX"] = product.gxx_path()
        if self.with_fortran:
            env["FC"] = product.gfortran_path()