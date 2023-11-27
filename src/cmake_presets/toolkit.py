import inspect
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
from abc import ABCMeta, abstractmethod
from argparse import _ArgumentGroup, Namespace
from copy import deepcopy
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, NamedTuple, Set, Tuple, TypeVar, Union

from .util import (
    EnvDict,
    SingletonABCMeta,
    final,  # Compatibility import
    merge_presets,
    override,  # Compatibility imports
)

log: logging.Logger = logging.getLogger(__name__)
ToolkitType = TypeVar("ToolkitType", bound="Toolkit")
ToolkitChainType = TypeVar("ToolkitChainType", bound="ToolkitChain")
ToolkitInstanceType = TypeVar("ToolkitInstanceType", bound="ToolkitInstance")

_TOOLKITS: Dict[str, "Toolkit"] = {}
_DEBUG = False

if _DEBUG:
    #logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)

    log.warning("DEBUG root log handler is enabled")

    def _is_abstract(method: ...) -> bool:
        return getattr(method, "__isabstractmethod__", False)

    def _get_abstract_methods(object: ...) -> List[Tuple[str, Any]]:
        return inspect.getmembers(object, predicate=_is_abstract)


def _register_toolkit(cls: Any) -> None:
    global _TOOLKITS
    name = cls.__name__
    if name in ["ToolkitChain", "ScriptToolkit"]:
        return
    if not inspect.isabstract(cls):
        log.debug("Register toolkit: %s", name)
        _TOOLKITS[name] = cls
    elif _DEBUG:
        log.debug("Skipping abstract toolkit: %s", name)
        members = _get_abstract_methods(cls)
        log.debug("    Members declared abstract:")
        for _, member in members:
            log.debug("    %s", member)


def get_toolkits() -> Dict[str, "Toolkit"]:
    return _TOOLKITS


class ToolkitError(Exception):
    """Any expected error in toolkit should be wrapped into this"""


class ToolkitSpec:
    def __init__(self) -> None:
        pass


class ToolkitInstance(NamedTuple):  # FIXME: Rename to Toolkit
    """Abstract base class for holding information about a single installation of a toolkit
    identified by version, path or set of tools installed
    """

    def print(self, detailed: bool = False) -> None:
        raise NotImplementedError

    # def __lt__(self, other: "ToolkitInstance") -> bool:
    #     raise NotImplementedError

    # def __eq__(self, other: "ToolkitInstance") -> bool:
    #     raise NotImplementedError


class ToolkitScanner(metaclass=SingletonABCMeta):
    """Abstract singleton base class for searching and holding ToolkitInstance"""

    @abstractmethod
    def scan(self) -> int:
        """Scan should not filter based on any properties. Filtering is done in
        the toolkit
        """
        raise NotImplementedError

    @abstractmethod
    def matches(
        self, spec: "Toolkit", print: bool = False, print_detailed: bool = False
    ) -> List[ToolkitInstance]:
        """Return"""
        raise NotImplementedError

    def get_best(self, spec: "Toolkit", print: bool = False) -> ToolkitInstance:
        raise NotImplementedError


