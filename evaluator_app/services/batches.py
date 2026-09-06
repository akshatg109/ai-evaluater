"""Persistence and private-storage operations for evaluation batches."""

from datetime import datetime, timedelta, timezone
import io
import logging
from pathlib import Path
from uuid import uuid4


LOGGER = logging.getLogger(__name__)


def utc_now():
    """Return an ISO timestamp accepted by Postgres and easy to test."""
    return datetime.now(timezone.utc).isoformat()


def storage_path(batch_id, category, filename):
    """Create a non-guessable path while preserving the source extension."""
    suffix = Path(filename).suffix.lower()
    return f"batches/{batch_id}/{category}/{uuid4().hex}{suffix}"


def _data(response):
    return getattr(response, "data", None) or []


def _first(response):
    data = _data(response)
    if isinstance(data, dict):
        return data
    return data[0] if data else None


class BatchStore:
    """Small Supabase adapter shared by HTTP routes and the worker."""

    def __init__(self, client, bucket):
        self.client = client
        self.bucket = bucket

    def create_batch(self, batch, sheets):
        """Insert a draft batch and all of its pending answer-sheet rows."""
        response = self.client.table("evaluation_batches").insert(batch).execute()
        created = _first(response) or batch
        if sheets:
            try:
                self.client.table("batch_evaluations").insert(sheets).execute()
            except Exception:
                LOGGER.exception("Unable to create answer-sheet rows for batch %s", batch["id"])
                self.client.table("evaluation_batches").delete().eq(
                    "id", str(batch["id"])
                ).execute()
                raise
        return created

    def get_batch(self, batch_id):
        response = (
            self.client.table("evaluation_batches")
            .select("*")
            .eq("id", str(batch_id))
            .execute()
        )
        return _first(response)

    def list_sheets(self, batch_id, columns="*"):
        response = (
            self.client.table("batch_evaluations")
            .select(columns)
            .eq("batch_id", str(batch_id))
            .order("created_at", desc=False)
            .execute()
        )
        data = _data(response)
        return data if isinstance(data, list) else []

    def get_sheet(self, batch_id, sheet_id):
        response = (
            self.client.table("batch_evaluations")
            .select("*")
            .eq("batch_id", str(batch_id))
            .eq("id", str(sheet_id))
            .execute()
        )
        return _first(response)

    def update_batch(self, batch_id, fields, claim_token=None, expected_status=None):
        values = {**fields, "updated_at": utc_now()}
        query = self.client.table("evaluation_batches").update(values).eq(
            "id", str(batch_id)
        )
        if claim_token is not None:
            query = query.eq("claim_token", claim_token)
        if expected_status is not None:
            query = query.eq("status", expected_status)
        return query.execute()

    def batch_owned_by(self, batch_id, claim_token):
        batch = self.get_batch(batch_id)
        return bool(
            batch
            and batch.get("status") == "processing"
            and batch.get("claim_token") == claim_token
        )

    def batch_claim_matches(self, batch_id, claim_token):
        batch = self.get_batch(batch_id)
        return bool(batch and batch.get("claim_token") == claim_token)

    def mark_shared_uploaded(self, batch_id, kind):
        column = {
            "question": "question_uploaded",
            "answer_key": "answer_key_uploaded",
        }[kind]
        response = (
            self.client.table("evaluation_batches")
            .update({column: True, "updated_at": utc_now()})
            .eq("id", str(batch_id))
            .eq("status", "draft")
            .select("id")
            .execute()
        )
        return _first(response)

    def mark_sheet_uploaded(self, batch_id, sheet_id):
        response = (
            self.client.table("batch_evaluations")
            .update({"uploaded": True, "updated_at": utc_now()})
            .eq("batch_id", str(batch_id))
            .eq("id", str(sheet_id))
            .eq("status", "pending")
            .select("id")
            .execute()
        )
        return _first(response)

    def queue_batch(self, batch_id, expected_status="draft"):
        values = {
            "status": "queued",
            "last_error": None,
            "completed_at": None,
            "worker_id": None,
            "claim_token": None,
            "lease_expires_at": None,
        }
        query = self.client.table("evaluation_batches").update(values).eq(
            "id", str(batch_id)
        )
        if expected_status:
            query = query.eq("status", expected_status)
        return query.execute()

    def claim_batch(self, worker_id, lease_seconds):
        """Atomically claim the oldest queued or expired batch via Postgres RPC."""
        response = self.client.rpc(
            "claim_evaluation_batch",
            {
                "p_worker_id": worker_id,
                "p_lease_seconds": int(lease_seconds),
            },
        ).execute()
        data = _data(response)
        if isinstance(data, dict):
            return data if data.get("id") else None
        return data[0] if data else None

    def mark_sheet_processing(self, batch_id, sheet_id, attempt, claim_token):
        return (
            self.client.table("batch_evaluations")
            .update({
                "status": "processing",
                "attempts": int(attempt),
                "started_at": utc_now(),
                "claim_token": claim_token,
                "failure_message": None,
                "updated_at": utc_now(),
            })
            .eq("batch_id", str(batch_id))
            .eq("id", str(sheet_id))
            .eq("claim_token", claim_token)
            .execute()
        )

    def mark_sheet_completed(self, batch_id, sheet_id, result, claim_token):
        return (
            self.client.table("batch_evaluations")
            .update({
                "status": "completed",
                "score": int(result["score"]),
                "max_marks": int(result["max_marks"]),
                "feedback": result["feedback"],
                "question_text": result["question_text"],
                "student_answer": result["student_answer"],
                "answer_key": result.get("answer_key") or "",
                "answer_visibility": result.get("answer_visibility", []),
                "failure_message": None,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            })
            .eq("batch_id", str(batch_id))
            .eq("id", str(sheet_id))
            .eq("claim_token", claim_token)
            .execute()
        )

    def mark_sheet_failed(self, batch_id, sheet_id, message, claim_token):
        return (
            self.client.table("batch_evaluations")
            .update({
                "status": "failed",
                "failure_message": str(message)[:2000],
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            })
            .eq("batch_id", str(batch_id))
            .eq("id", str(sheet_id))
            .eq("claim_token", claim_token)
            .execute()
        )

    def update_progress(self, batch_id, lease_seconds=None, claim_token=None):
        """Persist counts after each sheet so clients survive worker restarts."""
        sheets = self.list_sheets(batch_id, "status")
        completed = sum(row.get("status") == "completed" for row in sheets)
        failed = sum(row.get("status") == "failed" for row in sheets)
        fields = {
            "completed_count": completed,
            "failed_count": failed,
            "heartbeat_at": utc_now(),
        }
        if lease_seconds is not None:
            fields["lease_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=int(lease_seconds))
            ).isoformat()
        self.update_batch(batch_id, fields, claim_token=claim_token)
        return completed, failed, len(sheets)

    def finish_batch(self, batch_id, claim_token=None):
        """Derive the terminal status from persisted child rows."""
        if claim_token is not None and not self.batch_owned_by(batch_id, claim_token):
            return "stale"
        completed, failed, total = self.update_progress(
            batch_id,
            claim_token=claim_token,
        )
        if total and completed + failed == total:
            if failed and completed:
                status = "partial"
            elif failed:
                status = "failed"
            else:
                status = "completed"
            self.update_batch(
                batch_id,
                {
                    "status": status,
                    "completed_count": completed,
                    "failed_count": failed,
                    "completed_at": utc_now(),
                    "worker_id": None,
                    "lease_expires_at": None,
                },
                claim_token=claim_token,
            )
            if claim_token is not None and not self.batch_claim_matches(batch_id, claim_token):
                return "stale"
        return status if total and completed + failed == total else "processing"

    def fail_unprocessed(self, batch_id, message, claim_token):
        """Turn work left behind by a fatal batch-level error into visible failures."""
        for sheet in self.list_sheets(batch_id):
            if sheet.get("status") in {"pending", "processing"}:
                self.mark_sheet_failed(batch_id, sheet["id"], message, claim_token)
        self.update_batch(
            batch_id,
            {"last_error": str(message)[:2000]},
            claim_token=claim_token,
        )

    def requeue_failed(self, batch_id, expected_status=None):
        """Retry only failed sheets while retaining completed results."""
        response = (
            self.client.table("batch_evaluations")
            .update({
                "status": "pending",
                "score": None,
                "max_marks": None,
                "feedback": None,
                "failure_message": None,
                "started_at": None,
                "completed_at": None,
                "claim_token": None,
                "updated_at": utc_now(),
            })
            .eq("batch_id", str(batch_id))
            .eq("status", "failed")
            .execute()
        )
        self.queue_batch(batch_id, expected_status=expected_status)
        return response

    def sheet_completed_for_claim(self, batch_id, sheet_id, claim_token):
        sheet = self.get_sheet(batch_id, sheet_id)
        return bool(
            sheet
            and sheet.get("status") == "completed"
            and sheet.get("claim_token") == claim_token
        )

    def upload(self, path, file_object, content_type):
        """Upload one source document to the configured private bucket."""
        if hasattr(file_object, "seek"):
            file_object.seek(0)
        if hasattr(file_object, "read") and not isinstance(
            file_object, (io.BufferedReader, io.FileIO)
        ):
            file_object = io.BufferedReader(file_object)
        return self.client.storage.from_(self.bucket).upload(
            path,
            file_object,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "upsert": "true",
            },
        )

    def download(self, path):
        return self.client.storage.from_(self.bucket).download(path)

    def remove(self, path):
        try:
            self.client.storage.from_(self.bucket).remove([path])
            return True
        except Exception:
            LOGGER.exception("Unable to remove temporary batch object %s", path)
            return False

    def list_user_batches(self, email):
        response = (
            self.client.table("evaluation_batches")
            .select("*")
            .eq("owner_email", email)
            .order("created_at", desc=True)
            .execute()
        )
        data = _data(response)
        return data if isinstance(data, list) else []

    def count_recent_batches(self, column, value, since):
        response = (
            self.client.table("evaluation_batches")
            .select("id")
            .eq(column, value)
            .gte("created_at", since)
            .execute()
        )
        data = _data(response)
        return len(data) if isinstance(data, list) else 0

    def list_batches_before(self, status, before):
        response = (
            self.client.table("evaluation_batches")
            .select("*")
            .eq("status", status)
            .lt("created_at", before)
            .execute()
        )
        data = _data(response)
        return data if isinstance(data, list) else []

    def delete_batch(self, batch):
        """Remove a batch only after its private source objects are removed."""
        for sheet in self.list_sheets(batch["id"]):
            if sheet.get("answer_path") and not self.remove(sheet["answer_path"]):
                return False
        for path in (batch.get("question_path"), batch.get("answer_key_path")):
            if path and not self.remove(path):
                return False
        self.client.table("batch_evaluations").delete().eq(
            "batch_id", str(batch["id"])
        ).execute()
        self.client.table("evaluation_batches").delete().eq(
            "id", str(batch["id"])
        ).execute()
        return True
