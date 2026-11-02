# Eval AI

Eval AI evaluates CBSE Class 10 and 12 answer sheets for schools, teachers and parents. Gemini reads question papers, marking schemes, diagrams and student answers through OpenRouter. English, Hindi, Tamil and bilingual documents use the same hosted multimodal pipeline; no local model, GPU or OCR service is required.

## Local setup

Requirements: Python 3.11, Node.js 24 and an OpenRouter API key. LibreOffice is optional for DOCX uploads.

1. Run `setup.bat` or install `backend/requirements.txt` and frontend packages manually.
2. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
3. Keep `OPENROUTER_MODEL=google/gemini-3.5-flash-lite` unless a tested replacement is intentionally selected.
4. Run `start.bat`, then open `http://localhost:5173`.

The backend is at `http://127.0.0.1:8000`; `/api/system/ai-status` verifies the OpenRouter key and model. Opening `/` on the backend returns `Not Found` by design.

## AI configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | required | Server-side OpenRouter credential |
| `OPENROUTER_MODEL` | `google/gemini-3.5-flash-lite` | Multimodal extraction and grading model |
| `AI_OCR_REASONING_EFFORT` | `minimal` | Preserve output capacity during page extraction |
| `AI_TEXT_REASONING_EFFORT` | `low` | Limited reasoning for grading |
| `AI_MAX_OUTPUT_TOKENS` | `8192` | Maximum visible/reasoning completion budget |
| `AI_PARALLEL_JOBS` | `1` | Concurrent paid AI jobs |

Dense pages recover by splitting the rendered page into regions. Rate-limited requests are not automatically repeated. All AI marks remain subject to teacher review and server-side maximum-mark validation.

## Subjects

The catalog retains the supplied Class 10 Hindi Course A/B patterns. Hindi Class 12 and Tamil Classes 10/12 are upload-driven, 3-hour, 80-mark language profiles: their uploaded paper and marking scheme define question counts, sections, choices and allocations.

## Verification

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test
npm run build
```

Tests use a local OpenRouter-compatible HTTP stand-in. Before release, run the supplied Maths paper and representative English, Hindi and Tamil documents with the real configured Gemini model.

For Render, Vercel and Supabase deployment, see [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md). For Docker/SQLite deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).
