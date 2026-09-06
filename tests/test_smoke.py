"""Fast checks for the refactored Flask application."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from evaluator_app.application import create_app
from evaluator_app.config import Config
from evaluator_app.services.evaluation import document_to_images, evaluate_submission
from evaluator_app.services.reports import generate_evaluation_report


class FakeCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.responses)))]
        )


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class ApplicationSmokeTests(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SUPABASE_URL": None,
            "SUPABASE_KEY": None,
            "OPENROUTER_API_KEY": "test-key",
            "UPLOAD_FOLDER": self.upload_directory.name,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.upload_directory.cleanup()

    def test_public_pages_are_available(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/batch/new").status_code, 200)
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/signup").status_code, 200)

    def test_history_requires_login(self):
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_invalid_upload_is_handled_before_ai_evaluation(self):
        response = self.client.post("/evaluate", data={})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Please select a question paper.", response.data)

    def test_request_limit_allows_question_answer_and_answer_key(self):
        self.assertGreaterEqual(
            Config.MAX_CONTENT_LENGTH,
            3 * Config.MAX_FILE_SIZE,
        )

    def test_png_jpg_and_jpeg_are_accepted_as_images(self):
        for extension in (".png", ".jpg", ".jpeg"):
            image_path = Path(self.upload_directory.name) / f"answer{extension}"
            image_path.write_bytes(b"image")
            self.assertEqual(document_to_images(image_path), [image_path])

    def test_submission_uses_two_qwen_calls_and_preserves_handwritten_prompt(self):
        question_path = Path(self.upload_directory.name) / "question.png"
        answer_path = Path(self.upload_directory.name) / "answer.jpg"
        question_path.write_bytes(b"question-image")
        answer_path.write_bytes(b"answer-image")
        reader_response = json.dumps({
            "question_text": "What is 2 + 2?",
            "student_answer": "4",
            "answer_key": None,
            "max_marks": 5,
            "answer_visibility": [{"question": "Q1", "status": "visible"}],
        })
        grader_response = json.dumps({"score": 5, "feedback": "Correct answer."})
        model = FakeClient([reader_response, grader_response])

        result = evaluate_submission(question_path, answer_path, model, "test-model")

        self.assertEqual(result["score"], 5)
        self.assertEqual(len(model.completions.calls), 2)
        reader_prompt = model.completions.calls[0]["messages"][0]["content"][0]["text"]
        self.assertIn("handwritten", reader_prompt.lower())
        self.assertIn("do not assume additional pages exist", reader_prompt.lower())
        grader_prompt = model.completions.calls[1]["messages"][0]["content"]
        self.assertIn("question marked not_found receives 0 marks", grader_prompt.lower())
        self.assertIn('"Q1"', grader_prompt)

    def test_pdf_report_generation(self):
        report = generate_evaluation_report({
            "score": 8,
            "feedback": "Clear and accurate.",
            "question": "Explain & compare.",
            "answer": "A < B.",
            "answer_key": "Comparison points.",
        })
        self.assertTrue(report.read().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