class Toolkit(metaclass=ABCMeta):  # FIXME: Rename to Generator
    """Toolkit: Abstract base class"""

    def __init__(self, name: str, required_vars: Union[Set[str], None] = None) -> None:
        self.name: str = "toolkit_" + name  # name
        self.required_vars: Set[str] = (
            required_vars if required_vars is not None else set()
        )
        self._MARKER = "=#= ENVIRONMENT =#="
        self._chain: Union[ToolkitChain, None] = None
        self._chain_idx: int = -1
        self._env_result: EnvDict = EnvDict()
        self._logger: logging.Logger = log

    def __init_subclass__(cls, *args: Any, **kwargs: Any) -> None:
        super().__init_subclass__(*args, **kwargs)
        _register_toolkit(cls)

    ############################################################
    # Basic information
    ############################################################

    @final
    def copy(self) -> Any:
        return deepcopy(self)

    @staticmethod
    @abstractmethod
    def get_toolkit_name() -> str:
        """Return human readable name of toolkit"""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def is_supported() -> bool:
        """Return True if Toolkit is supported by current platform"""
        raise NotImplementedError

    def is_instance_supported(self) -> bool:
        """Return True if instance construct of settings is supported"""
        return self.__class__.is_supported()

    ############################################################
    # Command-line arguments
    ############################################################

    @staticmethod
    def _get_argument_prefix() -> str:
        """
        Return a non-empty prefix if toolkit need arguments from command-line
        Applicable to generate or scan commands
        The same, or overridden prefix, will be added as argument to AddArguments
        and FromArgs
        """
        return ""

    @staticmethod
    def _add_arguments(prefix: str, parser: _ArgumentGroup) -> None:
        """Add Toolkit specific arguments to parser (check if already defined)"""
        return

    @classmethod
    def _from_args(cls, prefix: str, args: Namespace) -> "Toolkit":
        """Parse arguments from argument-parser and construct Toolkit for generation
        Only called from CLI if _get_argument_prefix return Non-empty string
        """
        raise NotImplementedError

    ############################################################
    # The actual grunt work of every toolkit
    ############################################################

    @abstractmethod
    def scan(self, select: bool = False) -> bool:
        """Scan for compatible toolkits, print out the result and
        store the results internally for later use in generation methods
        If select is true, scan must result in the best toolkit
        if select is false, scan must contain all matching toolkits
        return True on successfully found toolkit(s)
        """
        raise NotImplementedError

    @abstractmethod
    def print(self, detailed: bool = False) -> None:
        raise NotImplementedError

    ############################################################
    # Preset generation
    ############################################################

    def get_base_json(self) -> Dict[str, Any]:
        """Return base JSON of configurePresets object, before environment.
        Must always be callable regardless of if supported on platform on not.
        May not contain 'environment' or 'cacheVariables' as these is may
        be overwritten in base class
        """
        return {"name": self.name, "hidden": True}

    @final
    def get_json(self) -> Dict[str, Any]:
        """Return the complete JSON of configurePresets object
        Instead of overridding this method, subclasses should override:
            GetBaseJSON()
            GetEnvScript()
            AddPostEnvVars()
            GetCacheVariables()
        """
        json = self.get_base_json()
        env = self._get_environment()
        if env:
            if not isinstance(env, EnvDict):
                raise RuntimeError("GetEnvironment() did not return an EnvDict type")
            pathvars = self._get_path_vars()
            pathvars.add("PATH")
            for name in env:
                if name in pathvars:
                    env_item = f"$penv{{{name}}}"
                    env.append_path(name, env_item)
            json["environment"] = dict(env)
        cachevars = self._get_cache_vars(env)
        if cachevars:
            if not isinstance(cachevars, dict):
                raise RuntimeError(
                    "GetCacheVariables() did not return a dict type: {type(env)}"
                )
            json["cacheVariables"] = cachevars
        return json

    ############################################################
    # Preset environment variables
    ############################################################

    def _get_path_vars(self) -> Set[str]:
        """Return a set of PATH-like variables that should be considered
        when running diff or merge of environment variables
        'PATH' is always considered
        """
        return set()

    def _get_ignore_vars(self) -> Union[Set[str], None]:
        """Return a set of variables that can be ignored when collected
        from environment run script"""
        return None

    def _get_pre_environment(self) -> EnvDict:
        env = EnvDict.os()
        tk: Union[Toolkit, None] = self.get_prev_toolkit()
        if tk is not None:
            if tk._env_result:
                env.merge(tk._env_result)
        return env

    def _get_environment(self) -> EnvDict:
        if self._env_result:
            return self._env_result

        script = self._get_env_script()
        if script:
            ignore = self._get_ignore_vars()
            if ignore is None:
                ignore = set()
            if sys.platform == "linux":
                ignore |= {"_", "SHLVL"}
            pathvars = self._get_path_vars()
            if pathvars is None:
                pathvars = set()
            pathvars |= {"PATH"}

            preenv = self._get_pre_environment()
            postenv = self._execute_env_script(script, preenv)
            env = postenv.diff(preenv, ignore=ignore, pathvars=pathvars)
        else:
            env = EnvDict()
        self._add_post_env_vars(env)

        self._env_result = env  # Cache result
        return env

    def _get_env_script(self) -> str:
        """Return contents of either batch or linux shell script
        Contents may be empty string '' to skip environment script to run
        """
        return ""

    def _add_post_env_vars(self, env: EnvDict) -> None:
        """Manually add or set any variables to the environment
        PATH-like variables should be modified with env_prepend_path method.
        """
        return

    @final
    def _execute_env_script(self, script: str, runenv: EnvDict) -> EnvDict:
        """Execute environment script and return the environment difference in environment
        run before and after the script
        """

        if not self.is_supported():
            raise RuntimeError("Toolkit cannot execute on this platform...")

        if platform.system() == "Windows":
            script += f"echo {self._MARKER}\n"
            script += "set"
        else:
            script += f'echo "{self._MARKER}"\n'
            script += "/usr/bin/env"

        debuglog = log.isEnabledFor(logging.DEBUG)

        # print(f"Generate environment settings for: " + self.GetEnvScriptInfo())

        is_win = platform.system() == "Windows"
        if is_win:
            script_name = "_checkenv.bat"
        else:
            script_name = "_checkenv.run"  # Let's not assume script type

        dstenv = EnvDict()
        with TemporaryDirectory() as tmpdir:
            tmpfile = os.path.join(tmpdir, script_name)

            with open(tmpfile, "w", encoding="utf-8") as f:
                f.write(script)
            if debuglog:
                logging.debug("Wrote script to: %s", tmpfile)
                logging.debug(script)

            if not is_win:
                st = os.stat(tmpfile)
                os.chmod(tmpfile, st.st_mode | stat.S_IEXEC)

            try:
                output = (
                    subprocess.check_output(tmpfile, env=dict(runenv))
                    .decode()
                    .splitlines()
                )
            except subprocess.CalledProcessError as err:
                raise ToolkitError(
                    "ERROR: Failed to run environment script. Verify that correct version of tools installed in standard paths"
                ) from err

            seek_marker = True
            for line in output:
                if seek_marker:
                    if line == self._MARKER:
                        seek_marker = False
                    elif debuglog:
                        logging.debug("> %s", line)  # Line from script
                    continue

                p = line.split("=", 1)
                name = p[0]
                val = p[1]

                dstenv[name] = val

        return dstenv

    ############################################################
    # Preset CMake cache variables
    ############################################################

    def _resolve_exe(
        self, name: str, desc: str, env: EnvDict, val: Union[str, None] = None
    ) -> Union[str, None]:
        if not val:
            val = env.get(name, "")
        if val:
            if os.path.isabs(val):
                print(f"Resolved {desc} as: {val}")
            elif "PATH" in env:
                # logging.debug("Resolving %s %s in PATH: %s", desc, val, env["PATH"])
                val = shutil.which(val, path=env["PATH"])
        if not val:
            if name in self.required_vars:
                raise ToolkitError(f"Could not resolve {desc}")
        return val

    def _get_cache_vars(self, env: EnvDict) -> Dict[str, Any]:
        """Add any CMake cache variables here.
        Default implementation checks for CC, CXX and FC and sets
        corresponding CMake variable
        """
        vars = {}
        val = self._resolve_exe("CC", desc="C compiler", env=env)
        if val:
            vars["CMAKE_C_COMPILER"] = val
        val = self._resolve_exe("CXX", desc="C++ compiler", env=env)
        if val:
            vars["CMAKE_CXX_COMPILER"] = val
        val = self._resolve_exe("FC", desc="Fortran compiler", env=env)
        if val:
            vars["CMAKE_Fortran_COMPILER"] = val
        return vars

    ############################################################
    # Methods for running in ToolkitChain
    # Toolkits that rely on Visual Studio for instance can
    # verify that Visual Studio is run in chain before
    ############################################################

    @final
    def _register_chain(self, chain: "ToolkitChain", idx: int) -> None:
        self._chain = chain
        self._chain_idx = idx

    @final
    def in_chain(self) -> bool:
        return bool(self._chain)

    @final
    def get_prev_toolkit(self) -> Union["Toolkit", None]:
        if self._chain:
            return self._chain._get_prev_toolkit(self._chain_idx)
        return None

    @final
    def get_next_toolkit(self) -> Union["Toolkit", None]:
        if self._chain:
            return self._chain._get_next_toolkit(self._chain_idx)
        return None


