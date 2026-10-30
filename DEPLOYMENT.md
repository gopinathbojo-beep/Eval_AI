# Deploy the web application

For **Render backend + Vercel frontend + Supabase PostgreSQL/storage + OpenRouter**, follow [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md). The instructions below describe the separate Docker/SQLite deployment option.

The supported topology is **one Linux server, one API process, SQLite on a persistent Docker volume**, and an existing private Ollama/IndicOCR host. Caddy terminates HTTPS, Nginx serves the compiled web app and proxies `/api`. Only ports 80 and 443 are published. No mobile build is involved.

Do not add API workers or replicas: the GPU queue and locks are in-process, and startup recovery/purge scheduling must run once. For multiple servers, migrate to a shared database, object storage and a durable external job queue first. Restarting the current API interrupts queued AI jobs; startup recovery makes interrupted work available for teacher review/retry.

## First deployment

1. Install Docker Engine with Compose v2 on the Linux server. Point a domain's DNS A record (and AAAA only if IPv6 is configured) at it. Open 80/tcp, 443/tcp and optionally 443/udp. Restrict SSH to administrators.
2. Copy this project to the server. Copy `.env.example` to `.env` in the project root. Set `DOMAIN` to the bare hostname, `ACME_EMAIL` to your email, and `SECRET_KEY` to at least 32 random characters. Generate it with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Restrict `.env` permissions to its owner (`chmod 600 .env`). The older root file named `env` is ignored and is **not** loaded by Compose or the backend.
3. Set `INTERNVL_API_URL` to the private Ollama endpoint and enable/configure IndicOCR if needed. The defaults address a service on the Docker host. Such host services must listen on an address reachable from the container, with firewall rules allowing only the private API host/network. Do not expose Ollama or IndicOCR publicly. Pull `blaifa/InternVL3_5:4B` on that GPU host and verify its model licence and hardware requirements for your use.
4. Run from the project root:

   ```sh
   docker compose config --quiet
   docker compose build --pull
   docker compose up -d
   docker compose ps
   docker compose logs --tail=100 backend edge
   ```

5. Sign in with the protected owner Google account to open `/admin`. Schools and parents register at `/register` and complete their profile without administrator approval. School management creates teacher accounts at `/management`; teachers change their temporary password at `/account` before entering the workspace. See [WORKSPACES.md](WORKSPACES.md) for account setup and permissions.

6. Visit `https://YOUR_DOMAIN`. Caddy obtains and renews the certificate automatically. Verify login, refresh on a deep URL, logout, uploads, real OCR and AI evaluation, teacher review, finalization, and PDF/XLSX exports with a representative exam before onboarding users. Visually check reports for every language you use: Linux has Noto fonts, but complex-script shaping and glyph coverage must be validated on your actual reports.

The deployment starts with an empty `app_data` volume. To migrate existing data, back it up first, stop the old API, and copy the **entire** old DATA_DIR into the new volume using the restore procedure below. Never copy a live SQLite database without its WAL state. Keep the old data until the migrated instance is verified. Ensure restored files are owned by UID/GID 10001.

## Security and limits

### Owner, teacher access and Google sign-in

The owner is `seyamesh91@gmail.com` (backend `ADMIN_EMAIL`). On startup this account is provisioned without a default password. Sign in with that verified Google account to open `/admin`. At `/account`, set a password if you also want password sign-in. The owner can edit accounts/profiles, reset passwords, enable/disable users and workspaces, inspect activity and see usage totals. School management creates teachers. Emails connected to Google cannot be changed through ordinary profile editing. Accounts are disabled instead of deleted, preserving academic data and activity history.

Public registration is available at `/register` using Google or email/password for school management and parents. New users complete their school or single-child family profile at `/onboarding` and immediately receive access. No approval is required. Teachers are provisioned by their school management with exact class/subject assignments. Only CBSE Classes 10 and 12 are supported. Profile and temporary-password requirements are enforced by the API.

