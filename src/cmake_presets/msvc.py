import json
import logging
import os
import platform
from argparse import Namespace, _ArgumentGroup
from functools import total_ordering
from subprocess import CalledProcessError, check_output
from typing import Any, Dict, List, Set, TypeVar, Union

from .toolkit import Toolkit
from .util import (
    ScanError,
    Version,
    override,  # Compatibility imports
)

log = logging.getLogger(__name__)
MSVCType = TypeVar("MSVCType", bound="MSVC")
BuildToolType = TypeVar("BuildToolType", bound="BuildTool")


def vs_version(val: Union[str, Version]) -> Version:
    return Version.make(val, maxlen=1)


def build_tools_version(val: Union[str, Version]) -> Version:
    if val is not None and isinstance(val, str) and val.startswith("v"):
        # FIXME. This comparison needs to be a range
        if val == "v143":
            return Version(14, 30)
        if val == "v142":
            return Version(14, 20)
        if val == "v141":
            return Version(14, 10)
        raise ValueError(
            "Only build tools alternative version formats v143, v142 or v141 are supported"
        )
    return Version.make(val, minlen=2, maxlen=3)


def win_sdk_version(val: Union[str, Version]) -> Version:
    return Version.make(val, minlen=4)


@total_ordering
class BuildTool:
    dir: str
    version: Version
    x86_tools: List[str]
    x64_tools: List[str]

    def __init__(self, dir: str, version: Version) -> None:
        self.dir = dir
        self.version = version
        self.x64_tools = []
        self.x86_tools = []

        for host, tset in [("Hostx86", self.x86_tools), ("Hostx64", self.x64_tools)]:
            hostdir = os.path.join(self.dir, "bin", host)
            if os.path.isdir(hostdir):
                for file in os.listdir(hostdir):
                    if os.path.isdir(os.path.join(hostdir, file)):
                        tset.append(file)

    def name(self) -> str:
        return f"Build Tool {(self.version)}"

    def tool_names(self) -> List[str]:
        ret = []
        for host, targets in [("x64", self.x64_tools), ("x86", self.x86_tools)]:
            for target in targets:
                ret.append(target if host == target else f"{host}_{target}")
        return ret

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, BuildTool):
            return False
        return self.version < other.version

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BuildTool):
            return False
        return self.version == other.version


r"""
Class to find installed:
* Visual Studio or Build Tools, using vswhere?
    - vswhere:
        Always installed to (unless using chocolatey). Can also be installed (how? do we )
        "%ProgramFiles(x86)%\\Microsoft Visual Studio\\Installer\\vswhere.exe"
    - Grab the product install folder:
        Example: VSDIR = "C:\\Program Files (x86)\\Microsoft Visual Studio\\<version>\\<edition>"
    - Scan the tools via path:
        Example: <VSDIR>\\VC\Tools\\MSVC\\14.20.27508
        First digits are required and denotes major compatibility:
            v143 -> Visual Studio 2022
            v142 -> Visual Studio 2019
            v141 -> Visual Studio 2017
            (v12  -> Visual Studio 2015 or 2013) - unsupported
            (v11  -> Visual Studio 2012) - unsupported
            (v10  -> Visual Studio 2010) - unsupported


* Windows SDK version:
    - Run this one:                   "<VSDIR>\\Common7\\Tools\\vsdevcmd\\core\\winsdk.bat" -> Sets WindowsSdkDir
    - Or assume:                      "%ProgramFiles(x86)%\\Windows Kits\\10\\"
    - Version (for instance '10.0.17763.0') should be listed under:
        %WindowsSdkDir%\\Include    and    %WindowsSdkDir%\\Lib
"""


