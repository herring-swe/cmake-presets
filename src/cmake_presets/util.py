import logging
import os
import stat
import sys
from abc import ABCMeta
from collections import UserDict
from functools import total_ordering
from typing import Any, Dict, List, Sequence, Set, TypeVar, Union

VersionType = TypeVar("VersionType", bound="Version")
EnvDictType = TypeVar("EnvDictType", bound="EnvDict")
SingletonABCMetaType = TypeVar("SingletonABCMetaType", bound="SingletonABCMeta")


# fmt: off
if sys.version_info >= (3, 8):
    from typing import final
else:
    def final(func):  # noqa
        return func

if sys.version_info >= (3, 9):
    StrUserDict = UserDict[str, str]
else:
    StrUserDict = UserDict

# if sys.version_info >= (3, 11):
#     from typing import LiteralString
# else:
#     LiteralString: _SpecialForm

if sys.version_info >= (3, 12):
    from typing import override
else:
    def override(func):  # noqa
        return func
# fmt: on


class ScanError(Exception):
    """Raised on severe scan errors"""


class VersionMismatchError(Exception):
    """Raised when versions are expected to be equal"""


class SingletonABCMeta(ABCMeta):
    """Abstract singleton meta class"""

    _instances = {}

    @classmethod
    def __call__(cls, *args: Any, **kwargs: Any) -> SingletonABCMetaType:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(cls, *args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def _clear_instance(cls) -> None:
        if cls in cls._instances:
            del (cls._instances, cls)


@total_ordering
class Version(Sequence[int]):
    parts: List[int]

    def __init__(
        self,
        val: Union[int, VersionType, str, List[Any]],
        minor: int = -1,
        patch: int = -1,
        revision: int = -1,
        minlen: int = 1,
        maxlen: int = 4,
        sep: str = ".",
    ) -> None:
        if minlen <= 1:
            minlen = 1

        if isinstance(val, Version):
            self.parts = val.parts
        else:
            self.parts = []

        if isinstance(val, int):
            major: int = val
            for v in [major, minor, patch, revision]:
                if v >= 0:
                    self.parts.append(v)
        elif isinstance(val, str):
            strings: List[str] = val.split(sep)
            try:
                for i in range(min(4, len(strings))):
                    self.parts.append(int(strings[i]))
            except ValueError as e:
                raise ValueError(f"Version is not numerical: {val}\n+{str(e)}") from e
        elif isinstance(val, list):
            for i in range(min(4, len(val))):
                self.parts.append(int(val[i]))

        if len(self.parts) > maxlen:
            raise ValueError(f"Version must have at most {maxlen} components: {val})")
        if len(self.parts) < minlen:
            raise ValueError(f"Version needs have at least {minlen} components: {val}")

    @classmethod
    def make(
        cls, val: Union[str, None], minlen: int = 1, maxlen: int = 4, sep: str = "."
    ) -> VersionType:
        """Same as constructor but only accept string or None. None will return None"""
        if not val:
            return None
        return cls(val, minlen=minlen, maxlen=maxlen, sep=sep)

    @classmethod
    def make_safe(
        cls, val: Union[str, None], minlen: int = 1, maxlen: int = 4, sep: str = "."
    ) -> VersionType:
        """Same as make() but None is returned on any exception"""
        try:
            return cls.make(val, minlen=minlen, maxlen=maxlen, sep=sep)
        except Exception:  # noqa: S110
            pass
        return None

    def string(self, maxnum: int = 4, sep: str=".") -> str:
        maxnum = min(len(self), maxnum)
        return sep.join([str(self.parts[i]) for i in range(maxnum)])

    def underscore(self, max: int = 4) -> str:
        return self.string(max, sep="_")

    def dotted(self, max: int = 4) -> str:
        return self.string(max, sep=".")

    def joined(self, max: int = 4) -> str:
        return self.string(max, sep="")

    @property
    def major(self) -> int:
        return self[0] if len(self) > 0 else None

    @property
    def minor(self) -> int:
        return self[1] if len(self) > 1 else None

    @property
    def patch(self) -> int:
        return self[2] if len(self) > 2 else None

    @property
    def revision(self) -> int:
        return self[3] if len(self) > 3 else None

    def __hash__(self) -> int:
        return hash(self.parts)

    def __len__(self) -> int:
        return len(self.parts)

    def __getitem__(self, i: int) -> int:
        return self.parts[i]

    def __str__(self) -> str:
        return self.string()

    def __repr__(self) -> str:
        return f"Version ({str(self.parts)})"

    def __lt__(self, other: Union[int, VersionType, str, List[Any]]) -> bool:
        slen = len(self)
        if isinstance(other, (int, str, list)):
            try:
                other = Version(other)
                if not other:
                    return False
            except Exception:
                return False

        olen = len(other)
        for idx in range(4):
            if idx < slen and idx < olen:
                # Numerical comparison
                if self[idx] == other[idx]:
                    continue
                return self[idx] < other[idx]

        if slen == olen:
            return True  # Equal
        return slen < olen  # Shorter is less than

    def __eq__(self, other: Union[VersionType, int, str, List[Any]]) -> bool:
        return self.parts_equal(other, True)

    def parts_equal(
        self, other: Union[VersionType, int, str, List[Any]], full: bool = False
    ) -> bool:
        """
        Matches either fully or as long as this version is defined
        WARNING: Equality is asymmetric if not full
        """
        if isinstance(other, (int, str, list)):
            try:
                other = Version(other)
                if not other:
                    return False
            except Exception:
                return False
        if full:
            return self.parts == other.parts
        for idx in range(len(self.parts)):
            if self.parts[idx] != other.parts[idx]:
                return False
        return True


class EnvDict(StrUserDict):
    def __setitem__(self, key: str, item: Any) -> None:
        if os.name == "nt":
            # Should we keep a copy of original just in case?
            key = key.upper()
        return super().__setitem__(key, item)

    @classmethod
    def os(cls) -> EnvDictType:
        return cls(os.environ)

    @staticmethod
    def diff_path(src: str, dst: str, symmetric: bool = False) -> str:
        """Compare PATH-like entries src and dst and
        returns the difference as a new string
        If symmetric is False then only additions in dst
        are returned.
        """
        src_paths = set(src.split(os.pathsep))
        dst_paths = set(dst.split(os.pathsep))
        if symmetric:
            diffpaths = dst_paths.symmetric_difference(src_paths)
        else:
            diffpaths = dst_paths.difference(src_paths)
        return os.pathsep.join(diffpaths).strip(os.pathsep)

    def diff(
        self, other: EnvDictType, ignore: Set[str] = None, pathvars: Set[str] = None
    ) -> EnvDictType:
        """Diff this (baseline) environment to the other enviroment
        Returns a new EnvDict containing the differences
        """
        if pathvars is None:
            pathvars = set()
        if ignore is None:
            ignore = set()
        pathvars.add("PATH")
        names = self.keys() | other.keys()

        result = EnvDict()
        for name in names:
            if name in ignore:
                continue
            if name in self and name in other:
                if self[name] == other[name]:
                    continue
                if name in pathvars:
                    diff = EnvDict.diff_path(other[name], self[name])
                    result[name] = diff
                    logging.debug(
                        "Env: Difference on path variable %s = %s", name, diff
                    )
                else:
                    result[name] = self[name]
                    logging.warning(
                        "Env: Unhandled difference on variable %s, replacing", name
                    )
            elif name in self:
                logging.debug(
                    "Env: Added new environment variable %s = %s", name, self[name]
                )
                result[name] = self[name]
            else:
                logging.warning(
                    "Env: Ignored removal of environment variable %s = %s",
                    name,
                    other[name],
                )
        return result

    def merge(self, other: EnvDictType, pathvars: Set[str] = None) -> None:
        pathvars.add("PATH")
        for name, val in other.items():
            if name not in self:
                self[name] = val
            elif name in pathvars:
                self.prepend_path(name, val)

    def add_path(
        self, name: str, value: Union[str, List[str]], append: bool = True
    ) -> None:
        if isinstance(value, str):
            value = [value]
        if name in self:
            parts = self[name].strip(os.pathsep).split(os.pathsep)
            for v in value:
                if v in parts:
                    parts.remove(v)
            if append:
                parts = parts + value
            else:
                parts = value + parts
        else:
            parts = value
        self[name] = os.pathsep.join(parts)

    def prepend_path(self, name: str, value: Union[str, List[str]]) -> None:
        """Prepend a PATH variable with one or multiple values
        It will remove duplicate values already existing in in path.
        """
        self.add_path(name, value, append=False)

    def append_path(self, name: str, value: Union[str, List[str]]) -> None:
        self.add_path(name, value, append=True)


def merge_cachevars(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for name, val in src.items():
        if name not in dst:
            dst[name] = val


def merge_presets(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """Merge src preset into dst, keeping dst on conflict"""
    for key, val in src.items():
        if key not in dst:
            dst[key] = val
        elif key == "environment":
            dstenv: EnvDict = dst[key]
            if isinstance(dstenv, EnvDict):
                pass
            elif isinstance(dstenv, dict):
                dstenv = EnvDict(dstenv)
            else:
                raise ValueError(f"Expected EnvDict but got type {type(dstenv)}")
            dstenv.merge(val)
        elif key == "cacheVariables":
            merge_cachevars(dst[key], val)


def expand_dir(dir: str) -> str:
    return os.path.realpath(os.path.expandvars(os.path.expanduser(dir)))


def expand_dirs(dirs: List[str]) -> List[str]:
    return [expand_dir(d) for d in dirs]


def is_exec_stat(st: os.stat_result) -> bool:
    return bool(
        st.st_mode & stat.S_IXUSR
        or st.st_mode & stat.S_IXGRP
        or st.st_mode & stat.S_IXOTH
    )
