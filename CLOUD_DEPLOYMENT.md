# Render + Vercel + Supabase deployment

The API runs as one Docker service on Render. Vercel serves the web frontend and proxies `/api` to Render. Supabase PostgreSQL stores application records; a **private** Supabase Storage bucket stores documents and reports. OpenRouter provides vision and grading through `qwen/qwen3-vl-8b-instruct`. No local GPU or IndicOCR is required for this configuration.

## 5. Push the deployment code

Review and push the project changes to your GitHub repository. Never commit `.env`, service-role keys, database passwords or OAuth secrets. The root `.env` is for local development; Render requires its own environment variables.

## 6. Create the Vercel frontend

1. In Vercel, choose **Add New → Project** and import the repository.
2. Set **Root Directory** to `frontend`, framework **Vite**, Node.js **24.x**, install command `npm ci`, build command `npm run build`, output directory `dist`.
3. Deploy and record the production origin, for example `https://YOUR-PROJECT.vercel.app`.

The first frontend deployment intentionally has an unconfigured API destination. Its login will work only after step 8. Do not put backend credentials in Vercel or in `VITE_*` variables.

## 7. Create the Render backend

Choose **New → Blueprint**, connect this repository and select its root `render.yaml`. It defines a Docker web service with root directory `backend`, one API process, `/api/ready` health check and automatic migrations. Choose the region nearest Supabase.

Fill the prompted variables with your own values:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase PostgreSQL connection string, preferably the transaction pooler when direct IPv6 is unavailable; URL-encode password special characters |
| `SUPABASE_URL` | `https://YOUR-PROJECT.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend-only service-role key |
| `OPENROUTER_API_KEY` | Your OpenRouter key |
| `GOOGLE_CLIENT_ID` | Value currently named `Client_ID` in your local file |
| `GOOGLE_CLIENT_SECRET` | Value currently named `Client_secret` in your local file |
| `PUBLIC_WEB_URL` | Exact Vercel production origin, without trailing slash |
| `GOOGLE_REDIRECT_URI` | `https://YOUR-PROJECT.vercel.app/api/auth/google/callback` |
| `CORS_ORIGINS` | `https://YOUR-PROJECT.vercel.app` |
| `ALLOWED_HOSTS` | Your Render hostname, your Vercel hostname, `localhost,127.0.0.1`, separated by commas; no schemes |

Render generates `SECRET_KEY`. Keep it stable across deployments. If your bucket name differs from `eval-ai-documents`, change `SUPABASE_STORAGE_BUCKET`. The bucket must remain private. App tables have row-level security enabled; application authorization is enforced by the backend. The browser receives short-lived upload URLs, never the service-role key.

If Render assigns its hostname after the first deployment, update `ALLOWED_HOSTS` to include that exact hostname and redeploy. Startup installs the schema and provisions the protected owner without a default password. It does not import or erase the old SQLite database. A previously initialized database without migration history is rejected rather than overwritten.

Check the Render logs and visit `https://YOUR-SERVICE.onrender.com/api/ready`. It should return HTTP 200. Retain a single service instance and one API worker.

## 8. Connect Vercel to Render

From the `frontend` directory run:

```powershell
npm run configure:api -- https://YOUR-SERVICE.onrender.com
```

This replaces the safe placeholder in `frontend/vercel.json` with your real API origin. Commit and push that file, then redeploy Vercel. Keep browser API calls on `/api`; the same-origin proxy preserves secure session cookies.

## 9. Complete Google OAuth

In Google Cloud Console, open your OAuth web client. Add the Vercel production origin to authorized JavaScript origins and the **exact** `GOOGLE_REDIRECT_URI` above to authorized redirect URIs. Keep your localhost entries if you still use local development. If the OAuth consent screen is in Testing, add the accounts that need access as test users.

Sign in through the Vercel URL with `seyamesh91@gmail.com` to open `/admin`. School management and parents can register without approval. Teachers are created by school management. See [WORKSPACES.md](WORKSPACES.md).

## 10. Verify before inviting users

Test registration, Google and password login, logout, school and parent profiles, teacher provisioning, uploads, OCR, evaluation, review and report downloads. Test a multi-page handwritten answer sheet, not only a small sample. Refresh a deep route such as `/admin`. Redeploy the backend and verify saved exams and files remain available.

The API uses `/tmp/eval-ai` only as a disposable processing cache. PostgreSQL retains job records; queued jobs resume after restart. Interrupted running jobs become available for explicit retry, avoiding an automatic repeat of paid AI calls. Reports and source documents are stored remotely. Configure Supabase database backups and private-bucket backup/retention before storing important student records.

Render Free sleeps after 15 minutes without incoming traffic and may interrupt background evaluations. Use it for a pilot; use an always-on paid service for reliable evaluation processing. This phase does not introduce a separate worker service or multiple API replicas. See [Render Free limits](https://render.com/docs/free) and [Vercel external rewrites](https://vercel.com/docs/routing/rewrites).

## Local checks and future VLM endpoint

The backend reads root `.env`, then `backend/.env` if present; process environment variables take precedence. A populated `backend/.env` can override root settings, so avoid stale duplicate values. The legacy root file named `env` is not loaded.

From `backend`:

```powershell
.venv/Scripts/python.exe -B -m scripts.cloud_check
.venv/Scripts/python.exe -B -m scripts.migrate
```

The check reports connection status without printing credentials. Migrations are also run at startup when `AUTO_MIGRATE=true`.

For your future hosted VLM, set `AI_PROVIDER=custom`, `CUSTOM_AI_BASE_URL=https://YOUR-ENDPOINT/v1`, `CUSTOM_AI_API_KEY` and `CUSTOM_AI_MODEL`. The endpoint must implement OpenAI-compatible chat completions with image input and JSON responses. Keep `INDIC_OCR_ENABLED=false` until a separately hosted IndicOCR service is explicitly configured. If a provider omits token probabilities, OCR confidence is capped for teacher review rather than presented as measured confidence.
