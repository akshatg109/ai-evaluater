# Batch Answer-Sheet Evaluation Plan

## Confirmed Scope

- Evaluate up to 60 student answer sheets in one batch.
- Use one shared question paper for the batch.
- Support one optional shared answer key.
- Show progress while the batch is being processed.
- Show a result summary with per-sheet scores and feedback.
- Provide an individual PDF report for each completed answer sheet.
- Use a Render background worker and Supabase for durable batch state and storage.

Combined PDF and CSV/Excel export are outside the current scope.

## Current Constraints

The current application evaluates one answer sheet synchronously through `POST /evaluate`.
Each evaluation makes two OpenRouter calls, stores one result in the session, and optionally
writes one row to the `evaluations` Supabase table.

A batch of 60 files should not be submitted as one large multipart request. At the current
20 MB per-file limit, that request could exceed 1 GB and would not be reliable on Render.
The complete result set also cannot be stored in the Flask session cookie.

## Target Workflow

1. The user selects one question paper, an optional answer key, and up to 60 answer sheets.
2. The browser creates a batch and validates the selected files.
3. Each file is uploaded in a separate request to private Supabase Storage.
4. The browser starts the batch after all uploads finish successfully.
5. The API returns a batch URL immediately instead of waiting for AI processing.
6. The results page polls the batch status endpoint.
7. A Render worker claims the queued batch from Supabase.
8. The worker reads the shared question paper and answer key once.
9. The worker transcribes and evaluates each answer sheet independently.
10. The worker persists each result or failure immediately, allowing progress to survive restarts.
11. The results page displays completed results as they become available.
12. Users can download an individual PDF report for every completed sheet.

## Backend Changes

### Batch and Upload Routes

- Add a batch creation endpoint that validates the requested sheet count and creates a
  secure batch identifier.
- Add a per-file upload endpoint so the question paper, answer key, and answer sheets do
  not share one oversized request.
- Store uploaded files under random batch-specific paths in a private Supabase Storage bucket.
- Add a start endpoint that verifies all required files are present before queueing the batch.
- Enforce the 20 MB per-file limit and a maximum of 60 answer sheets on the server.
- Generate unique storage paths rather than using the original filename directly.
- Return clear errors for invalid extensions, missing files, incomplete uploads, and oversized files.

### Batch Status and Result Routes

- Add a batch page route that checks ownership and renders the progress UI.
- Add a JSON status endpoint returning batch status, counts, and per-sheet summaries.
- Add an individual result/PDF route protected by the batch owner or guest access token.
- Keep the current single-evaluation download behavior available for legacy history records.
- Store only a small batch identifier or access token in the Flask session, never the full result set.

### Worker

- Add a worker entry point suitable for a Render Background Worker service.
- Add a Supabase SQL function or equivalent atomic claim operation for queued batches.
- Mark batches as `queued`, `processing`, `completed`, `partial`, or `failed`.
- Mark each sheet as `pending`, `processing`, `completed`, or `failed`.
- Download source files to a worker-local temporary directory and remove them after processing.
- Retry transient OpenRouter errors with bounded exponential backoff.
- Continue processing remaining sheets after an individual sheet fails.
- Recover or requeue stale work after a worker restart.
- Update progress after every completed or failed sheet.
- Remove source objects after the configured retention period or after successful processing.

## Evaluation Service Changes

- Split shared-document reading from answer-sheet reading.
- Read the question paper and optional answer key once per batch.
- Read each student answer sheet separately to avoid mixing submissions in one vision prompt.
- Preserve the existing visibility audit so missing, partial, and unreadable answers are not inferred.
- Reuse the existing structured grading response for each answer sheet.
- Return explicit failure information instead of treating an infrastructure failure as a genuine zero score.
- Keep the one-sheet service path covered so existing single evaluations do not regress.

## Database and Storage Changes

Add a Supabase migration for a parent batch record and batch-linked evaluation records.

The batch record should include:

- Batch ID.
- Owner email or a securely stored guest access token hash.
- Question-paper and answer-key storage paths.
- Original shared-document filenames.
- Total sheet count.
- Overall status and timestamps.
- Completed and failed counts.

Batch-linked evaluation records should include:

- Batch ID.
- Answer-sheet filename and storage path.
- Per-sheet status.
- Score and maximum marks.
- Feedback, transcribed answer, and shared question/key text.
- Failure message when processing fails.
- Completion timestamp.

Existing single-evaluation rows should remain readable as legacy records. Add ownership checks
to all new batch and result queries, and document the required Supabase policies/functions.

## Frontend Changes

### Dashboard

- Change the answer-sheet input to support multiple files.
- Make drag-and-drop add files instead of replacing the current selection.
- Show the selected file list with remove controls.
- Display the 60-sheet limit and per-file 20 MB limit.
- Validate file type and size before upload while retaining server-side validation.
- Upload files individually with visible upload progress.
- Disable duplicate submissions while the batch is being created or uploaded.

### Progress and Results Page

- Add a dedicated batch page rather than relying on the single-result session page.
- Poll the status endpoint at a bounded interval.
- Show total, completed, failed, and remaining counts.
- Render each answer-sheet filename with its current status.
- Show score, maximum marks, feedback, and an individual PDF download action for completed sheets.
- Show a useful partial-completion state when some sheets fail.
- Provide retry guidance for failed sheets without hiding successful results.

### History

- Group batch-linked evaluations into one batch history entry.
- Show batch date, total count, completion state, and summary statistics.
- Allow users to reopen a batch and download completed reports.
- Continue displaying existing standalone evaluation history entries.

## PDF Reports

- Extend report data to include maximum marks and the answer-sheet filename.
- Generate reports on demand from persisted evaluation data.
- Preserve escaping of model-generated text before passing it to ReportLab.
- Use authorization checks before generating any historical or batch report.

## Configuration and Deployment

- Add configurable values for maximum batch size, per-file size, storage bucket, polling interval,
  retry count, and worker lease/recovery timing.
- Add the required storage configuration to `.env.example` without exposing service credentials.
- Document creation of the private Supabase Storage bucket and database migration.
- Document separate Render commands for the web service and background worker.
- Ensure the server-side Supabase credential has only the permissions required for application
  storage and queue operations, and is never sent to the browser.

## Testing and Verification

- Test batch count, extension, size, and missing-file validation.
- Test unique storage paths when filenames are duplicated.
- Test staged upload and start validation.
- Test that shared documents are read once per batch.
- Test per-sheet evaluation isolation and partial failures.
- Test worker claim, progress updates, retries, and stale-job recovery.
- Test batch ownership and guest-token authorization.
- Test polling responses for queued, processing, completed, partial, and failed batches.
- Test individual batch PDF generation and legacy history downloads.
- Test dashboard multi-file selection behavior where frontend testing is available.
- Run the existing smoke tests and the complete test suite before deployment.

## Implementation Order

1. Add the Supabase schema/storage migration and configuration values.
2. Refactor evaluation services around shared references and independent answer sheets.
3. Implement batch creation, staged upload, start, status, and download routes.
4. Implement the Render worker and durable Supabase claim/recovery flow.
5. Replace the dashboard upload controls with the multi-file upload workflow.
6. Add the progress/results page and batch-aware history.
7. Update PDF reports and documentation.
8. Add and run unit, route, service, and integration tests.
9. Verify deployment with a small batch, a partial failure, and a full 60-sheet batch.

## Out of Scope

- Different question papers or answer keys within one batch.
- Combined PDF generation.
- CSV or Excel export.
- Automatic student identity extraction beyond the uploaded filename.
- Parallel processing without bounded concurrency and rate-limit protection.
