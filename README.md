# LedgerEyes

Turns a phone video of a stockroom into an audit-ready count, reconciled to the books. The business runs it; the auditor or lender receives the evidence.

## Stack
- Frontend: React (Vite PWA), hosted on Vercel
- Backend: Python (FastAPI) with a background worker and Postgres, hosted on Render (US region)
- Video, frames and evidence packs: S3-compatible object storage, uploaded directly from the browser

## Models: Meta only
| Model | Job |
| --- | --- |
| Segment Anything Model 3.1 | Finds, masks and tracks every instance of an item (text phrase or boxed example) |
| Muse Spark 1.3 | Reads labels and serials, classifies items, spots damage, checks capture against the plan |
| Muse Voice Transcribe | Transcribes narration and ties video segments to locations |
| Muse Glimmer (later) | Open-weight option for customers whose data cannot leave their premises |

No other models are used. Allowed non-model utilities: ffmpeg (frame extraction), `hashlib`/`cryptography` (sealing), numpy pixel statistics (lighting and steadiness checks). No OCR, ASR, detection or embedding libraries.

## Setup
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set MODEL_API_KEY=...
python scripts/smoke_models.py
```
`smoke_models.py` lists every model ID the key can see. Base URL defaults to `https://api.meta.ai/v1`; override with `META_API_BASE_URL`.

## How a clip is counted
1. **Muse Voice Transcribe** transcribes the narration; `app/narration.py` turns "aisle one bay area two" into a plan location and finds the item named.
2. **SAM 3.1** tracks every "cardboard box" through the clip (`app/sam_client.py`). Its output is parsed and filtered per frame (`app/segmentation.py`).
3. **Muse Spark 1.3** checks each SAM box on the clip's best frame, 3 times, majority vote (`app/verification.py`). The count is the number of boxes verified in at least 2 of 3 runs.
4. Anything disputed, split between runs, or seen by Spark with no box sends the clip to human review, with a colour-coded frame (green verified, orange disputed, blue ? uncovered).
5. `app/reconcile.py` compares counts with book stock, values variances at cost, and writes `reconciliation.csv` and `proposed_adjustments.csv`.

Model output is cached in `testdata/out/`, so everything after the model calls reruns offline.

## What we learned (build log)
| Step | Finding | Decision |
| --- | --- | --- |
| API check | `sam-3.1`, `muse-spark-1.3` and `muse-voice-transcribe-1.0` are all visible to the key; base URL `https://api.meta.ai/v1` | Hosted API is the main path; Baseten or Spark Open only as a fallback |
| SAM on video | Text prompts work and give masks, confidence and ids. Box prompts mark one object; "find every look-alike from one example" is not documented for the hosted API | Use a text phrase; derive hard-to-name items from Spark |
| SAM ids | Every clip returned exactly 16 distinct ids (probably a cap), and the docs say ids are unreliable across exit, re-entry and occlusion | Never count unique ids; count filtered boxes per frame |
| Filters | Confidence 0.8+, area 4-70% of frame, overlap suppression, then the 80th percentile of per-frame counts. Box size and edge rules cannot tell "more than half visible" | Don't tune thresholds on four clips; add a second opinion |
| Spark check | Per-box verdicts matched the frames; majority of 3 runs was exact on A, B, C and, with its stable uncovered cartons, on D | Spark verifies SAM; uncovered cartons are review triggers, not counts |
| Units bug | Spark returned uncovered boxes in pixels, percent or per-mille | Prompt states pixel size; boxes outside the image are dropped |
| Voice | Transcript was accurate and item names were recognised; timestamps are per turn, not per word | Staff should say a standard location phrase |
| Footage | Some clips are filmed sideways; cartons are visually identical, so item identity comes from narration or labels | Capture check for orientation (todo); mixed clips compare location totals |

Known limits: four clips of one shelf is not an accuracy claim. Accuracy needs footage of other shelves, scored against hand counts. Cartons are treated as units (no pack sizes). The NetSuite-style adjustment columns come from community docs and need a test import.

## Running it
```
cd backend
.\.venv\Scripts\python.exe -m pytest                                  # unit tests
.\.venv\Scripts\python.exe scripts\evaluate.py                        # score cached SAM output vs testdata\clip_truth.csv
.\.venv\Scripts\python.exe scripts\run_pipeline.py "Clip A.mp4" --canonical "A1-B2=Clip A.mp4"
```
Model calls need `MODEL_API_KEY`. `testdata/` (clips, book_stock.csv, clip_truth.csv, cached output) is git-ignored.

## Next steps
1. Run all four clips through the pipeline, check what the narration resolver makes of B, C and D, and settle how mixed clips are split between items.
2. Backend service: Postgres schema, FastAPI endpoints for plan, upload, jobs and results, and a hello-world deploy to Render and Vercel.
3. Frontend: guided capture with hash and timestamp at capture, then the reviewer queue that feeds confirmed counts into reconciliation.
