import logging
import os
import re
import stat
import sys
from abc import ABCMeta
from collections import UserDict
from enum import Enum
from functools import total_ordering
from typing import Any, Dict, List, Sequence, Set, TypeVar, Union

VersionType = TypeVar("VersionType", bound="Version")
EnvDictType = TypeVar("EnvDictType", bound="EnvDict")
SingletonABCMetaType = TypeVar("SingletonABCMetaType", bound="SingletonABCMeta")
log = logging.getLogger(__name__)

# RE_TAG = r"([a-z])"
RE_VERSION = r"(\d+(?:\.\d+){0,3})"
RE_OP_COMMON = r"<|lt|<=|lte|=|eq|>=|gte|>|gt"
RE_OP = f"({RE_OP_COMMON})"
RE_OP_SINGLE = f"({RE_OP_COMMON}|range)"

# Single version, optional op (default EQ)
SPEC_SINGLE = re.compile(f"^\s*{RE_OP_SINGLE}?\s*{RE_VERSION}\s*$", re.I)
# Double version, separated by comma. Ops are mandatory
SPEC_RANGE = re.compile(
    f"^\s*{RE_OP}\s*{RE_VERSION}\s*,\s*{RE_OP}\s*{RE_VERSION}\s*$", re.I
)

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

    _instances: Dict[Any, Any] = {}

    @classmethod
    def __call__(cls, *args: Any, **kwargs: Any) -> "SingletonABCMeta":
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
        val: Any = None,
        minor: int = -1,
        patch: int = -1,
        revision: int = -1,
    ) -> None:
        self.parts = []
        if val is None:
            return

        if isinstance(val, Version):
            self.parts = val.parts
        elif isinstance(val, int):
            major: int = val
            for v in [major, minor, patch, revision]:
                if v < 0:
                    break
                self.parts.append(v)
        elif isinstance(val, str):
            raise ValueError(
                f"Initialization from string needs to go through Version.make: {val}"
            )
        elif isinstance(val, list):
            for i in range(min(4, len(val))):
                ival = int(val[i])
                if ival < 0:
                    break
                self.parts.append(ival)
        else:
            raise ValueError(f"Initialization from unsupported type: {type(val)}")

    @classmethod
    def make(
        cls,
        val: Union[str, "Version", None],
        minlen: int = 1,
        maxlen: int = 4,
        sep: str = ".",
    ) -> "Version":
        """Same as constructor but only accept string, Version or None. None will return None"""
        if not val:
            return Version()
        if minlen <= 1:
            minlen = 1

        if isinstance(val, Version):
            parts = val.parts
        else:
            parts = []
            strings: List[str] = val.split(sep)
            try:
                for i in range(min(4, len(strings))):
                    ival = int(strings[i])
                    if ival < 0:
                        break
                    parts.append(int(strings[i]))
            except ValueError as e:
                raise ValueError(f"Version is not numerical: {val}\n+{str(e)}") from e
        if len(parts) > maxlen:
            raise ValueError(f"Version must have at most {maxlen} components: {val})")
        if len(parts) < minlen:
            raise ValueError(f"Version needs have at least {minlen} components: {val}")

        return cls(*parts)

    @classmethod
    def make_safe(
        cls,
        val: Union[str, "Version", None],
        minlen: int = 1,
        maxlen: int = 4,
        sep: str = ".",
    ) -> "Version":
        """Same as make() but catches exceptions and return empty version"""
        try:
            return cls.make(val, minlen=minlen, maxlen=maxlen, sep=sep)
        except Exception:  # noqa: S110
            pass
        return Version()

    def string(self, maxnum: int = 4, sep: str = ".") -> str:
        if not (self):
            return "Unspecified"
        maxnum = min(len(self), maxnum)
        return sep.join([str(self.parts[i]) for i in range(maxnum)])

    def underscore(self, max: int = 4) -> str:
        return self.string(max, sep="_")

    def dotted(self, max: int = 4) -> str:
        return self.string(max, sep=".")

    def joined(self, max: int = 4) -> str:
        return self.string(max, sep="")

    @property
    def major(self) -> Union[int, None]:
        return self[0] if len(self) > 0 else None

    @property
    def minor(self) -> Union[int, None]:
        return self[1] if len(self) > 1 else None

    @property
    def patch(self) -> Union[int, None]:
        return self[2] if len(self) > 2 else None

    @property
    def revision(self) -> Union[int, None]:
        return self[3] if len(self) > 3 else None

    def __bool__(self) -> bool:
        # Any number non-zero. we don't allow negative values
        for part in self.parts:
            if part > 0:
                return True
        return False

    def __hash__(self) -> int:
        return hash(self.parts)

    def __len__(self) -> int:
        return len(self.parts)

    def __getitem__(self, i: Any) -> Any:
        if not isinstance(i, (int, slice)):
            raise ValueError
        return self.parts[i]

    def __str__(self) -> str:
        return self.string()

    def __repr__(self) -> str:
        return f"Version ({str(self.parts)})"

    def __lt__(self, other: Any) -> bool:
        return self.parts_lt(other, True)  # Full comparison
        # slen = len(self)
        # if not isinstance(other, Version):
        #     try:
        #         other = Version(other)
        #         if not other:
        #             return False
        #     except Exception:
        #         return False

        # olen = len(other)
        # for idx in range(4):
        #     if idx < slen and idx < olen:
        #         # Numerical comparison
        #         if self[idx] == other[idx]:
        #             continue
        #         return self[idx] < other[idx]

        # if slen == olen:
        #     return False  # Equal
        # return slen < olen  # Shorter is less than

    def __eq__(self, other: Any) -> bool:
        return self.parts_equal(other, True)  # Full comparison

    def parts_lt(
        self, other: Union["Version", str, int, None], full: bool = False
    ) -> bool:
        """
        Matches either fully or either version appended with zeroes
        WARNING: Equality is asymmetric if full is not True
        """
        if other is None:
            return not bool(self)  # None is less than a value
        if isinstance(other, int):
            other = Version(other)
        if isinstance(other, str):
            try:
                other = Version.make(other)
            except Exception:
                other = None
            if not other:
                return not bool(self)

        lself = len(self)
        lother = len(other)
        if full or lself == lother:
            return self.parts < other.parts
        for idx in range(max(lself, lother)):
            lval = self.parts[idx] if idx < lself else 0
            oval = other.parts[idx] if idx < lother else 0
            if lval < oval:
                return True
        return False

        if full:
            return self.parts < other.parts
        print(str(self) + " < " + str(other))
        for idx in range(min(len(self), len(other))):
            if self.parts[idx] < other.parts[idx]:
                return True
        return len(self) < len(other)

    def parts_equal(
        self, other: Union["Version", str, int, None], full: bool = False
    ) -> bool:
        """
        Matches either fully or either version appended with zeroes
        WARNING: Equality is asymmetric if full is not True
        """
        if other is None:
            return bool(self)
        if isinstance(other, int):
            other = Version(other)
        if isinstance(other, str):
            try:
                other = Version.make(other)
                if not other:
                    return False
            except Exception:
                return False
        lself = len(self)
        lother = len(other)
        if full or lself == lother:
            return self.parts == other.parts
        for idx in range(max(lself, lother)):
            lval = self.parts[idx] if idx < lself else 0
            oval = other.parts[idx] if idx < lother else 0
            if lval != oval:
                return False
        return True


