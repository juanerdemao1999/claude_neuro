import pytest

from nex5_analyzer.gui.region_mapping_dialog import (
    RegionMappingEntry,
    build_region_map_from_entries,
    compress_region_map,
    parse_channel_range,
    validate_region_map,
)


def test_parse_channel_range_accepts_single_value_and_range() -> None:
    assert parse_channel_range("3") == (3, 3)
    assert parse_channel_range("2-6") == (2, 6)
    assert parse_channel_range(" 10 - 12 ") == (10, 12)


def test_build_region_map_from_entries_requires_full_channel_coverage() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_region_map_from_entries(
            [
                RegionMappingEntry(channel_range="1-2", region="M1"),
                RegionMappingEntry(channel_range="4", region="M2"),
            ],
            channel_ids=[1, 2, 3, 4],
        )

    assert "3" in str(excinfo.value)


def test_build_region_map_from_entries_builds_dense_mapping() -> None:
    region_map = build_region_map_from_entries(
        [
            RegionMappingEntry(channel_range="1-2", region="M1"),
            RegionMappingEntry(channel_range="3-4", region="M2"),
        ],
        channel_ids=[1, 2, 3, 4],
    )

    assert region_map == {1: "M1", 2: "M1", 3: "M2", 4: "M2"}


def test_build_region_map_from_entries_supports_subject_region_pairs() -> None:
    region_map = build_region_map_from_entries(
        [
            RegionMappingEntry(channel_range="1-2", subject="Mouse A", region="M1"),
            RegionMappingEntry(channel_range="3-4", subject="Mouse B", region="M1"),
        ],
        channel_ids=[1, 2, 3, 4],
    )

    assert region_map == {
        1: {"subject": "Mouse A", "region": "M1"},
        2: {"subject": "Mouse A", "region": "M1"},
        3: {"subject": "Mouse B", "region": "M1"},
        4: {"subject": "Mouse B", "region": "M1"},
    }


def test_validate_region_map_reports_missing_channels() -> None:
    errors = validate_region_map({1: "M1", 2: "M1", 4: "M2"}, channel_ids=[1, 2, 3, 4])

    assert errors
    assert "3" in errors[0]


def test_compress_region_map_groups_adjacent_equal_regions() -> None:
    entries = compress_region_map(
        [1, 2, 3, 4, 5, 6],
        {1: "M1", 2: "M1", 3: "M2", 4: "M2", 5: "M2", 6: "M3"},
    )

    assert entries == [
        RegionMappingEntry(channel_range="1-2", region="M1"),
        RegionMappingEntry(channel_range="3-5", region="M2"),
        RegionMappingEntry(channel_range="6", region="M3"),
    ]


def test_compress_region_map_keeps_subject_boundaries() -> None:
    entries = compress_region_map(
        [1, 2, 3, 4],
        {
            1: {"subject": "Mouse A", "region": "M1"},
            2: {"subject": "Mouse A", "region": "M1"},
            3: {"subject": "Mouse B", "region": "M1"},
            4: {"subject": "Mouse B", "region": "M1"},
        },
    )

    assert entries == [
        RegionMappingEntry(channel_range="1-2", subject="Mouse A", region="M1"),
        RegionMappingEntry(channel_range="3-4", subject="Mouse B", region="M1"),
    ]
