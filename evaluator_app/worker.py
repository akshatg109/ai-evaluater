"""Durable sequential batch worker for a Render Background Worker service."""

import json
import logging
import os
import socket
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .application import create_app
from .services.batches import BatchStore
from .services.evaluation import evaluate_answer_sheet, read_reference_documents


LOGGER = logging.getLogger(__name__)


def worker_id():
    """Return a stable-enough identifier for lease ownership and log correlation."""
    return (
        os.getenv("RENDER_INSTANCE_ID")
        or os.getenv("HOSTNAME")
        or socket.gethostname()
        or uuid4().hex
    )[:120]


def _retryable(error):
    """Treat provider/network failures as retryable, not malformed model output."""
    if isinstance(error, (ValueError, KeyError, TypeError, FileNotFoundError, json.JSONDecodeError)):
        return False
    status = getattr(error, "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    name = error.__class__.__name__.lower()
    return any(
        marker in name
        for marker in ("timeout", "connection", "ratelimit", "internalserver", "serviceunavailable")
    ) or isinstance(error, (OSError, RuntimeError))


def _download(store, storage_key, destination, app, sleep=time.sleep):
    """Download a source object with the same bounded retry policy as AI calls."""
    max_retries = app.config["WORKER_MAX_RETRIES"]
    backoff = app.config["WORKER_RETRY_BACKOFF_SECONDS"]
    for attempt in range(1, max_retries + 2):
        try:
            content = store.download(storage_key)
            if isinstance(content, str):
                content = content.encode()
            destination.write_bytes(content)
            return
        except Exception as error:
            if attempt > max_retries or not _retryable(error):
                raise
            delay = backoff * (2 ** (attempt - 1))
            LOGGER.warning(
                "Retrying storage download after attempt %s: %s",
                attempt,
                error,
            )
            if delay:
                sleep(delay)


def _evaluate_with_retries(
    store,
    batch_id,
    sheet,
    answer_path,
    references,
    app,
    sleep=time.sleep,
    claim_token=None,
):
    max_retries = app.config["WORKER_MAX_RETRIES"]
    backoff = app.config["WORKER_RETRY_BACKOFF_SECONDS"]
    for attempt in range(1, max_retries + 2):
        store.mark_sheet_processing(batch_id, sheet["id"], attempt, claim_token)
        try:
            return evaluate_answer_sheet(
                answer_path,
                references,
                app.extensions["openrouter"],
                app.config["EVALUATION_MODEL"],
                app.config["MAX_DOCUMENT_PAGES"],
            )
        except Exception as error:
            if attempt > max_retries or not _retryable(error):
                raise
            delay = backoff * (2 ** (attempt - 1))
            LOGGER.warning(
                "Retrying sheet %s in batch %s after attempt %s: %s",
                sheet["id"],
                batch_id,
                attempt,
                error,
            )
            if delay:
                sleep(delay)


def _read_references_with_retries(question_path, answer_key_path, app, sleep=time.sleep):
    """Retry transient provider failures while loading shared batch references."""
    max_retries = app.config["WORKER_MAX_RETRIES"]
    backoff = app.config["WORKER_RETRY_BACKOFF_SECONDS"]
    for attempt in range(1, max_retries + 2):
        try:
            return read_reference_documents(
                question_path,
                app.extensions["openrouter"],
                app.config["EVALUATION_MODEL"],
                answer_key_path,
                app.config["MAX_DOCUMENT_PAGES"],
            )
        except Exception as error:
            if attempt > max_retries or not _retryable(error):
                raise
            delay = backoff * (2 ** (attempt - 1))
            LOGGER.warning(
                "Retrying shared references in batch after attempt %s: %s",
                attempt,
                error,
            )
            if delay:
                sleep(delay)


def process_claimed_batch(app, store, batch):
    """Process one claimed batch and persist every child outcome."""
    batch_id = str(batch["id"])
    claim_token = batch.get("claim_token") or batch.get("worker_id")
    if not claim_token:
        LOGGER.error("Claimed batch %s has no lease fence", batch_id)
        return "failed"

    try:
        with tempfile.TemporaryDirectory(
            prefix=f"batch-{batch_id}-",
            dir=app.config["UPLOAD_FOLDER"],
        ) as directory:
            workdir = Path(directory)
            question_path = workdir / f"question{Path(batch['question_filename']).suffix.lower()}"
            _download(store, batch["question_path"], question_path, app)

            answer_key_path = None
            if batch.get("answer_key_path"):
                answer_key_path = workdir / f"answer-key{Path(batch['answer_key_filename']).suffix.lower()}"
                _download(store, batch["answer_key_path"], answer_key_path, app)

            references = _read_references_with_retries(
                question_path,
                answer_key_path,
                app,
            )
            sheets = store.list_sheets(batch_id)
            for sheet in sheets:
                if sheet.get("status") != "pending":
                    continue
                if not store.batch_owned_by(batch_id, claim_token):
                    LOGGER.warning("Lease fence lost for batch %s", batch_id)
                    return "stale"
                answer_path = workdir / f"answer-{sheet['id']}{Path(sheet['answer_filename']).suffix.lower()}"
                try:
                    _download(store, sheet["answer_path"], answer_path, app)
                    result = _evaluate_with_retries(
                        store,
                        batch_id,
                        sheet,
                        answer_path,
                        references,
                        app,
                        claim_token=claim_token,
                    )
                    store.mark_sheet_completed(batch_id, sheet["id"], result, claim_token)
                    # Completed reports are generated from the database, so the
                    # original answer object no longer needs to be retained.
                    if store.sheet_completed_for_claim(batch_id, sheet["id"], claim_token):
                        store.remove(sheet["answer_path"])
                except Exception as error:
                    LOGGER.exception("Evaluation failed for sheet %s in batch %s", sheet["id"], batch_id)
                    store.mark_sheet_failed(
                        batch_id,
                        sheet["id"],
                        str(error) or "Evaluation failed",
                        claim_token,
                    )
                finally:
                    answer_path.unlink(missing_ok=True)
                    store.update_progress(
                        batch_id,
                        lease_seconds=app.config["WORKER_LEASE_SECONDS"],
                        claim_token=claim_token,
                    )
        final_status = store.finish_batch(batch_id, claim_token=claim_token)
        if final_status == "completed":
            store.remove(batch["question_path"])
            if batch.get("answer_key_path"):
                store.remove(batch["answer_key_path"])
        return final_status
    except Exception as error:
        LOGGER.exception("Fatal error while processing batch %s", batch_id)
        try:
            store.fail_unprocessed(
                batch_id,
                str(error) or "Batch processing failed",
                claim_token,
            )
            return store.finish_batch(batch_id, claim_token=claim_token)
        except Exception:
            LOGGER.exception("Unable to persist fatal batch failure for %s", batch_id)
            return "failed"


def process_next_batch(app):
    """Claim and process one batch; return whether work was found."""
    client = app.extensions.get("supabase")
    if client is None:
        LOGGER.error("Worker cannot start without Supabase configuration")
        return False
    store = BatchStore(client, app.config["SUPABASE_STORAGE_BUCKET"])
    batch = store.claim_batch(worker_id(), app.config["WORKER_LEASE_SECONDS"])
    if not batch:
        return False
    process_claimed_batch(app, store, batch)
    return True


def cleanup_expired_batches(app, now=None):
    """Garbage-collect abandoned drafts and old terminal batches."""
    client = app.extensions.get("supabase")
    if client is None:
        return 0
    store = BatchStore(client, app.config["SUPABASE_STORAGE_BUCKET"])
    now = now or datetime.now(timezone.utc)
    cutoff_groups = (
        (
            "draft",
            now - timedelta(hours=app.config["BATCH_DRAFT_RETENTION_HOURS"]),
        ),
        (
            "completed",
            now - timedelta(days=app.config["BATCH_TERMINAL_RETENTION_DAYS"]),
        ),
        (
            "partial",
            now - timedelta(days=app.config["BATCH_TERMINAL_RETENTION_DAYS"]),
        ),
        (
            "failed",
            now - timedelta(days=app.config["BATCH_TERMINAL_RETENTION_DAYS"]),
        ),
    )
    deleted = 0
    for status, cutoff in cutoff_groups:
        try:
            candidates = store.list_batches_before(status, cutoff.isoformat())
            for batch in candidates:
                if store.delete_batch(batch):
                    deleted += 1
        except Exception:
            LOGGER.exception("Unable to clean up expired %s batches", status)
    return deleted


def run_worker(app=None):
    """Poll Supabase continuously for Render's background-worker process."""
    app = app or create_app()
    LOGGER.info("Batch worker started as %s", worker_id())
    next_cleanup = 0.0
    while True:
        if time.monotonic() >= next_cleanup:
            try:
                cleanup_expired_batches(app)
            except Exception:
                LOGGER.exception("Batch cleanup iteration failed")
            next_cleanup = time.monotonic() + app.config["BATCH_CLEANUP_INTERVAL_SECONDS"]
        try:
            claimed = process_next_batch(app)
        except Exception:
            LOGGER.exception("Batch worker iteration failed")
            claimed = False
        if not claimed:
            time.sleep(app.config["WORKER_POLL_SECONDS"])


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()
