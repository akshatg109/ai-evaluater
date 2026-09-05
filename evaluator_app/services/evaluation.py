"""Two-call Qwen document reading and answer-evaluation services."""

import base64
import json
import logging
from pathlib import Path

from pdf2image import convert_from_path


LOGGER = logging.getLogger(__name__)


def document_to_images(file_path):
    """Return page images for a PDF, or the source image for image uploads."""
    source_path = Path(file_path)
    extension = source_path.suffix.lower()

    if extension in {".png", ".jpg", ".jpeg"}:
        return [source_path]
    if extension != ".pdf":
        raise ValueError(f"Unsupported file type: {extension}")

    image_paths = []
    for page_number, image in enumerate(convert_from_path(source_path)):
        image_path = source_path.with_name(f"{source_path.name}_{page_number}.png")
        image.save(image_path, "PNG")
        image_paths.append(image_path)
    return image_paths


def _image_content(image_path):
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    media_type = "image/jpeg" if image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{encoded_image}"},
    }


def _append_document(content, label, file_path, generated_images):
    """Add one labelled document's images to a vision prompt."""
    source_path = Path(file_path)
    image_paths = document_to_images(source_path)
    generated_images.extend(path for path in image_paths if path != source_path)

    content.append({"type": "text", "text": f"BEGIN {label}"})
    content.extend(_image_content(image_path) for image_path in image_paths)
    content.append({"type": "text", "text": f"END {label}"})


def _parse_json(content):
    """Parse a JSON response, tolerating a Markdown code fence."""
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(value)


def read_submission_documents(question_path, answer_path, client, model, answer_key_path=None):
    """Read every supplied document in one Qwen vision request."""
    content = [{
        "type": "text",
        "text": """
You are reading exam documents. The following labelled image groups are a QUESTION PAPER, a STUDENT ANSWER, and optionally an ANSWER KEY.

Read every page in every group. The student answer may be handwritten. The images between BEGIN STUDENT ANSWER and END STUDENT ANSWER are the complete uploaded submission: do NOT assume additional pages exist.

Transcribe readable handwriting faithfully; do not correct spelling, grammar, or calculations. Use [illegible] only where text truly cannot be read, and never invent, complete, or infer student-answer text from the question paper or answer key.

Audit the submitted pages against the questions in the question paper. For each question, report one of: visible (a complete readable answer is visible), partial (only part of an answer is visible, including a cut-off answer), unreadable (an answer area is present but cannot be read), or not_found (no answer is visible in the uploaded student-answer pages). This audit must be based only on the student-answer images. In particular, use not_found when a question appears in the question paper but no corresponding response appears in the uploaded pages.

Determine the TOTAL maximum marks from the QUESTION PAPER.

Return ONLY valid JSON in this exact shape:
{
  "question_text": "complete question-paper transcription",
  "student_answer": "complete student-answer transcription",
  "answer_key": "complete answer-key transcription or null when absent",
  "max_marks": 100,
  "answer_visibility": [
    {"question": "Q1", "status": "visible"},
    {"question": "Q2", "status": "not_found"}
  ]
}
""",
    }]
    generated_images = []

    try:
        _append_document(content, "QUESTION PAPER", question_path, generated_images)
        _append_document(content, "STUDENT ANSWER", answer_path, generated_images)
        if answer_key_path:
            _append_document(content, "ANSWER KEY", answer_key_path, generated_images)

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
        )
        result = _parse_json(response.choices[0].message.content)
        return {
            "question_text": str(result["question_text"]).strip(),
            "student_answer": str(result["student_answer"]).strip(),
            "answer_key": str(result["answer_key"]).strip() if result.get("answer_key") else None,
            "max_marks": int(result["max_marks"]),
            "answer_visibility": result.get("answer_visibility", []),
        }
    finally:
        for image_path in generated_images:
            image_path.unlink(missing_ok=True)


def evaluate_answer(
    question,
    student_answer,
    max_marks,
    client,
    model,
    answer_key=None,
    answer_visibility=None,
):
    """Generate a structured score and feedback response in the second call."""
    visibility_audit = json.dumps(answer_visibility or [], ensure_ascii=False)
    visibility_rules = f"""
Student-answer visibility audit (created only from the uploaded answer-sheet pages):
{visibility_audit}

This audit is binding. Evaluate ONLY content visible in the uploaded student-answer pages.
- A question marked not_found receives 0 marks. Include the exact phrase "Answer not found in uploaded pages." in its feedback.
- A question marked partial or unreadable receives marks only for the readable, visible portion; do not reconstruct or infer the rest.
- Never assume missing pages or use the answer key to supply a student answer.
"""

    if answer_key:
        prompt = f"""
You are an experienced examiner evaluating student answers STRICTLY against the provided answer key.

Question:
{question}

ANSWER KEY (Source of Truth):
{answer_key}

Student Answer:
{student_answer}

Maximum Marks:
{max_marks}

The answer key is the only source of truth. Award marks only for points that match it. Identify covered key points, missing key points, and extra incorrect information.
{visibility_rules}

Return ONLY valid JSON:
{{"score": integer between 0 and {max_marks}, "feedback": "detailed feedback"}}
"""
    else:
        prompt = f"""
You are an experienced examiner.

Question:
{question}

Student Answer:
{student_answer}

Maximum Marks:
{max_marks}

Determine the ideal key points, then evaluate accuracy, completeness, relevance, and clarity.
{visibility_rules}

Return ONLY valid JSON:
{{"score": integer between 0 and {max_marks}, "feedback": "brief feedback including covered and missing key points"}}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _parse_json(response.choices[0].message.content)
        return {"score": int(result["score"]), "feedback": str(result["feedback"])}
    except Exception:
        LOGGER.exception("Unable to generate a usable AI evaluation")
        return {
            "score": 0,
            "feedback": "AI evaluation is temporarily unavailable.",
        }


def evaluate_submission(question_path, answer_path, client, model, answer_key_path=None):
    """Run the two-call document reading and marking workflow."""
    documents = read_submission_documents(
        question_path,
        answer_path,
        client,
        model,
        answer_key_path,
    )
    evaluation = evaluate_answer(
        documents["question_text"],
        documents["student_answer"],
        documents["max_marks"],
        client,
        model,
        documents["answer_key"],
        documents["answer_visibility"],
    )
    return {**documents, **evaluation}
