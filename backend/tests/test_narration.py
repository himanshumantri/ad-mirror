import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.narration import mentioned_items, resolve_item, resolve_location, spoken_numbers  # noqa: E402

LOCATIONS = ["A1-B2", "A1-B3", "A2-B2"]
ITEMS = ["IFB Microwave", "TV stand", "TV unit"]


def test_spoken_location_from_real_transcript():
    t = "these are the boxes of IFB Microwave oven on aisle one bay area two"
    assert spoken_numbers(t) == [1, 2]
    assert resolve_location(t, LOCATIONS) == "A1-B2"


def test_location_digits_and_codes():
    assert resolve_location("aisle A2 shelf B2, 24-pack cartons", LOCATIONS) == "A2-B2"
    assert resolve_location("aisle 1, bay 3", LOCATIONS) == "A1-B3"


def test_unknown_or_ambiguous_location_is_none():
    assert resolve_location("aisle nine bay nine", LOCATIONS) is None
    assert resolve_location("no location said", LOCATIONS) is None


def test_single_item_resolved_with_extra_words():
    assert resolve_item("these are the boxes of IFB Microwave oven", ITEMS) == "IFB Microwave"


def test_tv_stand_does_not_match_tv_unit():
    assert resolve_item("one TV stand on the top right", ITEMS) == "TV stand"


def test_mixed_clip_has_no_single_item():
    t = "five microwave boxes IFB Microwave, one TV stand and one TV unit"
    assert set(mentioned_items(t, ITEMS)) == set(ITEMS)
    assert resolve_item(t, ITEMS) is None