class ScriptToolkit(Toolkit):
    """
    Abstract class to get environment from a user-provided script
    # TODO Add arguments and parsing
    """

    def __init__(
        self,
        name: str,
        desc: str,
        script_path: str,
        need_cc: bool = False,
        need_cxx: bool = False,
        need_fortran: bool = False,
    ) -> None:
        self.script = script_path
        self.desc = desc
        required_vars = set()
        if need_cc:
            required_vars.add("CC")
        if need_cxx:
            required_vars.add("CXX")
        if need_fortran:
            required_vars.add("Fortran")
        super().__init__(name, required_vars)

    @override
    def scan(self, select: bool = False) -> bool:
        """In this case we only need to verify script existence"""
        if os.path.isfile(self.script):
            print(self.desc)
            return True
        else:
            logging.error("Script does not exist: %s", self.script)
        return False

    @override
    def print(self, detailed: bool = False) -> None:
        log.info("%s: %s", self.get_toolkit_name(), self.script)

    @override
    def _get_env_script(self) -> str:
        try:
            ret = ""
            with open(self.script) as f:
                for line in f.readlines():  # keep newlines
                    ret += line
            return ret
        except Exception as e:
            msg = f"Failed to read contents of {self.script}\n{e}"
            raise ToolkitError(msg) from e