class MSVC:
    def __init__(self) -> None:
        self.instanceId: str = ""  # 9bfa93d9
        self.productId: str = ""  # Microsoft.VisualStudio.Product.Professional
        self.installDir: str = ""  # ...\\Microsoft Visual Studio\\2019\\Professional
        self.displayName: str = ""  # Visual Studio Professional 2019
        self.productVersion: Version = Version()  # 2019
        self.displayVersion: Version = Version()  # 16.11.29
        self.fullVersion: Version = Version()  # 16.11.33927.289
        self.vcBuildTools: List[BuildTool] = []  # List of BuildTools like '14.20.27508'
        self.isValid: bool = False  # true if proper info, "isComplete" and supported

    def print(self, detailed: bool = False, list_buildtools: bool = True) -> None:
        if not log.isEnabledFor(logging.INFO):
            return

        if detailed:
            validstr = "True" if self.isValid else "False"
            log.info("    Instance ID: %s", self.instanceId)
            log.info("     Product ID: %s", self.productId)
            log.info("        Product: %s", self.displayName)
            log.info("Product Version: %s", self.productVersion)
            log.info("Display Version: %s", self.displayVersion)
            log.info("   Full Version: %s", self.fullVersion)
            log.info("   Install Path: %s", self.installDir)
            log.info("          Valid: %s", validstr)
            if list_buildtools:
                for tool in self.vcBuildTools:
                    log.info("     Build Tool: %s", tool.version)
                    log.info("                 %s", ", ".join(tool.tool_names()))
        else:
            log.info(" * Product: %s - %s", self.displayName, self.displayVersion)
            if list_buildtools:
                for tool in self.vcBuildTools:
                    log.info("   * Build Tool: %s", tool.version)
        log.info("")

    @classmethod
    def create(cls, json: Dict[str, Any]) -> Union["MSVC", None]:
        obj = MSVC()
        obj.productId = json.get("productId", "")
        if not obj.productId.lower().startswith("microsoft.visualstudio.product."):
            log.debug("Skipping product: %s", obj.productId)
            return None
        last = obj.productId.split(".", 4)[3].lower()
        if last not in ["community", "professional", "enterprise", "buildtools"]:
            return None

        obj.instanceId = json.get("instanceId", "")
        obj.installDir = json.get("installationPath", "")
        obj.displayName = json.get("displayName", "")
        if "catalog" in json:
            catalog = json["catalog"]
            if not isinstance(catalog, dict):
                raise ScanError(
                    f"Catalog is not of expected type (type is {type(dict)})"
                )
            obj.productVersion = Version.make(catalog.get("productLineVersion", ""))
            obj.displayVersion = Version.make(catalog.get("productDisplayVersion", ""))
            obj.fullVersion = Version.make(catalog.get("buildVersion", ""))
        else:
            log.debug('No "catalog" in json')
        obj.isValid = json.get("isComplete", False)
        obj.validate_info()
        return obj

    def validate_info(self) -> bool:
        if self.isValid:
            self.isValid = bool(
                self.instanceId
                and self.installDir
                and self.displayName
                and self.displayVersion
                and self.fullVersion
            )
        if self.isValid:
            self.isValid = self.productVersion in [2017, 2019, 2022]
        if self.isValid:
            self.isValid = len(self.displayVersion) >= 1  # Let's be nice
        if self.isValid:
            self.isValid = os.path.isdir(self.installDir)
        # Ignore full version
        return self.isValid

    @classmethod
    def scan_products(cls) -> List["MSVC"]:
        products = cls._scan_vs_installs()
        for product in products:
            cls._scan_build_tools(product)
        return products

    @classmethod
    def _scan_vs_installs(cls) -> List["MSVC"]:
        vswhere = os.path.expandvars(
            r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
        )
        if not os.path.isfile(vswhere):
            log.debug("Could not find vswhere utility: %s", vswhere)
            return []
        cmd = [vswhere, "-products", "*", "-all", "-format", "json"]
        log.debug("Running %s", " ".join(cmd))
        try:
            out = check_output(cmd)
        except CalledProcessError as e:
            raise ScanError("Could not execute vswhere") from e
        data = json.loads(out)
        if not data:
            log.debug("No data returned from vswhere")

        installs = []
        for d in data:
            msvc = MSVC.create(d)
            if msvc:
                installs.append(msvc)
        return installs

    @classmethod
    def _scan_build_tools(cls, msvc: "MSVC") -> None:
        kitdir = os.path.join(msvc.installDir, "VC", "Tools", "MSVC")
        for file in os.listdir(kitdir):
            fn = os.path.join(kitdir, file)
            if not os.path.isdir(fn):
                continue
            dirver = Version.make_safe(file)
            if not dirver:
                continue
            msvc.vcBuildTools.append(BuildTool(fn, dirver))
        msvc.vcBuildTools.sort(reverse=True)


