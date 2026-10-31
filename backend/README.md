# ADEM Backend

FastAPI server for every ADEM app: the Web app (school managers and teachers, :5173), the Admin app (:5174) and the
Parents app (:5175). **InternVL3.5 4B** (via Ollama) reads documents and suggests marks; Tamil and other
Indian-language subjects are read by **IndicOCR** (`indic_ocr_service/`, :8090) and graded by InternVL.
The application owns question identity, mapping, maximum marks, validation, audit and the final result.

## Requirements
- Python 3.11, [Ollama](https://ollama.com) with `ollama pull blaifa/InternVL3_5:4B`
- For Tamil subjects: an NVIDIA GPU (CPU works but is slow) and a Hugging Face account that accepted the
  [IndicOCR licence](https://huggingface.co/bodhan-ai/indic-ocr). See [indic_ocr_service/README.md](indic_ocr_service/README.md).
- LibreOffice (`soffice`) only for DOCX uploads.

## Run
On Windows, use `setup.bat` and `start.bat` in the folder above this one. By hand, from this folder:
```bash
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe scripts\seed_dev.py          # dev accounts (see below)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
First Super Admin on a real server: `python -m app.create_admin "Name" admin@example.org "a-strong-password1"`.

Development accounts from `scripts/seed_dev.py`:

| App | Email | Password |
|---|---|---|
| Admin (:5174) | admin@adem.local | ChangeMe123 (must be changed at first sign-in) |
| Web, teacher (:5173) | rao@school.org | password123 (in the active "Demo School") |
| Parents (:5175) | parent@adem.local | password123 (10 free credits) |

Parents and schools sign up themselves in their apps. Without SMTP settings, every email (confirmation links,
invitations, password resets) is written to `data/outbox/` as an `.eml` file, so links can be opened locally.

## Tests
```bash
.venv\Scripts\python.exe -m pytest -q        # ~380 tests, ~45 s
```
The API tests run the real HTTP client against a stand-in for the Ollama server that lives only in `tests/conftest.py`,
on a throwaway SQLite database. The application itself has no mock mode.

## Accounts and sign-in
- One `users` table; `role` is `platform_admin`, `school_manager`, `teacher` or `parent`. One email = one role.
- Every sign-in names its portal (`admin`, `school`, `teacher`, `parent`); the token is valid for that portal only.
  The Web app signs in with `web`, which takes school managers and teachers; the token still gets the role's portal.
- School managers invite their teachers (`app/routes/staff.py`, `/api/school/teachers`); a teacher joins from the
  emailed link and signs in on the same Web page.
- Role, status and `token_version` are re-read on every request: suspension, role change and "sign out everywhere"
  take effect immediately. Guards live in `app/security.py` (`current_teacher`, `current_school_manager`,
  `current_parent`, `current_admin`, `current_super_admin`).
- Lockout after 5 wrong passwords (15 minutes); rate limits on login, signup and password reset.
- Emailed links (invite, reset, signup confirmation) are single use; only their SHA-256 is stored.
- Google sign-in (`GOOGLE_CLIENT_ID`) creates accounts only for schools and parents; for teachers and admins it signs in
  to an existing or invited account. Off while `GOOGLE_CLIENT_ID` is empty.
- Schools that sign up stay `PENDING` until a Platform Admin approves them; their teachers cannot sign in until then.
- Routes: `app/routes/auth.py`. Rules: `app/services/accounts.py`.

## Credits
One credit evaluates one student's answer sheet. Free tier: 10 credits (parents at signup, schools at approval; once
per phone number). Wallets and the append-only ledger are in `app/services/credits.py`; prices are editable settings.

## Environment (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `INTERNVL_MODEL` / `INTERNVL_API_URL` | `blaifa/InternVL3_5:4B` / `http://127.0.0.1:11434` | Ollama model and server |
| `INDIC_OCR_ENABLED` / `INDIC_OCR_URL` | `false` / `http://127.0.0.1:8090` | IndicOCR for Indian-language subjects |
| `DATABASE_URL` | empty | Empty = SQLite in `DATA_DIR`; or `postgresql+psycopg://...` |
| `DATA_DIR` | `data` | Database, uploaded files, outbox. Relative to this folder |
| `SECRET_KEY` | auto | JWT secret; generated into `data/.secret_key` if empty |
| `CORS_ORIGINS` | ports 5173, 5174, 5175 | The three apps |
| `WEB_URL` / `ADMIN_URL` / `PARENT_URL` | localhost:5173 / 5174 / 5175 | Where emailed links point |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | empty | Email; empty host = write to `data/outbox/` |
| `GOOGLE_CLIENT_ID` | empty | Google sign-in OAuth client |

## Where the rules live
| Rule | File |
|---|---|
| Subject formats (sections, marks) | `app/cbse/class10/subjects/*/format.json`, `app/cbse/class12/subjects/tamil/` |
| Numbering, choices (OR / any N), mapping, mark rules, rubric | `app/cbse/common/` |
| Subject-specific formatting (Tamil, English, Maths, ...) | `app/cbse/common/subjects/` |
| Model output parsing | `app/ocr/parser.py` |
| Ollama client (retries, validation, no fallback) | `app/ocr/internvl.py` |
| Exam state machine | `app/services/state.py` |
| Evaluation and finalize checks | `app/services/evaluation_service.py` |

Sample CBSE papers and marking schemes used by tests and by the paper generator are in `exam/`.
Planning documents are in `docs/`.
