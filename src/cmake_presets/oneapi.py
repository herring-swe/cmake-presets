import os
import sys
import platform
import logging
from functools import total_ordering
from typing import Dict, List, Set, Union, TypeVar, Sequence, Iterable, NamedTuple
from argparse import _ArgumentGroup

from .toolkit import Toolkit
from .msvc import MSVCToolkit
from .util import Version, ScanError, expand_dirs
from .util import override  # Compatibility imports

log = logging.getLogger(__name__)
OneAPIType = TypeVar("OneAPIType", bound="OneAPI")


def oneapi_version(val: str) -> Version:
    return Version.make(val, minlen=1, maxlen=3)


class _CompDirs(NamedTuple):
    rootdir: str
    version: Version
    varspath: str
    ifortpath: str
    ifxpath: str


@total_ordering
class OneAPI:
    COMPONENTS = ["compiler", "mkl", "tbb", "mpi"]
    FORTRAN = ["ifx", "ifort"]
    TARGET = "intel64"

    def __init__(self, dir: str) -> None:
        self.dir = dir
        self.version = None
        self.ifort = ""
        self.ifx = ""
        self.components: Dict[str, str] = {}

    def ifort_path(self) -> str:
        if self.ifort:
            return os.path.join(self.dir, self.ifort)
        return ""

    def ifx_path(self) -> str:
        if self.ifx:
            return os.path.join(self.dir, self.ifx)
        return ""

    def __lt__(self, other: OneAPIType) -> bool:
        if isinstance(other, OneAPI):
            return self.version < other.version
        return False

    def __eq__(self, other: OneAPIType) -> bool:
        if isinstance(other, OneAPI):
            return self.version == other.version
        return False

    def string(
        self,
        fortran: str = "any",
        components: List[str] = COMPONENTS,
        verbose: bool = False,
    ) -> str:
        print_comp = {c: path for c, path in self.components.items() if c in components}

        if verbose:
            s = (
                f"   Product: Intel oneAPI {self.version.major}\n"
                f"   Version: {self.version}\n"
            )
            if fortran in ["any", "ifx"]:
                s += f"       ifx: {self.ifx_path()}\n"
            if fortran in ["any", "ifort"]:
                s += f"     ifort: {self.ifort_path()}\n"
            s += "Components:\n"
            for name, path in print_comp.items():
                s += f"  - {name}: {path}\n"
        else:
            compilers = []
            if fortran in ["any", "ifx"]:
                compilers.append("ifx")
            if fortran in ["any", "ifort"]:
                compilers.append("ifort")
            s = (
                f" * Product: Intel oneAPI {self.version.major}\n"
                f"       Version: {self.version}\n"
                f"     Compilers: {', '.join(compilers)}\n"
                f"    Components: {', '.join(print_comp)}"
            )
        return s

    @override
    @classmethod
    def scan(cls, root_dir: str = "", verbose: bool = False) -> List[OneAPIType]:
        if root_dir:
            dirs = [root_dir]
        else:
            dirs = []

        if "ONEAPI_ROOT" in os.environ:
            dirs.append(os.environ["ONEAPI_ROOT"])

        if platform.system() == "Linux":
            dirs.extend(["/opt/intel/oneapi", "$HOME/intel/oneapi"])
            osdir = "linux"
            scriptsuffix = ".sh"
            exesuffix = ""
        else:
            dirs.extend([r"%ProgramFiles(x86)%\Intel\oneAPI"])
            osdir = "windows"
            scriptsuffix = ".bat"
            exesuffix = ".exe"

        compdirs = _CompDirs()
        compdirs.ifortpath = os.path.join(
            osdir, "bin", OneAPI.TARGET, "ifort" + exesuffix
        )
        compdirs.ifxpath = os.path.join(osdir, "bin", "ifx" + exesuffix)
        compdirs.varspath = os.path.join("env", "vars" + scriptsuffix)

        scan_dirs = expand_dirs(dirs)
        scan_dirs = list(set(scan_dirs))  # remove duplicates, don't care for order

        if verbose:
            print("Scan directories:")
            for dir in scan_dirs:
                print(dir)

        products = []
        for rootdir in scan_dirs:
            allver = []
            if not os.path.isdir(rootdir):
                continue

            if verbose:
                print("Scanning: " + rootdir)

            for comp in OneAPI.COMPONENTS:
                compdir = os.path.join(rootdir, comp)
                if os.path.isdir(compdir):
                    for file in os.listdir(compdir):
                        ver = Version.make_safe(file, 3)
                        if ver and ver not in allver:
                            allver.append(ver)
            allver.sort(reverse=True)

            if verbose:
                print("Found potential versions:")
                for ver in allver:
                    print(f" * {ver}")

            for ver in allver:
                obj = cls._scan_version(rootdir, ver, compdirs)
                if obj is not None:
                    products.append(obj)

        products.sort(reverse=True)
        return products

    @classmethod
    def _scan_version(
        cls, rootdir: str, ver: Version, compdirs: _CompDirs
    ) -> Union[OneAPIType, None]:
        obj = OneAPI(rootdir)
        obj.version = ver
        found_comps = 0

        for name in OneAPI.COMPONENTS:
            comp_path = os.path.join(rootdir, name, str(ver))
            vars_path = os.path.join(comp_path, compdirs.varspath)
            if os.path.isdir(vars_path):
                found_comps += 1
                obj.components[name] = vars_path
                if name == "compiler":
                    ifort_path = os.path.join(comp_path, compdirs.ifortpath)
                    log.debug("Checking for ifort: %s", ifort_path)
                    if os.path.exists(ifort_path):
                        obj.ifort = ifort_path
                    ifx_path = os.path.join(comp_path, compdirs.ifxpath)
                    log.debug("Checking for ifx: %s", ifx_path)
                    if os.path.exists(ifx_path):
                        obj.ifx = ifx_path
        if found_comps:
            return obj
        return None


