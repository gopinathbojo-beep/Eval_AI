# ADEM: AI-assisted Digital Examination Management and Evaluation

A local exam-marking platform. **InternVL3.5 4B** (via Ollama) reads documents and suggests marks.
**The application** owns question identity, mapping, maximum marks, validation, audit and the final result.
The teacher approves everything that matters.

```
Teacher login -> exam -> question paper -> OCR -> teacher verifies questions
 -> answer key -> OCR -> deterministic mapping to question IDs -> teacher verifies
 -> student answer sheet -> OCR -> deterministic mapping -> teacher resolves doubts
 -> AI evaluation (validated) -> teacher approves/overrides -> finalize -> result
```

## Requirements
- Python 3.10+ (tested 3.12), Node 18+ (tested 22)
- [Ollama](https://ollama.com) with the model: `ollama pull blaifa/InternVL3_5:4B`
- LibreOffice (`soffice`) only if you upload **DOCX** files. PDFs and images need nothing extra.

## Setup
```bash
# 1. model
ollama pull blaifa/InternVL3_5:4B
ollama list                      # must show blaifa/InternVL3_5:4B

# 2. backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.create_teacher "Your Name" you@school.org 'a-strong-password'   # there is no sign-up page
uvicorn app.main:app --port 8000

# 3. frontend (second terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173 (proxies /api to :8000)

# 4. mobile app (Expo + React Native)
cd mobile
npm install
npx expo start                   # Press 'a' for Android emulator, scan QR with Expo Go on physical device
```
Production-style: `npm run build`, then `npm run preview` (proxy target is set in `vite.config.ts`).

### Mobile App Connectivity
- **Android Emulator**: Uses `http://10.0.2.2:8000` by default.
- **Physical Device (Expo Go)**: Enter your computer's local network IP (e.g. `http://192.168.1.X:8000`) on the Login screen or Settings screen.
- Start the FastAPI backend with host `0.0.0.0` when testing with physical devices:
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Environment (`backend/.env`)
| Variable | Default | Meaning |
|---|---|---|
| `INTERNVL_ENABLED` | `true` | Must be true to process documents |
| `INTERNVL_MODEL` | `blaifa/InternVL3_5:4B` | The only model used. There is no fallback model |
| `INTERNVL_API_URL` | `http://127.0.0.1:11434` | Ollama server (native `/api/chat`) |
| `INTERNVL_TIMEOUT` | `300` | Seconds per model call |
| `SECRET_KEY` | auto | JWT secret. If empty, one is generated into `data/.secret_key` |
| `DATA_DIR` | `../data` | SQLite DB and all files |
| `PDF_RENDER_DPI` | `300` | Render resolution for PDFs |
| `MAX_UPLOAD_MB` | `50` | Upload size limit |

## Run the tests
```bash
cd backend && pytest -q            # 111 tests, ~20 s
cd frontend && npm run build       # type-check + production build
```
The API tests run the **real** HTTP client against a small stand-in for the Ollama server that lives only in `tests/conftest.py`.
The application itself contains no mock mode.

## Where the rules live
| Rule | File |
|---|---|
| Number normalisation (`Q1`, `3 (a)`, `3-a`, `3a` -> `3(a)`) | `backend/app/services/numbering.py` |
| Deterministic mapping, never guessing | `backend/app/services/mapping.py` |
| JSON extraction from model output | `backend/app/ocr/parser.py` |
| Rejecting impossible AI marks | `backend/app/services/evaluation_rules.py` |
| Exam state machine | `backend/app/services/state.py` |
| Finalize checks | `backend/app/services/evaluation_service.py` (`finalize_issues`) |
| Ollama client (retries, validation, no fallback) | `backend/app/ocr/internvl.py` |

### Mapping, in one paragraph
A label maps automatically **only** when its normalised number equals exactly one exam question. `1` never maps to `10`; `3(a)` never maps to `3(b)`.
Bare `3` when the exam has `3(a)`/`3(b)`, `3(a)` when the exam only has `3`, unreadable labels, duplicates (two answers for one question), and low-confidence reads all go to teacher review, with suggested candidates but no auto-selection.
Text similarity and answer order are never used.

### Marks authority
Maximum marks belong to the exam question. If the answer key disagrees, the row shows **MARK MISMATCH** and verification is blocked until the teacher keeps the question's marks or changes them with a recorded reason.
AI marks above the maximum (or negative, or with a different `max_marks`) produce `EVALUATION_ERROR`; they are never clamped silently.
The AI mark is stored separately and never overwritten. A teacher override needs a reason.

## Known limits (please read)
- **Not validated against the real model here.** The sandbox this was built in has no Ollama/GPU. Prompts, bounding-box quality and handwriting accuracy on *your* scans need a trial run on your machine. Prompts are in `backend/app/ocr/prompts.py`.
- **Bounding boxes are approximate.** Small models are unreliable at localisation. The UI labels crops and highlights as approximate, and the full page is always shown next to the data.
- **Orientation:** only EXIF/camera orientation is corrected automatically. Sideways scans are not auto-rotated. "Page boundary" detection is stored as metadata (`content_bbox`) and does not crop.
- **One file per student** (multi-page = one PDF). Multiple loose photos per student are not supported yet.
- **Evaluation is text-only.** The AI grades the transcribed answer, so teachers should check the OCR text for handwriting.
- **No Alembic migrations.** Tables are created with `create_all` on first start, and the existing DB is never dropped. Add Alembic before changing the schema on a database with real data.
- Retrying failed pages **rebuilds** the extracted list for that document (the UI warns first).
- Teacher accounts are created from the command line; there is no password reset UI.

## Troubleshooting
| Symptom | Fix |
|---|---|
| "InternVL3.5 4B is not available..." | Start Ollama (`ollama serve`), run `ollama list`, and pull the exact model name. Settings page has "Check again" |
| Document stuck at `AI error` | Fix Ollama, then press **Retry** on the document |
| Page shows `Failed parse` | Open **Show diagnostics** for the raw model output, then retry the page. Very dense pages may exceed `INTERNVL_NUM_PREDICT` |
| DOCX upload fails | Install LibreOffice, or export the file to PDF |
| Timeouts on large scans | Raise `INTERNVL_TIMEOUT`, lower `PDF_RENDER_DPI` or `OCR_MAX_SIDE` |
| Login always fails | Create the teacher with `python -m app.create_teacher` (same `DATA_DIR`) |
| Browser "Cannot reach the ADEM server" | Backend not running on the proxied port |
