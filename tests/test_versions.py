#!/usr/bin/python3

# import cmake_presets as cmp  # type: ignore
import pytest
from cmake_presets.util import Version, VersionOp, VersionSpec


@pytest.mark.parametrize(
    "verstr,verval",
    [
        ("2", Version(2)),
        ("2.10.6", Version(2, 10, 6)),
        ("2.1", Version(2, 1)),
        ("2016", Version(2016)),
        ("2.0.01.5", Version(2, 0, 1, 5)),
        ("2.0.01.5.10", Version(2, 0, 1, 5)),
        pytest.param("-5", Version(), marks=pytest.mark.xfail),
        pytest.param("hej", Version(), marks=pytest.mark.xfail),
        pytest.param("v142", Version(), marks=pytest.mark.xfail),
    ],
)
def test_parse_versions(verstr, verval) -> None:
    assert Version.make(verstr) == verval


@pytest.mark.parametrize(
    "specstr,specval",
    [
        ("2", VersionSpec(Version(2), VersionOp.EQ)),
        ("=2", VersionSpec(Version(2), VersionOp.EQ)),
        ("= 2", VersionSpec(Version(2), VersionOp.EQ)),
        (" eq2", VersionSpec(Version(2), VersionOp.EQ)),
        ("<2.5", VersionSpec(Version(2, 5), VersionOp.LT)),
        ("lt2.5", VersionSpec(Version(2, 5), VersionOp.LT)),
        ("<=2.5", VersionSpec(Version(2, 5), VersionOp.LTE)),
        ("lte2.5", VersionSpec(Version(2, 5), VersionOp.LTE)),
        (">=2.5", VersionSpec(Version(2, 5), VersionOp.GTE)),
        ("gte2.5", VersionSpec(Version(2, 5), VersionOp.GTE)),
        (">2.5", VersionSpec(Version(2, 5), VersionOp.GT)),
        ("gt2.5", VersionSpec(Version(2, 5), VersionOp.GT)),
        pytest.param("nope", VersionSpec(), marks=pytest.mark.xfail),
        pytest.param(
            "2,2", VersionSpec(Version(2, 2), VersionOp.EQ), marks=pytest.mark.xfail
        ),
        (
            ">1.2.3,<3.2.1",
            VersionSpec(Version(1, 2, 3), VersionOp.GT, Version(3, 2, 1), VersionOp.LT),
        ),
        pytest.param(
            "<=1,>=3",
            VersionSpec(Version(1), VersionOp.LTE, Version(3), VersionOp.GTE),
            marks=pytest.mark.xfail
        ),
        ("range2.5", VersionSpec(Version(2, 5), VersionOp.GTE, Version(2, 6), VersionOp.LT))
    ],
)
def test_parse_version_specs(specstr, specval) -> None:
    assert VersionSpec.make(specstr) == specval


@pytest.mark.parametrize(
    "specstr,vertrue,verfalse",
    [
        ("2", "2", "1"),
        ("<2.5", "2", "2.5"),
        ("<=2.5", "2.5.0", "2.6"),
        (">=2.5", "2.5.1", "2.4.9"),
        (">2.5", "2.6", "2.4.0.1"),
        (">2,<4", "3", "4"),
        (">2,<4", "2.1", "2"),
        ("<2,<4", "1.9", "3"),
        (None, "123", ""),  # No spec matches any
        pytest.param("<2,>=4", "2", "4", marks=pytest.mark.xfail),
        pytest.param("<2,>=4", "1", "2", marks=pytest.mark.xfail),
        ("range2.5", "2.5.2", "2.6"),
        ("range2.5", "2.5", "2.4.12"),
    ],
)
def test_match_version_specs(specstr, vertrue, verfalse) -> None:
    spec = VersionSpec.make(specstr)
    if vertrue:
        assert spec.matches(Version.make(vertrue))
    if verfalse:
        assert not spec.matches(Version.make(verfalse))