class OneAPIToolkit(Toolkit):
    VALID_FORTRAN = ["any"] + OneAPI.FORTRAN + ["none"]
    VALID_COMPONENTS = ["all"] + OneAPI.COMPONENTS

    def __init__(
        self,
        name: str = "",
        ver: str = "",
        fortran: str = "any",
        components: Union[str, Iterable[str]] = "all",
        root_dir: str = "",
    ) -> None:
        self.version: Version = oneapi_version(ver)
        self.fortran: str = fortran
        self.components: List[str] = []
        self.root_dir: str = root_dir
        self.scanned: List[OneAPI] = []

        if fortran in OneAPIToolkit.VALID_FORTRAN:
            if self.fortran == "none":
                self.fortran = ""
            else:
                self.fortran = fortran

        if components:
            if isinstance(components, str):
                components = [components]
            if "all" in components:
                self.components = OneAPI.COMPONENTS
            else:
                self.components = list(components)
                if self.fortran != "none" and "compiler" not in self.components:
                    self.components.insert(0, "compiler")
        self.root_dir = root_dir

        if not name:
            if self.version:
                parts = [f"oneapi{self.version.underscore()}"]
            else:
                parts = ["oneapi_latest"]
            name = "_".join(parts)

        required_vars = set()
        if self.fortran:
            required_vars.add("FC")

        super().__init__(name, required_vars)

    @override
    @staticmethod
    def is_supported() -> bool:
        return platform.system() in ["Linux", "Windows"]

    # def _is_compat_vs(self, tk):
    #     __oa2022_3 = Version(2022, 3)
    #     __v143: Version = build_tools_version("v143")
    #     __v142: Version = build_tools_version("v142")
    #     # __v141: Version = BuildToolsVersion('v141')

    #     if self.version:
    #         if self.version < __oa2022_3 and tk.vs_version >= 2022:
    #             if not tk.tools_version:
    #                 tk.tools_version = __v142  # Hint to use v142 build tools
    #             elif tk.tools_version >= __v143:
    #                 return False
    #         elif self.version >= __oa2022_3 and tk.vs_version <= 2017:
    #             return False
    #     return True

    def _get_vs_in_chain(self) -> Union[MSVCToolkit, None]:
        if self.in_chain():
            print("In chain")
            tk: Union[MSVCToolkit, None] = self.get_prev_toolkit()
            print(tk)
            while tk:
                print(tk)
                if isinstance(tk, MSVCToolkit):
                    return tk
                tk = tk.GetPreviousToolkit()
        print("Not in chain")
        return None

    @override
    def is_instance_supported(self) -> bool:
        if sys.platform != "win32":
            return True
        tk = self._get_vs_in_chain()
        if tk is None:
            log.error(
                "oneAPI: Requires Visual Studio or Visual Studio Build Tools but not found"
            )
            return False
        log.info("oneAPI: Found Visual Studio in chain")
        return True

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "Intel oneAPI"

    @override
    @staticmethod
    def _get_argument_prefix() -> str:
        return "oneapi_"

    @override
    @staticmethod
    def _add_arguments(prefix: str, parser: _ArgumentGroup) -> None:
        parser.add_argument(
            f"--{prefix}ver",
            default=None,
            metavar="VER",
            type=oneapi_version,
            help="oneAPI Version. Can be in form 2021, 2021.3 or 2021.3.1",
        )
        parser.add_argument(
            f"--{prefix}fortran",
            choices=["any", "ifx", "ifort", "none"],
            default="any",
            type=str,
            help="Flag to specify needed Intel Fortran compiler",
        )
        parser.add_argument(
            f"--{prefix}comp",
            default=[],
            metavar="DIR",
            action="append",
            choices=["all"] + OneAPI.COMPONENTS,
            help=f"Components needed. Valid choices: f{', '.join(['all'] + OneAPI.COMPONENTS)}",
        )
        parser.add_argument(
            f"--{prefix}dir",
            default="",
            metavar="DIR",
            type=str,
            help="Additional Intel oneAPI root DIR to search",
        )

    @override
    @classmethod
    def _from_args(cls, prefix: str, args: Sequence[str]) -> OneAPIType:
        ver = getattr(args, prefix + "ver")
        fortran = getattr(args, prefix + "fortran")
        dirs = getattr(args, prefix + "dir")
        components = getattr(args, prefix + "comp")
        if not components:
            components = ["all"]
        return cls(ver=ver, fortran=fortran, components=components, root_dir=dirs)

    @override
    def scan(self, select: bool = False) -> bool:
        try:
            products = self.filter(OneAPI.scan(root_dir=self.root_dir))
            if select:
                best = self.select(products)
                products = []
                if best:
                    products.append(best)
            for product in products:
                s = product.string(fortran=self.fortran, components=self.components)
                if s:
                    print(s)
        except ScanError as e:
            log.exception(e)
            return False
        self.scanned = products
        return bool(products)

    def filter(self, products: List[OneAPI]) -> List[OneAPI]:
        left = []
        for product in products:
            if self.fortran != "none":
                if product.ifort and not product.ifx:
                    continue
                elif self.fortran == "ifort" and not product.ifort:
                    continue
                elif self.fortran == "ifx" and not product.ifx:
                    continue
            found = True
            if "any" not in self.components:
                for prod in self.components:
                    if prod not in product.components:
                        found = False
                        break
            if not found:
                continue
            if self.version and not self.version.parts_equal(product.version):
                continue
            left.append(product)
        return left

    def select(self, products: List[OneAPI]) -> Union[OneAPI, None]:
        # Already filtered and sorted
        if products:
            return products[0]
        return None

    @override
    def _get_ignore_vars(self) -> Set[str]:
        return set()

    def _get_path_vars(self) -> Set[str]:
        vars = {"CPATH", "CMAKE_PREFIX_PATH", "PKG_CONFIG_PATH"}
        if sys.platform == "win32":
            vars |= {"INCLUDE", "LIB", "NLSPATH", "OCL_ICD_FILENAMES"}
        else:
            vars |= {"LIBRARY_PATH", "LD_LIBRARY_PATH", "MANPATH", "FI_PROVIDER_PATH"}
        return vars

    @override
    def _get_env_script(self) -> str:
        obj = self.scanned[0]
        # TODO Handle flags for vars (default is first)
        #
        # Windows:
        # compiler: intel64|ia32 (vsVER)
        #      mkl: intel64|ia32 lp64|ilp64
        #      tbb: intel64|ia32 (vsVER|all) -> TBB_TARGET_VS=vc14|vc_mt
        #      mpi: vars.bat [-i_mpi_ofi_internal [0|1]] [-i_mpi_library_kind [debug|release]]
        #
        # Linux:
        # compiler: intel64|ia32
        #      mkl: intel64|ia32 lp64|ilp64
        #      tbb: intel64|ia32
        #      mpi: vars.sh [-i_mpi_ofi_internal[=0|1]] [-i_mpi_library_kind[=debug|debug_mt|release|release_mt]]

        str = ""
        if platform.system() == "Linux":
            str = "#!/bin/bash\n"
            for path in obj.components.values():
                str += f'source "{path}"\n'
            if self.fortran in ["any", "ifx"] and obj.ifx:
                str += f'export FC="{obj.ifx}"\n'
            elif self.fortran in ["any", "ifort"] and obj.ifort:
                str += f'export FC="{obj.ifort}"\n'
        elif platform.system() == "Windows":
            str = "@echo off\n"
            # tk = self._GetVisualStudioInChain()
            # if tk is not None and tk.vs_version:
            #    str += f"set VSCMD_VER={tk.vs_version}\n"
            str += "if not defined VSCMD_VER (\n"
            str += '    echo "ERROR: Visual Studio needs to be setup before"\n'
            str += "    exit /B 1\n"
            str += ")\n"
            for path in obj.components.values():
                str += f'call "{path}"\n'
            if self.fortran in ["any", "ifx"] and obj.ifx:
                str += f"set FC={obj.ifx}\n"
            elif self.fortran in ["any", "ifort"] and obj.ifort:
                str += f"set FC={obj.ifort}\n"
        return str