class MSVCToolkit(Toolkit):
    def __init__(
        self,
        name: str = "",
        ver: Union[str, Version] = "",
        tools: Union[str, Version] = "",
        winsdk: Union[str, Version] = "",
    ) -> None:
        self.vs_version = vs_version(ver)
        self.tools_version = build_tools_version(tools)
        self.winsdk_version = win_sdk_version(winsdk)

        self._found: List[MSVC] = []

        required_vars = {"CC", "CXX"}

        if not name:
            if self.vs_version:
                parts = [f"vs{self.vs_version}"]
            else:
                parts = ["vs_latest"]
            name = "_".join(parts)

        super().__init__(name, required_vars)

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "MSVC"

    @override
    @staticmethod
    def is_supported() -> bool:
        return platform.system() == "Windows"

    @override
    @staticmethod
    def _get_argument_prefix() -> str:
        return "msvc_"

    @override
    @staticmethod
    def _add_arguments(prefix: str, parser: _ArgumentGroup) -> None:
        parser.add_argument(
            f"--{prefix}ver",
            choices=[Version(2017), Version(2019), Version(2022)],
            default=None,
            metavar="VER",
            type=vs_version,
            help="Visual Studio Version. By default it will select the latest with compatible build tools",
        )
        parser.add_argument(
            f"--{prefix}tools",
            default=None,
            metavar="VER",
            type=build_tools_version,
            help="MSVC Build Tools. Can be in form v142, 14.20 or 14.20.27508. Default is latest from Visual Studio Version",
        )
        parser.add_argument(
            f"--{prefix}winsdk",
            action="store",
            metavar="VER",
            type=win_sdk_version,
            help="Windows SDK Version. Must be in full version form: 10.0.17763.0. Default is latest",
        )

    @override
    @classmethod
    def _from_args(cls, prefix: str, args: Namespace) -> "MSVCToolkit":
        ver = getattr(args, prefix + "ver")
        tools = getattr(args, prefix + "tools")
        winsdk = getattr(args, prefix + "winsdk")
        return cls(ver=ver, tools=tools, winsdk=winsdk)

    @override
    def scan(self, select: bool = False, verbose: bool = False) -> bool:
        try:
            products = self._filter(MSVC.scan_products())
            if select:
                best = self._select(products)
                products = [best] if best else []
        except ScanError as e:
            log.exception(e)
            return False
        self._found = products
        return bool(self._found)

    def _filter(self, products: List[MSVC]) -> List[MSVC]:
        if not self.vs_version and not self.tools_version and not self.winsdk_version:
            return products

        left = []
        for product in products:
            # print(product.productVersion)
            # print(self.vs_version)
            if self.vs_version and product.productVersion != self.vs_version:
                continue

            if self.tools_version:
                left_tools: List[BuildTool] = []
                for tools in product.vcBuildTools:
                    if len(self.tools_version) >= 3:
                        if tools.version == self.tools_version:
                            left_tools.append(tools)
                    elif tools.version >= self.tools_version:
                        left_tools.append(tools)
                if not left_tools:
                    continue
                product.vcBuildTools = left_tools

            left.append(product)
        return left

    def _select(self, products: List[MSVC]) -> Union[MSVC, None]:
        # Already filtered and sorted
        if products:
            return products[0]
        return None

    @override
    def print(self, detailed: bool = False) -> None:
        for product in self._found:
            product.print(detailed)

    @override
    def get_base_json(self) -> dict:
        json = super().get_base_json()
        # TODO Not seen as needed. Find out more
        # json['toolset'] = {
        #     "value": "amd64",
        #     "strategy": "external"
        # }
        # json['architecture'] = {
        #     "value": "amd64",
        #     "strategy": "external"
        # }
        return json

    @override
    def _get_ignore_vars(self) -> Set[str]:
        return {
            "__VSCMD_PREINIT_PATH",
        }

    @override
    def _get_path_vars(self) -> Set[str]:
        return {"LIB", "LIBPATH", "WINDOWSLIBPATH", "INCLUDE"}

    @override
    def _get_env_script(self) -> str:
        str = "@echo off\n"
        # TODO Scan for VSXXXXINSTALLDIR environment variables
        # TODO Support arch, winsdk_version and vc_version - But only possible without oneAPI (for now)
        # call "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvarsall.bat" amd64
        str += f'call "C:\\Program Files (x86)\\Microsoft Visual Studio\\{self.vs_version.major}\\Professional\\VC\\Auxiliary\\Build\\vcvarsall.bat" amd64\n'
        str += "set CC=cl.exe\n"
        str += "set CXX=cl.exe\n"
        return str