class VersionOp(Enum):
    NONE = 0
    LT = 1
    LTE = 2
    EQ = 3
    GTE = 4
    GT = 5

    @classmethod
    def make(
        cls, val: Union[str, None], default: Union["VersionOp", None] = None
    ) -> "VersionOp":
        if isinstance(val, str):
            val = val.lower()
            if val in ["<", "lt"]:
                return cls(cls.LT)
            if val in ["<=", "lte"]:
                return cls(cls.LTE)
            if val in ["=", "eq"]:
                return cls(cls.EQ)
            if val in [">=", "gte"]:
                return cls(cls.GTE)
            if val in [">", "gt"]:
                return cls(cls.GT)
        if default is not None:
            return default
        return cls(cls.NONE)

    def matches(self, lhs: Version, rhs: Version) -> bool:
        if self == VersionOp.LT:
            return lhs.parts_lt(rhs)
        if self == VersionOp.LTE:
            return lhs.parts_lt(rhs) or lhs.parts_equal(rhs)
        if self == VersionOp.EQ:
            return lhs.parts_equal(rhs)
        if self == VersionOp.GTE:
            return not lhs.parts_lt(rhs)
        if self == VersionOp.GT:
            return not lhs.parts_lt(rhs) and not lhs.parts_equal(rhs)
        raise ValueError("Undefined operator comparison NONE")

    def __bool__(self) -> bool:
        return self.value != VersionOp.NONE

    def __str__(self) -> str:
        if self == VersionOp.LT:
            return "<"
        if self == VersionOp.LTE:
            return "<="
        if self == VersionOp.EQ:
            return "="
        if self == VersionOp.GTE:
            return ">="
        if self == VersionOp.GT:
            return ">"
        return "Undefined Op"


