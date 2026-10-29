import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.reconcile import TOTAL, BookLine, ClipResult, reconcile, write_reports  # noqa: E402

BOOK = [
    BookLine("IFB Microwave", "A1-B2", 4, 1000.0),
    BookLine("TV stand", "A1-B2", 1, 500.0),
    BookLine("TV unit", "A1-B2", 1, 2000.0),
]


def clip(item, counted, review=False):
    return ClipResult("c.mp4", "A1-B2", item, counted, review, ["x"] if review else [], "e.png")


def by_item(rows):
    return {r.item: r for r in rows}


def test_single_item_clip_variance_valued_at_cost():
    rows = by_item(reconcile(BOOK, {"A1-B2": clip("IFB Microwave", 5)}))
    r = rows["IFB Microwave"]
    assert (r.variance_qty, r.variance_value, r.status) == (1, 1000.0, "variance")
    assert rows["TV stand"].status == "not_counted"


def test_match_and_pending_review():
    assert by_item(reconcile(BOOK, {"A1-B2": clip("IFB Microwave", 4)}))["IFB Microwave"].status == "match"
    assert by_item(reconcile(BOOK, {"A1-B2": clip("IFB Microwave", 5, review=True)}))["IFB Microwave"].status == "pending_review"


def test_mixed_clip_compares_location_total_and_defers_items():
    rows = by_item(reconcile(BOOK, {"A1-B2": clip(None, 7)}))
    assert rows[TOTAL].book_qty == 6 and rows[TOTAL].variance_qty == 1
    assert rows["TV stand"].status == "pending_review"


def test_uncounted_location():
    assert all(r.status == "not_counted" for r in reconcile(BOOK, {}))


def test_adjustments_only_include_confirmed_variances(tmp_path):
    rows = reconcile(BOOK, {"A1-B2": clip("IFB Microwave", 5)})
    write_reports(rows, tmp_path)
    adj = list(csv.DictReader((tmp_path / "proposed_adjustments.csv").open()))
    assert [a["Item"] for a in adj] == ["IFB Microwave"]
    assert adj[0]["Adjust Qty. By"] == "1" and adj[0]["New Quantity"] == "5"
    assert (tmp_path / "reconciliation.csv").exists()


def test_review_replaces_machine_count_and_produces_valued_adjustments(tmp_path):
    from app.reconcile import ReviewLine

    review = {"c.mp4": [ReviewLine("c.mp4", "IFB Microwave", 5, "kim"), ReviewLine("c.mp4", "TV stand", 2, "kim"), ReviewLine("c.mp4", "TV unit", 1, "kim")]}
    rows = reconcile(BOOK, {"A1-B2": clip(None, 8, review=True)}, review)
    r = by_item(rows)
    assert (r["IFB Microwave"].variance_qty, r["IFB Microwave"].variance_value) == (1, 1000.0)
    assert (r["TV stand"].variance_qty, r["TV stand"].variance_value) == (1, 500.0)
    assert r["TV unit"].status == "match"
    assert "machine count 8 -> reviewed 8" in r["TV unit"].note
    write_reports(rows, tmp_path)
    adj = list(csv.DictReader((tmp_path / "proposed_adjustments.csv").open()))
    assert [a["Item"] for a in adj] == ["IFB Microwave", "TV stand"]


def test_review_item_not_in_book_is_a_variance():
    from app.reconcile import ReviewLine

    review = {"c.mp4": [ReviewLine("c.mp4", "Mystery item", 2, "kim")]}
    rows = by_item(reconcile(BOOK, {"A1-B2": clip(None, 2)}, review))
    assert rows["Mystery item"].status == "variance" and rows["Mystery item"].book_qty == 0
