"""Run clips through the pipeline and write the reconciliation and proposed adjustments.

    python scripts/run_pipeline.py "Clip A.mp4" "Clip B.mp4" ... --canonical "A1-B2=Clip B.mp4" [--refresh]

Cached model output in testdata/out is reused, so clips already run need no API key. --canonical names the one
clip counted for each plan location (a shelf filmed several times is counted once).
Writes testdata/out/reconciliation.csv and testdata/out/proposed_adjustments.csv.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import OUT, TESTDATA  # noqa: E402
from app.pipeline import run_clip  # noqa: E402
from app.reconcile import load_book, reconcile, write_reports  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--canonical", action="append", default=[], help='"<location>=<clip file>", one per location')
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--refresh", action="store_true", help="ask Spark again instead of using cached verification")
    args = ap.parse_args()

    book = load_book(TESTDATA / "book_stock.csv")
    results = {}
    for name in args.clips:
        r = run_clip(TESTDATA / name, book, runs=args.runs, refresh_verification=args.refresh)
        results[name] = r
        flag = "REVIEW" if r.needs_review else "auto-pass"
        print(f"{name}: location={r.location} item={r.item} counted={r.counted} [{flag}] {'; '.join(r.reasons)}")
        print(f"   narration: {r.transcript!r}")

    canonical = {}
    for spec in args.canonical:
        location, clip = spec.split("=", 1)
        canonical[location] = results[clip]
    rows = reconcile(book, canonical)
    write_reports(rows, OUT)
    print("\nreconciliation:")
    for row in rows:
        print(f"  {row.location:8} {row.item:26} book {row.book_qty:>3} counted {str(row.counted_qty):>4} var {str(row.variance_qty):>4} value {str(row.variance_value):>8}  {row.status}")
    print(f"\nwrote {OUT / 'reconciliation.csv'} and {OUT / 'proposed_adjustments.csv'}")


if __name__ == "__main__":
    main()
