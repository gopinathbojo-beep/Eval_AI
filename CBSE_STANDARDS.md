# CBSE board-paper standards

New exams use the supplied Class 10/12 **2026–27** board-paper patterns (`2026-27.1`). They accept new question and answer content, with flexible visual layouts. They require the complete subject pattern, not shorter unit tests. There is no built-in sample library.

## Supported subjects

| Class 10 | Code | Class 12 | Code |
|---|---|---|---|
| Computer Applications | 165 | Accountancy | 055 |
| English Communicative | 101 | Biology | 044 |
| English Language and Literature | 184 | Chemistry | 043 |
| Hindi Course A | 002 | Computer Science | 083 |
| Hindi Course B | 085 | English Core | 301 |
| Mathematics Basic | 241 | English Elective | 001 |
| Mathematics Standard | 041 | Physics | 042 |
| Science | 086 | Political Science | 028 |
| Social Science | 087 | | |

Choose the class first, then the exact subject variant. Duration and maximum marks come from its profile. Teachers see profiles matching their existing class/subject assignments; management and parents can select supported profiles in their own workspace. Generic historical subjects such as “Maths” require an explicit variant selection. The chosen profile/version stays attached to the exam. Select the paper audience and, for Accountancy, the Part B option.

## Upload and review

1. Upload the full question paper and its matching marking scheme. A scheme uploaded early waits for verified questions.
2. Compare extracted questions with the PDF, edit as needed, and accept them. After page processing completes, **Verify Questions** opens the answer-key step and releases any waiting scheme.
3. Review the uploaded answer key and its mapping to each question. Verify it after resolving ordinary completeness, mapping and mark-mismatch errors.
4. CBSE validation panels and automatic board-pattern gates have been removed. Historical extraction notes do not prevent verification, evaluation submission, worker execution or finalization.
5. Basic checks remain: processing must finish, required answers and marks must exist, mappings must be unambiguous, and teacher review is required. Individual grading results still undergo score and evidence checks.

One canonical row represents a whole question. Its nested tree retains scored parts, OR alternatives, “answer any N” limits and unscored context. Accessibility and Accountancy variants are tagged separately so they do not add extra marks. The student transcription retains subpart labels, and multiple answer blocks belonging to one whole question are combined for grading.

The uploaded scheme supplies the answer content and marking rules. Sample answers from the standards corpus are never substituted into a different paper. AI-generated answers remain drafts and cannot be saved as the official scheme for new board-pattern exams.

## Grading and compatibility

The model judges each reviewed criterion using visible student evidence. The backend checks allocations and computes choice-aware totals. Explicit capped deductions are applied only under their reviewed source rule and within its cap. Positive awards use exact student excerpts; whitespace and equivalent Unicode typography do not invalidate a quote. When the extracted scoring tree has missing or inconsistent allocations, grading uses the uploaded scheme text for a whole-question assessment within the existing maximum instead of guessing step marks. Teacher approval remains necessary before finalization. An explicit question heading conflicting with its mapped question requires mapping review rather than being graded under the wrong question.

Existing exams with no standard profile continue under their historical workflow. No existing users, exams, files, grades, pass thresholds or reports are reset. School cohort grades, parent reports without relative grades/ranks, and omission of K levels remain unchanged.

## API and deployment

- `GET /api/standards?class_id=...`: authorized, class/assignment-filtered catalog and matching workspace subject IDs.
- `POST /api/exams`: accepts `standard_profile_id` and `standard_options`; resolves unambiguous existing subjects automatically. Rejects unsupported/ambiguous subjects and conflicting duration, marks or academic year. No legacy creation bypass exists in production.
- `GET /api/exams/{id}/standard-validation?phase=paper|scheme|evaluation`: current checks, persistent evidence, source locations and expected/detected values.
- `POST /api/exams/{id}/standard-review`: authorized source interpretation corrections with a reason; supports document details, question hierarchy, scheme scoring tree and version options. Revalidates and invalidates previous verification.

The diagnostic and source-review APIs remain available for compatibility, but board-pattern validation is not a workflow gate. Question verification records teacher acceptance and unlocks scheme extraction. All academic access uses existing workspace and assignment checks; inaccessible IDs return 404.

Deploy the backend with additive migration **`20261031_cbse`** before deploying the frontend. Render's existing `AUTO_MIGRATE=true` applies it on startup. For a manually managed database, run `python -m scripts.migrate` from `backend` before starting the updated API. Back up the database before deployment. Do not roll back by dropping columns or deleting evidence; restore a verified backup if necessary.

## Verification and release gate

`app/cbse/sources.json` fingerprints the 34 supplied PDF files and 341 pages without shipping their answer content as a library. Catalog tests check all profiles; API and integration tests check full-pattern creation, source validation, verified uploads, scheme-based grading and legacy compatibility. Browser tests cover role workflows and fixed-pattern exam setup.

Live corpus extraction is opt-in, uses paid API calls and leaves resumable results in ignored `.e2e-data/cbse`:

```powershell
# From backend; ensure the configured OpenRouter key/model is available.
.venv/Scripts/python.exe -B -m scripts.cbse_verify_corpus --workers 1
```

**Live verification is currently pending:** OpenRouter returned HTTP 429, including for a minimal text request. The corpus run was stopped. Do not describe this release as validated on all supplied papers until the provider limit is resolved, every page completes, results are reconciled against the source patterns, and representative real school and parent evaluations are reviewed. Failed reads block evaluation rather than silently passing.

Future academic-year changes require a new profile version. Preserve old profile definitions and fingerprints so existing exams retain their original standard.