Google verifies email ownership. Email/password registrations do not send verification email because no mail provider is configured. An existing password account must first sign in and connect Google through `/account`; an unauthenticated Google callback never replaces its password or links that account. School-created teachers also connect Google through this authenticated flow. Both login methods remain supported.

The workspace release starts with a clean demo-data reset after backup. No invitation or password-reset email is sent automatically. Share teacher credentials securely. Management and admin can reset passwords; teacher resets require another first-login password change. Disabling a school workspace blocks all members and revokes their sessions; re-enabling does not revive old sessions. Admin can inspect users, workspaces and date-filtered activity and AI usage. Payments are not enforced in this release.

For local development, the backend reads **only OAuth settings** from the root `.env`, supporting your existing `Client_ID` and `Client_secret` keys as aliases for `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Other local backend settings still come from `backend/.env` or environment variables. Use `http://localhost:5173`; register `http://localhost:5173/api/auth/google/callback` as an authorized redirect URI in Google Cloud. The OAuth start URL uses this canonical hostname even if the login page was opened via `127.0.0.1`.

For Compose, set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the root `.env` (the legacy aliases also work). Compose sets `GOOGLE_REDIRECT_URI=https://YOUR_DOMAIN/api/auth/google/callback`; register that exact URI with Google. Keep the Google app in Testing with your testers listed until ready to publish. No Gmail or Drive scopes are requested. OAuth state uses a separate signed HttpOnly cookie with SameSite=Lax for the Google callback; the application session retains SameSite=Strict. Google codes/tokens are not exposed to frontend JavaScript or retained in activity records, and access logs omit query strings.

Class/exam counts describe current records. Upload counts use retained audit events and include each file in a bulk upload, even if later removed. AI run/request counts begin with this release, so earlier evaluations are not reconstructed as new usage. Runs include full answer-sheet evaluation and question retries; grading requests include failures but exclude OCR, key generation and internal HTTP retries. Run completion indicates that the job finished; individual grading answers can still require teacher review. The activity list excludes raw student answers and uploaded filenames. It is an application activity log, not a browser click tracker.

- Browser authentication uses an HttpOnly, Secure, SameSite=Strict cookie. Cookie writes require the web client's custom header and an approved origin. Mobile bearer login remains supported; query-string tokens are rejected in production. Existing web users must sign in again after this upgrade.
- The default production session expires after 60 minutes. Logout clears the browser cookie; signed bearer tokens remain valid until expiry. Rotate `SECRET_KEY` to invalidate all existing sessions in an emergency (and update your securely stored backup of it).
- Sign-in allows 20 attempts per client IP per minute, including successful attempts. Adjust `LOGIN_ATTEMPTS_PER_MINUTE` for schools behind shared NAT. Proxy headers are trusted only because API/web ports are private; do not publish these ports or attach untrusted containers to their networks.
- API responses are not cached. Fingerprinted assets are cached for a year; HTML is revalidated. CSP allows only local scripts, with inline styles retained for KaTeX and the UI.
- Each upload is limited to 50 MB; the reverse proxy caps a complete multipart request at 100 MB. Split larger bulk batches. Temporary file space is limited to 512 MB per API container. Monitor RAM, disk, upload concurrency and GPU queue length before expanding usage.
- Existing behavior deletes uploaded originals, page images, crops and raw AI output **24 hours after exam finalization**, while keeping reports and database results. Confirm this retention policy meets your school's needs before use. Backups may retain deleted data longer; set their retention/access policy deliberately.
- Store `.env`, backups, Docker volumes and host disks securely. Rotate any secret previously committed/shared. Never place secrets in frontend assets. Production startup rejects missing/short secrets, insecure cookies and wildcard origins/hosts. API docs are disabled in production.

## Verification and CI

### Report grading

