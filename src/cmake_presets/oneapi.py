import logging
import os
import platform
import sys
from argparse import _ArgumentGroup, Namespace
from functools import total_ordering
from typing import Any, Dict, Iterable, List, NamedTuple, Set, TypeVar, Union

from .msvc import MSVCToolkit
from .toolkit import Toolkit
from .util import (
    ScanError,
    Version,
    expand_dirs,
    override,  # Compatibility imports
)

log = logging.getLogger(__name__)
OneAPIType = TypeVar("OneAPIType", bound="OneAPI")


def oneapi_version(val: str) -> Version:
    return Version.make(val, minlen=1, maxlen=3)


class _CompDirs(NamedTuple):
    varspath: str
    ifortpath: str
    ifxpath: str


@total_ordering
class OneAPI:
    COMPONENTS = ["compiler", "mkl"] #, "tbb", "mpi"]
    FORTRAN = ["ifx", "ifort"]
    TARGET = "intel64"

    def __init__(self, dir: str) -> None:
        self.dir: str = dir
        self.version: Version = Version()
        self.ifort: str = ""
        self.ifx: str = ""
        self.components: Dict[str, str] = {}

    def ifort_path(self) -> str:
        if self.ifort:
            return os.path.join(self.dir, self.ifort)
        return ""

    def ifx_path(self) -> str:
        if self.ifx:
            return os.path.join(self.dir, self.ifx)
        return ""

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, OneAPI):
            return False
        return self.version < other.version

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, OneAPI):
            return False
        return self.version == other.version

    def print(
        self,
        detailed: bool = False,
        fortran: str = "any",
        components: List[str] = COMPONENTS,
    ) -> None:
        print_comp = {c: path for c, path in self.components.items() if c in components}

        if detailed:
            log.info("   Product: Intel oneAPI %s", self.version.major)
            log.info("   Version: ", self.version)
            if fortran in ["any", "ifx"]:
                log.info("       ifx: %s", self.ifx_path())
            if fortran in ["any", "ifort"]:
                log.info("     ifort: %s", self.ifort_path())
            log.info("Components:\n")
            for name, path in print_comp.items():
                log.info("  - %s: %s\n", name, path)
        else:
            compilers = []
            if fortran in ["any", "ifx"]:
                compilers.append("ifx")
            if fortran in ["any", "ifort"]:
                compilers.append("ifort")
            log.info(" * Product: Intel oneAPI %s", self.version.major)
            log.info("       Version: %s", self.version)
            log.info("     Compilers: %s", ", ".join(compilers))
            log.info("    Components: %s", ", ".join(print_comp))

    @classmethod
    def scan(cls, root_dir: str = "") -> List["OneAPI"]:
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

        compdirs = _CompDirs(
            ifortpath=os.path.join(osdir, "bin", OneAPI.TARGET, "ifort" + exesuffix),
            ifxpath=os.path.join(osdir, "bin", "ifx" + exesuffix),
            varspath=os.path.join("env", "vars" + scriptsuffix),
        )

        scan_dirs = expand_dirs(dirs)
        scan_dirs = list(set(scan_dirs))  # remove duplicates, don't care for order

        log.debug("Scan directories:")
        for dir in scan_dirs:
            log.debug(dir)

        products: List[OneAPI] = []
        for rootdir in scan_dirs:
            allver = []
            if not os.path.isdir(rootdir):
                continue

            log.debug("Scanning: %s", rootdir)

            for comp in OneAPI.COMPONENTS:
                compdir = os.path.join(rootdir, comp)
                if os.path.isdir(compdir):
                    for file in os.listdir(compdir):
                        ver = Version.make_safe(file)
                        if ver and ver not in allver:
                            allver.append(ver)
            allver.sort(reverse=True)

            log.debug("Found potential versions:")
            for ver in allver:
                log.debug(" * %s", ver)

            for ver in allver:
                obj = cls._scan_version(rootdir, ver, compdirs)
                if obj is not None:
                    products.append(obj)

            log.debug("number of versions found: %d", len(products))

        products.sort(reverse=True)
        return products

    @classmethod
    def _scan_version(
        cls, rootdir: str, ver: Version, compdirs: _CompDirs
    ) -> Union["OneAPI", None]:
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
        self._found: List[OneAPI] = []

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
            tk: Union[Toolkit, None] = self.get_prev_toolkit()
            while tk:
                if isinstance(tk, MSVCToolkit):
                    return tk
                tk = tk.get_prev_toolkit()
        return None

    @override
    def is_instance_supported(self) -> bool:
        if sys.platform != "win32":
            return True
        tk = self._get_vs_in_chain()
        if tk is None:
            log.error("oneAPI: Requires MSVCToolkit before OneAPIToolkit")
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
    def _from_args(cls, prefix: str, args: Namespace) -> "OneAPIToolkit":
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
            products = self._filter(OneAPI.scan(root_dir=self.root_dir))
            if select:
                best = self._select(products)
                products = [best] if best else []
        except ScanError as e:
            log.exception(e)
            return False
        self._found = products
        return bool(products)

    @override
    def print(self, detailed: bool = False) -> None:
        for product in self._found:
            product.print(detailed, fortran=self.fortran, components=self.components)

    def _filter(self, products: List[OneAPI]) -> List[OneAPI]:
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

    def _select(self, products: List[OneAPI]) -> Union[OneAPI, None]:
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
        obj = self._found[0]
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
