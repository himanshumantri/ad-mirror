"""Reconcile counted stock against book stock and write ERP-friendly files.

Book stock is an export from the customer's inventory system (item, location, qty, unit cost). One canonical
clip per location is counted; a re-film replaces the earlier clip so the same shelf is never counted twice.

Outputs (see `write_reports`):
- reconciliation.csv: one row per book line, plus a location-total row for mixed clips, for side-by-side comparison with the ERP.
- proposed_adjustments.csv: variance rows only, in the column layout of a NetSuite Inventory Adjustment CSV import.
  Those column names come from community documentation, not an official schema: confirm with a test import
  before relying on them. Adjustment account and reason are the customer's accounting choices and are left blank.

Cartons are treated as units (1 carton = 1 book unit). Pack sizes are not modelled yet.
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path

TOTAL = "(all items at location)"


@dataclass
class BookLine:
    item: str
    location: str
    book_qty: int
    unit_cost: float


@dataclass
class ClipResult:
    clip: str
    location: str | None
    item: str | None  # the one item named in the narration; None for a mixed or unnamed clip
    counted: int
    needs_review: bool
    reasons: list[str] = field(default_factory=list)
    evidence: str = ""
    transcript: str = ""


@dataclass
class Row:
    location: str
    item: str
    book_qty: int
    counted_qty: int | None
    unit_cost: float | None
    status: str  # match | variance | pending_review | not_counted
    evidence: str = ""
    note: str = ""
    count_source: str = ""  # machine | reviewed; blank when nothing was counted
    reviewer: str = ""
    flag: str = ""  # e.g. a possible transfer between locations

    @property
    def variance_qty(self) -> int | None:
        return None if self.counted_qty is None else self.counted_qty - self.book_qty

    @property
    def variance_value(self) -> float | None:
        if self.variance_qty is None or self.unit_cost is None:
            return None
        return round(self.variance_qty * self.unit_cost, 2)


@dataclass
class ReviewLine:
    """A human decision: `qty` cartons of `item` in the clip. A clip's lines replace its machine count."""
    clip: str
    item: str
    qty: int
    reviewer: str
    note: str = ""


def load_reviews(path: Path) -> dict[str, list[ReviewLine]]:
    """reviews.csv columns: clip, item, qty, reviewer, note. One row per item the reviewer counted."""
    reviews: dict[str, list[ReviewLine]] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                reviews.setdefault(r["clip"].strip(), []).append(ReviewLine(r["clip"].strip(), r["item"].strip(), int(r["qty"]), r["reviewer"].strip(), r.get("note", "").strip()))
    return reviews


def load_book(path: Path) -> list[BookLine]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [BookLine(r["item"].strip(), r["location"].strip(), int(r["book_qty"]), float(r["unit_cost"])) for r in csv.DictReader(fh)]


def _status(counted: int, book: int, review: bool) -> str:
    if review:
        return "pending_review"
    return "match" if counted == book else "variance"


def reconcile(book: list[BookLine], canonical: dict[str, ClipResult], reviews: dict[str, list[ReviewLine]] | None = None) -> list[Row]:
    """`canonical` maps a plan location to the one clip counted for it.

    If a human review exists for that clip, its per-item counts replace the machine count; the machine count
    stays in the note so the change is visible in the audit trail.
    """
    rows: list[Row] = []
    for location in dict.fromkeys(b.location for b in book):
        lines = [b for b in book if b.location == location]
        result = canonical.get(location)
        review = (reviews or {}).get(result.clip) if result else None
        if result and review:
            counted = {r.item: r.qty for r in review}
            who = ", ".join(sorted({r.reviewer for r in review}))
            note = f"reviewed by {who}; machine count {result.counted} -> reviewed {sum(counted.values())}"
            for b in lines:
                qty = counted.pop(b.item, 0)
                rows.append(Row(location, b.item, b.book_qty, qty, b.unit_cost, _status(qty, b.book_qty, False), result.evidence, note, "reviewed", who))
            for item, qty in counted.items():  # counted but not in the book for this location
                rows.append(Row(location, item, 0, qty, None, "variance", result.evidence, note + "; not in book for this location", "reviewed", who))
            continue
        for b in lines:
            if result is None:
                rows.append(Row(location, b.item, b.book_qty, None, b.unit_cost, "not_counted", note="no clip for this location"))
            elif result.item == b.item:
                rows.append(Row(location, b.item, b.book_qty, result.counted, b.unit_cost, _status(result.counted, b.book_qty, result.needs_review), result.evidence, "; ".join(result.reasons), "machine"))
            elif result.item is None:
                rows.append(Row(location, b.item, b.book_qty, None, b.unit_cost, "pending_review", result.evidence, "mixed clip: assign cartons to items"))
            else:
                rows.append(Row(location, b.item, b.book_qty, None, b.unit_cost, "not_counted", note=f"clip names {result.item} only"))
        if result is not None and result.item is None:
            # Mixed clip: cartons cannot yet be assigned to items, so compare the location total.
            total_book = sum(b.book_qty for b in lines)
            note = "; ".join([result.clip, *result.reasons])
            rows.append(Row(location, TOTAL, total_book, result.counted, None, _status(result.counted, total_book, result.needs_review), result.evidence, note, "machine"))
    _flag_transfers(rows)
    return rows


def _flag_transfers(rows: list[Row]) -> None:
    """Mark variances of the same item with opposite signs at different locations: a misplaced carton looks like
    a loss in one place and a gain in another, and may be a transfer, not an adjustment."""
    variances = [r for r in rows if r.status == "variance" and r.item != TOTAL and r.variance_qty]
    for r in variances:
        others = sorted({o.location for o in variances if o.item == r.item and o.location != r.location and (o.variance_qty > 0) != (r.variance_qty > 0)})
        if others:
            r.flag = "possible transfer with " + ", ".join(others)


def _memo(r: Row) -> str:
    """Memo for the ERP: what was counted, by whom, the evidence frame, and any transfer flag."""
    by = f"reviewed by {r.reviewer}" if r.count_source == "reviewed" else r.count_source
    parts = [f"LedgerEyes count {r.location}: book {r.book_qty}, counted {r.counted_qty}", by, f"evidence {r.evidence}" if r.evidence else "", r.flag]
    return "; ".join(p for p in parts if p)


def _fmt(v) -> str:
    return "" if v is None else str(v)


def write_reports(rows: list[Row], out_dir: Path, adjustment_location: str = "", adjustment_account: str = "") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "reconciliation.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["location", "item", "book_qty", "counted_qty", "variance_qty", "unit_cost", "variance_value", "status", "count_source", "reviewer", "flag", "evidence_frame", "note"])
        for r in rows:
            w.writerow([r.location, r.item, r.book_qty, _fmt(r.counted_qty), _fmt(r.variance_qty), _fmt(r.unit_cost), _fmt(r.variance_value), r.status, r.count_source, r.reviewer, r.flag, r.evidence, r.note])
    with (out_dir / "proposed_adjustments.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Adjustment Location", "Adjustment Account", "Adjust Qty. By", "New Quantity", "Unit Cost", "Memo"])
        for r in rows:
            if r.status == "variance" and r.item != TOTAL:
                w.writerow([r.item, adjustment_location or r.location, adjustment_account, r.variance_qty, r.counted_qty, _fmt(r.unit_cost), _memo(r)])
