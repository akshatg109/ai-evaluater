"""Staged upload, progress, and report routes for batch evaluations."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from ..services.batches import BatchStore, storage_path
from ..services.reports import generate_evaluation_report


LOGGER = logging.getLogger(__name__)
batches_bp = Blueprint("batches", __name__)


class BatchStateError(Exception):
    """Raised when a draft changes state during an upload request."""


@batches_bp.after_request
def _disable_private_caching(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _store():
    client = current_app.extensions.get("supabase")
    if client is None:
        return None
    return BatchStore(client, current_app.config["SUPABASE_STORAGE_BUCKET"])


def _api_error(message, status):
    return jsonify({"error": message}), status


def _file_size(upload):
    upload.seek(0, 2)
    size = upload.tell()
    upload.seek(0)
    return size


def _validate_filename(filename, label, size=None):
    if not filename:
        raise ValueError(f"Please select a {label}.")
    if not isinstance(filename, str):
        raise ValueError(f"The {label} filename is invalid.")
    if len(filename) > 255:
        raise ValueError(f"The {label} filename is too long.")

    suffix = Path(filename).suffix.lower()
    if suffix not in current_app.config["ALLOWED_DOCUMENT_EXTENSIONS"]:
        raise ValueError("Only PDF, PNG, JPG, and JPEG files are supported.")

    if size is not None:
        if isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0:
            raise ValueError(f"The {label} size is invalid.")
        if size == 0:
            raise ValueError(f"The {label} cannot be empty.")
        if size > current_app.config["MAX_FILE_SIZE"]:
            raise ValueError("File size exceeds the 20MB limit. Please upload a smaller file.")

    safe_name = secure_filename(Path(filename).name)
    if not safe_name:
        raise ValueError(f"The {label} filename is invalid.")
    return safe_name


def _validate_upload(upload, label):
    if upload is None or not upload.filename:
        raise ValueError(f"Please select a {label}.")
    safe_name = _validate_filename(upload.filename, label)
    file_size = _file_size(upload)
    if file_size == 0:
        raise ValueError(f"The {label} cannot be empty.")
    if file_size > current_app.config["MAX_FILE_SIZE"]:
        raise ValueError("File size exceeds the 20MB limit. Please upload a smaller file.")
    return safe_name


def _content_type(upload):
    if upload.mimetype:
        return upload.mimetype
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(Path(upload.filename).suffix.lower(), "application/octet-stream")


def _as_metadata(value):
    if isinstance(value, str):
        return {"filename": value}
    return value if isinstance(value, dict) else None


def _metadata_file(value, label, required=True):
    value = _as_metadata(value)
    if value is None:
        if required:
            raise ValueError(f"Please provide a {label}.")
        return None
    filename = value.get("filename") or value.get("name")
    safe_name = _validate_filename(filename, label, value.get("size"))
    return {
        "filename": safe_name,
        "size": value.get("size"),
    }


def _batch_token(batch_id):
    supplied = (
        request.headers.get("X-Batch-Token")
        or request.form.get("access_token")
    )
    if supplied:
        return supplied
    tokens = session.get("batch_tokens", {})
    return tokens.get(str(batch_id)) if isinstance(tokens, dict) else None


def _remember_guest_token(batch_id, token):
    tokens = session.get("batch_tokens", {})
    tokens = dict(tokens) if isinstance(tokens, dict) else {}
    tokens[str(batch_id)] = token
    # Keep the signed session cookie small even if a guest creates many batches.
    session["batch_tokens"] = dict(list(tokens.items())[-10:])
    session.modified = True


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _requester_ip_hash():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    address = forwarded_for.split(",", 1)[0].strip() or request.remote_addr or "unknown"
    secret = current_app.config["SECRET_KEY"]
    return hashlib.sha256(f"{secret}:{address}".encode("utf-8")).hexdigest()


def _authorized(row, batch_id):
    user = session.get("user")
    if user and row.get("owner_email") == user:
        return True

    token = _batch_token(batch_id)
    stored_hash = row.get("guest_token_hash")
    return bool(
        token
        and stored_hash
        and hmac.compare_digest(stored_hash, _token_hash(token))
    )


def _resolve_batch(batch_id):
    store = _store()
    if store is None:
        return None, None, "Batch evaluation is unavailable because Supabase is not configured.", 503
    try:
        row = store.get_batch(batch_id)
    except Exception:
        LOGGER.exception("Unable to retrieve batch %s", batch_id)
        return None, None, "Unable to retrieve this batch.", 500
    if not row or not _authorized(row, batch_id):
        return None, None, "Batch not found.", 404
    return store, row, None, None


def _same_origin():
    """Reject browser cross-origin writes while allowing non-browser API clients."""
    origin = request.headers.get("Origin")
    return not origin or urlparse(origin).netloc == request.host


def _check_write_origin():
    if _same_origin():
        return None
    return _api_error("Cross-origin batch requests are not allowed.", 403)


def _status_payload(store, batch, batch_id):
    sheets = store.list_sheets(
        batch_id,
        "id,answer_filename,status,score,max_marks,feedback,failure_message",
    )
    completed = sum(sheet.get("status") == "completed" for sheet in sheets)
    failed = sum(sheet.get("status") == "failed" for sheet in sheets)
    processing = sum(sheet.get("status") == "processing" for sheet in sheets)
    pending = sum(sheet.get("status") in {"pending", "draft"} for sheet in sheets)

    serialized_sheets = []
    for sheet in sheets:
        serialized = {
            "id": str(sheet.get("id")),
            "filename": sheet.get("answer_filename", "answer-sheet"),
            "status": sheet.get("status", "pending"),
            "score": sheet.get("score"),
            "max_marks": sheet.get("max_marks"),
            "feedback": sheet.get("feedback"),
            "failure_message": sheet.get("failure_message"),
        }
        if sheet.get("status") == "completed":
            serialized["pdf_url"] = url_for(
                "batches.download_batch_pdf",
                batch_id=batch_id,
                sheet_id=sheet["id"],
            )
        serialized_sheets.append(serialized)

    return {
        "batch": {
            "id": str(batch["id"]),
            "status": batch.get("status", "draft"),
            "total_sheets": int(batch.get("total_sheets", len(sheets))),
            "completed_count": completed,
            "failed_count": failed,
            "processing_count": processing,
            "pending_count": pending,
            "question_filename": batch.get("question_filename"),
            "answer_key_filename": batch.get("answer_key_filename"),
            "created_at": batch.get("created_at"),
            "completed_at": batch.get("completed_at"),
        },
        "evaluations": serialized_sheets,
    }


@batches_bp.get("/batch/new")
def new_batch():
    return render_template(
        "batch_upload.html",
        user=session.get("user", "Guest"),
        max_batch_size=current_app.config["MAX_BATCH_SIZE"],
        max_file_size_mb=current_app.config["MAX_FILE_SIZE"] // (1024 * 1024),
    )


@batches_bp.post("/batches")
def create_batch():
    """Create metadata rows before any source file is uploaded."""
    origin_error = _check_write_origin()
    if origin_error:
        return origin_error
    store = _store()
    if store is None:
        return _api_error(
            "Batch evaluation is unavailable because Supabase is not configured.",
            503,
        )

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _api_error("Batch metadata must be a JSON object.", 400)
    try:
        question = _metadata_file(
            payload.get("question") or payload.get("question_file"),
            "question paper",
        )
        answer_key = _metadata_file(
            payload.get("answer_key"),
            "answer key",
            required=False,
        )
        answer_sheets = payload.get("answer_sheets") or payload.get("answers")
        if not isinstance(answer_sheets, list):
            raise ValueError("Please provide a list of answer sheets.")
        max_batch_size = current_app.config["MAX_BATCH_SIZE"]
        if not 1 <= len(answer_sheets) <= max_batch_size:
            raise ValueError(f"Please provide between 1 and {max_batch_size} answer sheets.")

        owner_email = session.get("user") or None
        rate_column = "owner_email" if owner_email else "requester_ip_hash"
        rate_value = owner_email or _requester_ip_hash()
        since = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        if store.count_recent_batches(rate_column, rate_value, since) >= current_app.config["MAX_BATCHES_PER_HOUR"]:
            return _api_error("Batch creation limit reached. Please try again later.", 429)

        batch_id = str(uuid4())
        guest_token = None
        if not owner_email:
            guest_token = secrets.token_urlsafe(32)

        question_path = storage_path(batch_id, "question", question["filename"])
        answer_key_path = (
            storage_path(batch_id, "answer-key", answer_key["filename"])
            if answer_key
            else None
        )
        sheets = []
        client_ids = set()
        for item in answer_sheets:
            item = _as_metadata(item)
            metadata = _metadata_file(item, "answer sheet")
            client_id = str(item.get("client_id") or item.get("id") or uuid4())
            if not client_id or len(client_id) > 128 or client_id in client_ids:
                raise ValueError("Answer sheet identifiers must be unique.")
            client_ids.add(client_id)
            sheet_id = str(uuid4())
            sheets.append({
                "id": sheet_id,
                "batch_id": batch_id,
                "client_file_id": client_id,
                "answer_path": storage_path(batch_id, "answer-sheets", metadata["filename"]),
                "answer_filename": metadata["filename"],
                "status": "pending",
                "uploaded": False,
                "attempts": 0,
            })

        batch = {
            "id": batch_id,
            "owner_email": owner_email,
            "guest_token_hash": _token_hash(guest_token) if guest_token else None,
            "requester_ip_hash": _requester_ip_hash(),
            "question_path": question_path,
            "question_filename": question["filename"],
            "question_uploaded": False,
            "answer_key_path": answer_key_path,
            "answer_key_filename": answer_key["filename"] if answer_key else None,
            "answer_key_uploaded": False,
            "total_sheets": len(sheets),
            "status": "draft",
            "completed_count": 0,
            "failed_count": 0,
        }
        store.create_batch(batch, sheets)
        if guest_token:
            _remember_guest_token(batch_id, guest_token)

        result = {
            "batch_id": batch_id,
            "status": "draft",
            "upload_url": url_for("batches.upload_file", batch_id=batch_id),
            "start_url": url_for("batches.start_batch", batch_id=batch_id),
            "batch_url": url_for("batches.batch_page", batch_id=batch_id),
            "question": {"kind": "question"},
            "answer_key": {"kind": "answer_key"} if answer_key else None,
            "answer_sheets": [
                {"id": sheet["id"], "filename": sheet["answer_filename"]}
                for sheet in sheets
            ],
        }
        if guest_token:
            result["access_token"] = guest_token
        return jsonify(result), 201
    except ValueError as error:
        return _api_error(str(error), 400)
    except Exception:
        LOGGER.exception("Unable to create evaluation batch")
        return _api_error("Unable to create this evaluation batch.", 500)


@batches_bp.post("/batches/<uuid:batch_id>/upload")
def upload_file(batch_id: UUID):
    origin_error = _check_write_origin()
    if origin_error:
        return origin_error
    store, batch, error, status = _resolve_batch(batch_id)
    if error:
        return _api_error(error, status)
    if batch.get("status") != "draft":
        return _api_error("This batch has already been queued and cannot accept uploads.", 409)

    kind = request.form.get("kind")
    upload = request.files.get("file")
    try:
        safe_name = _validate_upload(upload, {
            "question": "question paper",
            "answer_key": "answer key",
            "answer_sheet": "answer sheet",
        }.get(kind, "document"))
        sheet = None
        if kind == "question":
            target_path = batch["question_path"]
            expected_name = batch["question_filename"]
        elif kind == "answer_key":
            if not batch.get("answer_key_path"):
                raise ValueError("This batch does not have an answer key.")
            target_path = batch["answer_key_path"]
            expected_name = batch["answer_key_filename"]
        elif kind == "answer_sheet":
            sheet_id = request.form.get("sheet_id")
            if not sheet_id:
                raise ValueError("An answer sheet identifier is required.")
            sheet = store.get_sheet(batch_id, sheet_id)
            if not sheet:
                return _api_error("Answer sheet not found.", 404)
            target_path = sheet["answer_path"]
            expected_name = sheet["answer_filename"]
        else:
            raise ValueError("Upload kind must be question, answer_key, or answer_sheet.")

        if Path(safe_name).suffix.lower() != Path(expected_name).suffix.lower():
            raise ValueError("The uploaded file type must match the file selected for this batch.")

        # The path is generated when metadata is created; the uploaded name is only
        # used for validation so retries cannot introduce a path traversal component.
        store.upload(target_path, upload.stream, _content_type(upload))
        try:
            if kind in {"question", "answer_key"}:
                updated = store.mark_shared_uploaded(batch_id, kind)
            else:
                updated = store.mark_sheet_uploaded(batch_id, sheet["id"])
            if not updated:
                raise BatchStateError("This batch changed state before the upload could be finalized.")
        except Exception:
            store.remove(target_path)
            raise
        return jsonify({"uploaded": True, "kind": kind, "filename": safe_name}), 200
    except BatchStateError as error:
        return _api_error(str(error), 409)
    except ValueError as error:
        return _api_error(str(error), 413 if "20MB" in str(error) else 400)
    except Exception:
        LOGGER.exception("Unable to upload a file for batch %s", batch_id)
        return _api_error("Unable to upload this file. Please try again.", 500)


@batches_bp.post("/batches/<uuid:batch_id>/start")
def start_batch(batch_id: UUID):
    origin_error = _check_write_origin()
    if origin_error:
        return origin_error
    store, batch, error, status = _resolve_batch(batch_id)
    if error:
        return _api_error(error, status)
    if batch.get("status") != "draft":
        if batch.get("status") in {"queued", "processing"}:
            return jsonify({
                "batch_id": str(batch_id),
                "status": batch["status"],
                "batch_url": url_for("batches.batch_page", batch_id=batch_id),
            }), 202
        return _api_error("This batch cannot be started in its current state.", 409)

    try:
        if not batch.get("question_uploaded"):
            raise ValueError("Upload the question paper before starting the batch.")
        if batch.get("answer_key_path") and not batch.get("answer_key_uploaded"):
            raise ValueError("Upload the answer key before starting the batch.")
        sheets = store.list_sheets(batch_id)
        if len(sheets) != int(batch.get("total_sheets", 0)) or any(
            not sheet.get("uploaded") for sheet in sheets
        ):
            raise ValueError("Upload every answer sheet before starting the batch.")
        store.queue_batch(batch_id, expected_status="draft")
        current = store.get_batch(batch_id) or batch
        if current.get("status") not in {"queued", "processing"}:
            return _api_error("This batch changed state before it could be started.", 409)
        return jsonify({
            "batch_id": str(batch_id),
            "status": current.get("status", "queued"),
            "batch_url": url_for("batches.batch_page", batch_id=batch_id),
        }), 202
    except ValueError as value_error:
        return _api_error(str(value_error), 400)
    except Exception:
        LOGGER.exception("Unable to start batch %s", batch_id)
        return _api_error("Unable to start this batch.", 500)


@batches_bp.get("/batches/<uuid:batch_id>")
def batch_page(batch_id: UUID):
    _store_instance, batch, error, status = _resolve_batch(batch_id)
    if error:
        return render_template("error.html", error=error), status
    return render_template(
        "batch.html",
        batch_id=str(batch["id"]),
        poll_interval=current_app.config["BATCH_POLL_INTERVAL_SECONDS"],
    )


@batches_bp.get("/batches/<uuid:batch_id>/status")
@batches_bp.get("/api/batches/<uuid:batch_id>")
def batch_status(batch_id: UUID):
    store, batch, error, status = _resolve_batch(batch_id)
    if error:
        return _api_error(error, status)
    try:
        return jsonify(_status_payload(store, batch, batch_id))
    except Exception:
        LOGGER.exception("Unable to retrieve progress for batch %s", batch_id)
        return _api_error("Unable to retrieve batch progress.", 500)


@batches_bp.post("/batches/<uuid:batch_id>/retry")
def retry_batch(batch_id: UUID):
    origin_error = _check_write_origin()
    if origin_error:
        return origin_error
    store, batch, error, status = _resolve_batch(batch_id)
    if error:
        return _api_error(error, status)
    if batch.get("status") not in {"partial", "failed"}:
        return _api_error("Only a completed batch with failures can be retried.", 409)
    try:
        store.requeue_failed(batch_id, expected_status=batch.get("status"))
        current = store.get_batch(batch_id) or batch
        return jsonify({
            "batch_id": str(batch_id),
            "status": current.get("status", "queued"),
        }), 202
    except Exception:
        LOGGER.exception("Unable to retry batch %s", batch_id)
        return _api_error("Unable to retry failed answer sheets.", 500)


@batches_bp.get("/batches/<uuid:batch_id>/sheets/<uuid:sheet_id>/pdf")
def download_batch_pdf(batch_id: UUID, sheet_id: UUID):
    store, batch, error, status = _resolve_batch(batch_id)
    if error:
        return error, status
    try:
        sheet = store.get_sheet(batch_id, sheet_id)
    except Exception:
        LOGGER.exception("Unable to retrieve sheet %s in batch %s", sheet_id, batch_id)
        return "Unable to retrieve evaluation", 500
    if not sheet:
        return "Evaluation not found", 404
    if sheet.get("status") != "completed":
        return "This answer sheet has not completed evaluation", 409

    report = generate_evaluation_report({
        "score": sheet.get("score", 0),
        "max_marks": sheet.get("max_marks"),
        "feedback": sheet.get("feedback", ""),
        "question": sheet.get("question_text", ""),
        "answer": sheet.get("student_answer", ""),
        "answer_key": sheet.get("answer_key", ""),
        "answer_filename": sheet.get("answer_filename", ""),
        "created_at": sheet.get("completed_at") or batch.get("created_at"),
    }, include_date=True)
    name = secure_filename(Path(sheet.get("answer_filename", "answer-sheet")).stem)
    return send_file(
        report,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{name or 'answer-sheet'}-evaluation.pdf",
    )