class VersionSpec:
    def __init__(
        self,
        l_val: Any = None,
        l_op: VersionOp = VersionOp.EQ,
        u_val: Union[Version, None] = None,
        u_op: VersionOp = VersionOp.NONE,
    ) -> None:
        self.l_val = Version()
        self.l_op = l_op
        self.u_val = Version()
        self.u_op = u_op

        if l_val is None:
            return

        if isinstance(l_val, VersionSpec):
            self.l_val = l_val.l_val
            self.l_op = l_val.l_op
            self.u_val = l_val.u_val
            self.u_op = l_val.u_op
        elif isinstance(l_val, Version):
            self.l_val = l_val
            self.l_op = l_op
            if isinstance(u_val, Version):
                self.u_val = u_val
            self.u_op = u_op
        else:
            raise ValueError(f"Unexpected type: {type(l_val)}")

    @classmethod
    def make(cls, val: Union[str, "VersionSpec", None]) -> "VersionSpec":
        if val is None or isinstance(val, VersionSpec):
            return cls(val)
        m = SPEC_SINGLE.match(val)
        if m:
            opstr = m.group(1)
            ver = Version.make(m.group(2))
            if opstr == "range":
                next = ver.parts.copy()
                next[len(next) - 1] += 1
                ver2 = Version(next)
                print(f"range: {ver} -> {ver2}")
                return cls(ver, VersionOp.GTE, ver2, VersionOp.LT)
            else:
                op = VersionOp.make(m.group(1), VersionOp.EQ)
                return cls(ver, op)
        m = SPEC_RANGE.match(val)
        if m:
            l_op = VersionOp.make(m.group(1))
            l_val = Version.make(m.group(2))
            u_op = VersionOp.make(m.group(3))
            u_val = Version.make(m.group(4))

            if not l_op or not u_op:  # Regex guard against this
                raise ValueError(f"Undefined operators in {val}")

            if l_op == VersionOp.EQ or u_op == VersionOp.EQ:
                raise ValueError(f"Range cannot contain equality comparison: {val}")

            if u_val < l_val:
                # Swap positions
                tmp_val = l_val
                tmp_op = l_op
                l_op = u_op
                l_val = u_val
                u_op = tmp_op
                u_val = tmp_val

            # Check for impossible spec
            if l_op in [VersionOp.LT, VersionOp.LTE] and u_op in [
                VersionOp.GT,
                VersionOp.GTE,
            ]:
                raise ValueError(f"No version can satisfy specification: {val}")

            return cls(l_val, l_op, u_val, u_op)
        raise ValueError(f"Could not parse specification: {val}")

    # @classmethod
    # def make_safe(cls, val: Union[str, "VersionSpec", None]) -> "VersionSpec":
    #     try:
    #         return cls.make_safe(val)
    #     except ValueError:
    #         pass
    #     return cls()

    def matches(self, ver: Version) -> bool:
        match = True  # No spec
        if self.l_val and self.u_val:  # Range
            match = self.l_op.matches(ver, self.l_val) and self.u_op.matches(
                ver, self.u_val
            )
        elif self.l_val:  # Single
            match = self.l_op.matches(ver, self.l_val)
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Version spec: %s matches %s => %s", self, ver, match)
        return match

    def __repr__(self) -> str:
        if self.u_val or self.u_op != VersionOp.NONE:
            return f"VersionSpec({self.l_val}, {self.l_op}, {self.u_val}, {self.u_op})"
        return f"VersionSpec({self.l_val}, {self.l_op})"

    def __str__(self) -> str:
        if self.u_val or self.u_op != VersionOp.NONE:
            return f"{self.l_op} {self.l_val} and {self.u_op} {self.u_val}"
        return f"{self.l_op} {self.l_val}"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, VersionSpec):
            return False
        return (
            self.l_op == other.l_op
            and self.l_val == other.l_val
            and self.u_op == other.u_op
            and self.u_val == other.u_val
        )


class EnvDict(StrUserDict):
    def __setitem__(self, key: str, item: Any) -> None:
        if os.name == "nt":
            # Should we keep a copy of original just in case?
            key = key.upper()
        return super().__setitem__(key, item)

    @classmethod
    def os(cls) -> "EnvDict":
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
        self,
        other: "EnvDict",
        ignore: Union[Set[str], None] = None,
        pathvars: Union[Set[str], None] = None,
    ) -> "EnvDict":
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
                    log.debug("Env: Difference on path variable %s = %s", name, diff)
                else:
                    result[name] = self[name]
                    log.warning(
                        "Env: Unhandled difference on variable %s, replacing", name
                    )
            elif name in self:
                log.debug(
                    "Env: Added new environment variable %s = %s", name, self[name]
                )
                result[name] = self[name]
            else:
                log.warning(
                    "Env: Ignored removal of environment variable %s = %s",
                    name,
                    other[name],
                )
        return result

    def merge(self, other: EnvDictType, pathvars: Union[Set[str], None] = None) -> None:
        if not pathvars:
            pathvars = set()
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
