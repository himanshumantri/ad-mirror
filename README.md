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

## Status
Day 1 of a 5-day build. See the plan for the schedule.
