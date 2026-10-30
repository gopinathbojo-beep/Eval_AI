# School and family workspaces

Eval AI supports CBSE Classes 10 and 12. This release uses SQLite, local document storage and the existing in-process AI queue. AWS, PostgreSQL, S3, durable workers and payments are separate future work.

## Start using the application

- **Owner:** sign in with `seyamesh91@gmail.com` through Google, then open `/admin`. No default password is created. Set a password through `/account` if desired.
- **School management:** register at `/register`, choose school management, and complete the school/contact details. Access is immediate. Create classes and subjects, import students, then open `/management` to create teachers and assign class/subject pairs.
- **Teachers:** sign in with the email and temporary password supplied by management. Change the password at `/account`. Create and evaluate exams for assigned class/subject pairs.
- **Parents:** register as a parent and provide contact details and one child's name and Class 10 or 12. Create subjects and exams for that child. Update the family profile at `/family`.

Each email has one role and belongs to at most one workspace. A school has one management account; teachers cannot self-register. There is no school approval process or payment restriction in this release.

## Permissions and ownership

School classes, subjects, student rosters, branding and templates belong to the school workspace. The legacy `teacher_id` on shared records identifies the workspace owner for API compatibility. Exams additionally retain their creator in `teacher_id` and their workspace in `workspace_id`. The Python `User` alias and existing `teacher` authentication response are retained for older API consumers. The mobile frontend was subsequently removed from the active project during cleanup and retained in `backups/mobile-source-before-removal-20261030/` for recovery.

Management can view, edit and evaluate all exams in its school. Teachers can read assigned classes/subjects and their students, and access only exams they created for current exact class/subject assignments. Teachers cannot change the shared roster or branding. Removing assignments revokes existing sessions and access to affected exams. Restoring assignments restores access after sign-in. Disabling a teacher preserves academic records.

Family accounts have one child. Uploads are automatically linked to that child; a second answer sheet for the same exam is rejected until the previous sheet is removed. School and family resources cannot be accessed across workspace boundaries, including document downloads and reference examples.

School reports use shared school branding and relative grades in the existing exam cohort. Parent reports and result exports have marks, percentages, feedback and pass/fail without relative grades, rank or principal signatures. Pass thresholds and evaluation rules are otherwise unchanged.

Background jobs carry the requesting actor and check current workspace/account/assignment access before execution. Jobs skipped after access changes become available for review/retry. The queue remains in-process and still requires a single API process.

## Imports and credentials

Download the Excel template from the student import dialog or `/api/students/import-template`. Headers: Name, Roll Number, Registration Number, Class, Section. Class must be 10 or 12. Imports first preview additions, updates and row errors. Correct all errors and confirm before saving; each confirmed import is atomic. Name/registration identity conflicts must be corrected explicitly rather than silently overwriting another student.

No invitation, verification or password-reset email is sent. Management and admin perform password resets in the UI. A teacher must change a reset temporary password before accessing school data. Existing password accounts connect Google while signed in at `/account`; an ordinary Google login cannot silently claim them.

## Administration and usage

`/admin` provides role/search filters, date-filtered usage, account/profile editing, workspace suspension and activity. Usage distinguishes the acting user from the workspace owning the exam. Uploads count files, AI evaluation runs include retries, and grading requests include failed requests but exclude OCR. Counts are application activity rather than browser page views. Profile and password requirements replace approval; compatibility fields such as `approval_status` are not authorization gates.

## Demo reset performed on 2026-10-30

The local API was stopped before backup. A consistent database/document archive was created and restored successfully into an isolated temporary directory before the active demo data was moved out.

- Archive: `backups/eval-ai-20261030T100509029657Z.tar.gz`
- SHA-256: `699fe8504f179e9f8acbc7b3fa3e22be25051674bea70553c0ee285b89a6728e`
- Original demo directory contents: `backups/demo-before-workspaces-20261030/`
- Active data: fresh workspace schema with only the protected owner account.

The root `.env`, legacy `env`, local secret, source code and downloaded AI model caches were preserved. These backups contain personal/application data and must remain private. To recover the old demo, stop the API and restore the archive into an empty directory with `backend/scripts/backup_data.py`; use the matching old application revision for old account behavior. Never overwrite a live database.

## Verification

Backend tests cover school/family registration, cross-workspace access, teacher assignments, temporary passwords, workspace suspension, import preview/confirmation and report contents. Browser tests cover admin, school provisioning, teacher first login, parent profile and cookie sessions. `backend/scripts/workspace_smoke.py` exercises both school and parent workflows against the configured live VLM in a temporary database and writes inspection reports under ignored `.e2e-data/live-reports/`. It does not change active application records. Generated test reports/caches and unused logo source from the cleanup are recoverable under `backups/generated-cleanup-20261030/`; obsolete teacher/marksheet source is archived in `backups/retired-source-before-cleanup-20261030.zip`. Installed dependencies and the sample exam PDFs were kept.