class BatScriptToolkit(ScriptToolkit):
    def __init__(
        self,
        name: str,
        desc: str,
        script_path: str,
        need_cc: bool = False,
        need_cxx: bool = False,
        need_fortran: bool = False,
    ) -> None:
        super().__init__(name, desc, script_path, need_cc, need_cxx, need_fortran)

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "Bat-file"

    @override
    @staticmethod
    def is_supported() -> bool:
        return platform.system() == "Windows"


class ShellScriptToolkit(ScriptToolkit):
    def __init__(
        self,
        name: str,
        desc: str,
        script_path: str,
        need_cc: bool = False,
        need_cxx: bool = False,
        need_fortran: bool = False,
    ) -> None:
        super().__init__(name, desc, script_path, need_cc, need_cxx, need_fortran)

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "Shell script"

    @override
    @staticmethod
    def is_supported() -> bool:
        return platform.system() != "Windows"


class ToolkitChain(Toolkit):
    """Chain toolkits together for a joined environment
    This is an utility class without argument parsing
    """

    def __init__(self, toolkits: List[Toolkit], name: str = "") -> None:
        if not toolkits:
            raise ValueError("Empty toolkits")
        self._toolkits: List[Toolkit] = toolkits

        names = []
        required_vars = set()
        for idx, toolkit in enumerate(toolkits):
            toolkit._register_chain(self, idx)
            required_vars |= toolkit.required_vars
            names.append(toolkit.name.replace("toolkit_", ""))
        if not name:
            name = "_".join(names)
        super().__init__(name, required_vars)

    def _get_prev_toolkit(self, idx: int) -> Union[Toolkit, None]:
        print(f"_GetPreviousToolkit: idx {idx}, toolkits: {self._toolkits}")
        if idx > 0:
            return self._toolkits[idx - 1]
        return None

    def _get_next_toolkit(self, idx: int) -> Union[Toolkit, None]:
        if idx <= len(self._toolkits):
            return self._toolkits[idx + 1]
        return None

    @override
    @staticmethod
    def get_toolkit_name() -> str:
        return "Toolkit chain"

    @override
    @staticmethod
    def is_supported() -> bool:
        return True  # Platform agnostic - Cannot determine without object

    @override
    def is_instance_supported(self) -> bool:
        for t in self._toolkits:
            if not t.is_instance_supported():
                return False
        return True

    @override
    def _get_path_vars(self) -> Set[str]:
        ret = set()
        for t in self._toolkits:
            tvars = t._get_path_vars()
            if tvars:
                ret |= tvars
        return ret

    @override
    def _get_ignore_vars(self) -> Union[Set[str], None]:
        ret = set()
        for t in self._toolkits:
            tvars = t._get_ignore_vars()
            if tvars:
                ret |= tvars
        return ret

    @override
    def scan(self, select: bool = False) -> bool:
        for toolkit in self._toolkits:
            if not toolkit.scan(select=select):
                return False
        return True

    @override
    def get_base_json(self) -> dict:
        json = super().get_base_json()
        for t in reversed(self._toolkits):  # Merge from last
            subjson = t.get_base_json()
            merge_presets(json, subjson)  # Prefers json on conflicts
        return json

    @override
    def _get_environment(self) -> EnvDict:
        env = EnvDict()
        pathvars = self._get_path_vars()
        for toolkit in self._toolkits:
            env.merge(toolkit._get_environment(), pathvars=pathvars)
        return env
