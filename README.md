# ADEM: AI-assisted Digital Examination Management and Evaluation

CBSE Class 10 and 12 exam evaluation for schools, teachers and parents, with one setup and one start script. Two
folders: `backend/` and `frontend/`. Each app is its own repository. The web apps in `frontend/` share one
`node_modules` there (npm workspaces): run `npm install` in `frontend/`, not in each app.

| Folder | What it is | Port |
|---|---|---|
| `backend/` | FastAPI server and AI pipeline (repo Eval_AI_Backend) | 8000 |
| `backend/indic_ocr_service/` | IndicOCR service for Tamil and other Indian languages | 8090 |
| `backend/data/` | Database, uploaded files, email outbox (not in git) | |
| `backend/exam/`, `backend/docs/` | Sample papers and keys; deployment guide and reports | |
| `frontend/web/` | School management and the teachers they invite (repo Eval_AI_WEB) | 5173 |
| `frontend/admin/` | Platform Admin console (repo Eval_AI_Admin) | 5174 |
| `frontend/parent/` | Parents: children, timed exams, reports (repo Eval_AI_Parents) | 5175 |
| `mobile/` | Expo mobile app | 8081 |

## Windows quick start
1. **`setup.bat`**: creates the Python environments, installs every app, and creates dev accounts.
2. **`start.bat`**: starts IndicOCR (if local), the backend and all apps, each in its own window.
3. **`stop.bat`**: stops them all.

Dev accounts: Admin `admin@adem.local` / `ChangeMe123` (change at first sign-in); teacher `rao@school.org` /
`password123`; parent `parent@adem.local` / `password123`. Parents and schools can also sign up in their apps. Without SMTP settings, emails (confirmation links,
invitations, resets) are saved in `backend/data/outbox/`.

Details: [backend/README.md](backend/README.md).
