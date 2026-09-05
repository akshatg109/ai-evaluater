"""Submission evaluation and PDF-download routes."""

import logging
import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from .main import format_datetime
from ..services.evaluation import evaluate_submission
from ..services.reports import generate_evaluation_report


LOGGER = logging.getLogger(__name__)
evaluations_bp = Blueprint("evaluations", __name__)


def _render_error(message, status=400):
    return render_template("error.html", error=message), status


def _file_size(upload):
    upload.seek(0, 2)
    size = upload.tell()
    upload.seek(0)
    return size


def _validate_upload(upload, label):
    if upload is None or not upload.filename:
        raise ValueError(f"Please select a {label}.")
    if Path(upload.filename).suffix.lower() not in current_app.config["ALLOWED_DOCUMENT_EXTENSIONS"]:
        raise ValueError("Only PDF, PNG, JPG, and JPEG files are supported.")
    if _file_size(upload) > current_app.config["MAX_FILE_SIZE"]:
        raise ValueError("File size exceeds the 20MB limit. Please upload a smaller file.")


def _save_upload(upload, destination):
    filename = secure_filename(upload.filename)
    if not filename:
        raise ValueError("The uploaded filename is invalid.")
    path = destination / filename
    upload.save(path)
    return path


def _save_evaluation(result):
    """Store one result. Database trouble should not hide a completed evaluation."""
    supabase = current_app.extensions["supabase"]
    if supabase is None:
        return
    try:
        supabase.table("evaluations").insert({
            "user_email": session.get("user", "guest"),
            "score": int(result["score"]),
            "feedback": result["feedback"],
            "answer_key": result["answer_key"] or "",
            "question_text": result["question_text"],
            "student_answer": result["student_answer"],
            "report_path": "",
        }).execute()
    except Exception:
        LOGGER.exception("Unable to save evaluation to Supabase")


@evaluations_bp.post("/evaluate")
def evaluate():
    question_file = request.files.get("question_file")
    answer_file = request.files.get("answer_file")
    answer_key_file = request.files.get("answer_key")

    try:
        _validate_upload(question_file, "question paper")
        _validate_upload(answer_file, "answer sheet")
        if answer_key_file and answer_key_file.filename:
            _validate_upload(answer_key_file, "answer key")
    except ValueError as error:
        message = str(error)
        return _render_error(message, 413 if "20MB" in message else 400)

    upload_directory = Path(tempfile.mkdtemp(
        dir=current_app.config["UPLOAD_FOLDER"],
        prefix="evaluation-",
    ))
    try:
        question_path = _save_upload(question_file, upload_directory)
        answer_path = _save_upload(answer_file, upload_directory)
        answer_key_path = (
            _save_upload(answer_key_file, upload_directory)
            if answer_key_file and answer_key_file.filename
            else None
        )
        result = evaluate_submission(
            question_path,
            answer_path,
            current_app.extensions["openrouter"],
            current_app.config["EVALUATION_MODEL"],
            answer_key_path,
        )
        _save_evaluation(result)

        session["evaluation_data"] = {
            "score": int(result["score"]),
            "feedback": result["feedback"],
            "max_marks": result["max_marks"],
            "question": result["question_text"],
            "answer": result["student_answer"],
            "answer_key": result["answer_key"],
            "question_filename": question_file.filename,
            "answer_filename": answer_file.filename,
            "answer_key_filename": answer_key_file.filename if answer_key_file else None,
        }
        return render_template(
            "result.html",
            score=result["score"],
            feedback=result["feedback"],
            max_marks=result["max_marks"],
        )
    except Exception:
        LOGGER.exception("Evaluation failed")
        return _render_error("We could not evaluate these documents. Please try again.", 500)
    finally:
        shutil.rmtree(upload_directory, ignore_errors=True)


@evaluations_bp.get("/download-history/<int:eval_id>")
def download_history(eval_id):
    if "user" not in session:
        return "Unauthorized", 401

    supabase = current_app.extensions["supabase"]
    if supabase is None:
        return "History is unavailable because Supabase is not configured", 503
    try:
        result = (
            supabase.table("evaluations")
            .select("*")
            .eq("id", eval_id)
            .eq("user_email", session["user"])
            .execute()
        )
        if not result.data:
            return "Evaluation not found", 404
        evaluation = result.data[0]
    except Exception:
        LOGGER.exception("Unable to retrieve evaluation %s", eval_id)
        return "Error retrieving evaluation", 500

    report = generate_evaluation_report({
        "score": evaluation.get("score", 0),
        "feedback": evaluation.get("feedback", ""),
        "question": evaluation.get("question_text", ""),
        "answer": evaluation.get("student_answer", ""),
        "answer_key": evaluation.get("answer_key", ""),
        "created_at": format_datetime(evaluation.get("created_at")),
    }, include_date=True)
    return send_file(
        report,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"evaluation-{eval_id}.pdf",
    )


@evaluations_bp.get("/download-result")
def download_result():
    if "evaluation_data" not in session:
        return "No evaluation data found", 404
    report = generate_evaluation_report(session["evaluation_data"])
    return send_file(
        report,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="evaluation-result.pdf",
    )