Generated student reports, term report cards and class exam PDFs omit K-level columns and analysis sections. K-level data elsewhere in the evaluation system is retained. School grades A-1 through D-2 represent successive eighths of passed candidates in the relevant exam cohort; term subject grades use their respective exams, and overall grades use fully evaluated students in the authorized class/year/term. E means failed / Essential Repeat. Family reports and exports show marks, percentages, feedback and pass/fail without comparative grades, ranks or principal signatures. The existing pass threshold is 33% per subject, checked without display rounding. Overall passing requires every subject to pass; incomplete cards have no overall grade or rank.

Equal scores share the higher band at their first rank, so ties and small classes can produce uneven/empty bands. Grades are computed over the whole class even when exporting only one student. As more results are finalized, relative grades can change. Student report downloads are regenerated from retained database results; existing archived PDFs on disk are preserved rather than rewritten. Template previews show illustrative grades.

Use Node 24 and Python 3.11. The frontend lockfile and hashed backend lockfile are committed. To update the latter intentionally: `uv pip compile backend/requirements.txt --universal --generate-hashes --output-file backend/requirements.lock`.

```sh
cd frontend
npm ci
npm test
npm run build
npm audit --audit-level=moderate
cd ../backend
python -m pip install --require-hashes -r requirements.lock
python -m pytest -q
```

GitHub Actions runs these checks, API dependency auditing, browser tests and container builds. It does not publish anything automatically. In staging, run `node deploy/smoke.mjs https://YOUR_DOMAIN` to check HTTPS, headers, deep links, assets and API routing. This does not replace the real-model trial above: automated API tests use an Ollama stand-in.

## Backups, restore and updates

`app_data` holds SQLite, uploads, generated reports and the generated development secret (production uses `.env`). Caddy's certificate state is in `caddy_data`. Keep `.env` separately in your secure secret backup.

For a consistent database **and matching document files**, schedule a maintenance window, wait for active AI work to finish, stop the API, then archive the volume. These commands use a one-off API container with its normal user:

```sh
mkdir -p backups
sudo chown 10001:10001 backups
docker compose stop backend
docker compose run --rm --no-deps -v "$PWD/backups:/backups" backend python scripts/backup_data.py /backups
docker compose up -d backend
```

The backup command prints the archive path and SHA-256 checksum. It creates a permission-restricted archive, checks SQLite integrity, and excludes WAL/SHM after taking a SQLite snapshot. Copy backups off the server, encrypt them, automate this procedure to your maintenance schedule, and test restoration regularly. If backup fails, restart the API and investigate before the next deployment. Do not use `docker compose down -v`: that deletes persistent volumes.

Restore to a **fresh deployment/empty volume** after first verifying the archive checksum and preserving a backup of any existing volume. Stop the API, then run:

```sh
docker compose stop backend
docker compose run --rm --no-deps -v "$PWD/backups:/backups:ro" backend python scripts/backup_data.py --restore /backups/EXACT_ARCHIVE_NAME.tar.gz
docker compose up -d backend
```

The restore command refuses a nonempty target, unsafe paths, and links. Restore `.env` securely, retain the same domain/key where appropriate, and run the smoke test and account/data checks before opening traffic.

Before each update, make a backup and keep the previously deployed source revision/container images. Build and test the new revision, then run `docker compose up -d --build`. Check `/api/ready`, container health, logs and a real workflow. If rollback is needed, restore the previous source/images; if schema changes are involved, restore the matching database/files backup into a fresh volume too. Do not blindly run old code against a newer schema.

Monitor container health and restarts, external HTTPS `/api/ready`, free disk, RAM, GPU errors, backup age, 5xx responses and AI queue delays. `/api/health` is liveness; `/api/ready` checks database connectivity; authenticated Settings shows AI availability. Logs rotate at 3 × 10 MB per service. Health checks report failure but do not themselves restart an unhealthy process; use your host monitoring to alert an operator.
