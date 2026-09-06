"""Local tests for staged batches and the durable worker workflow."""

import io
import json
import tempfile
import unittest
from copy import deepcopy
from types import SimpleNamespace

from evaluator_app.application import create_app
from evaluator_app.worker import process_next_batch


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, database, table_name):
        self.database = database
        self.table_name = table_name
        self.operation = "select"
        self.values = None
        self.filters = []
        self.ordering = None

    def select(self, _columns):
        return self

    def insert(self, values):
        self.operation = "insert"
        self.values = values
        return self

    def update(self, values):
        self.operation = "update"
        self.values = values
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def order(self, column, desc=False):
        self.ordering = (column, desc)
        return self

    def _matches(self, row):
        for operation, column, value in self.filters:
            if operation == "eq" and str(row.get(column)) != str(value):
                return False
            if operation == "gte" and str(row.get(column) or "") < str(value):
                return False
        return True

    def execute(self):
        rows = self.database.setdefault(self.table_name, [])
        if self.operation == "insert":
            values = self.values if isinstance(self.values, list) else [self.values]
            inserted = [deepcopy(value) for value in values]
            rows.extend(inserted)
            return FakeResponse(inserted)
        matched = [row for row in rows if self._matches(row)]
        if self.operation == "update":
            for row in matched:
                row.update(deepcopy(self.values))
            return FakeResponse(deepcopy(matched))
        result = [deepcopy(row) for row in matched]
        if self.ordering:
            column, desc = self.ordering
            result.sort(key=lambda row: row.get(column) or "", reverse=desc)
        return FakeResponse(result)


class FakeBucket:
    def __init__(self, objects):
        self.objects = objects

    def upload(self, path, file_object, file_options=None):
        del file_options
        self.objects[path] = file_object.read()
        return {"path": path}

    def download(self, path):
        return self.objects[path]

    def remove(self, paths):
        for path in paths:
            self.objects.pop(path, None)
        return paths


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def from_(self, _bucket):
        return FakeBucket(self.objects)


class FakeRpc:
    def __init__(self, database, arguments):
        self.database = database
        self.arguments = arguments

    def execute(self):
        batches = self.database["evaluation_batches"]
        candidate = next(
            (
                batch
                for batch in batches
                if batch.get("status") == "queued"
            ),
            None,
        )
        if candidate is None:
            return FakeResponse([])
        claim_token = "test-claim-token"
        candidate.update({
            "status": "processing",
            "worker_id": self.arguments["p_worker_id"],
            "claim_token": claim_token,
        })
        for sheet in self.database["batch_evaluations"]:
            if sheet.get("batch_id") == candidate.get("id") and sheet.get("status") in {
                "pending",
                "processing",
            }:
                sheet.update({"status": "pending", "claim_token": claim_token})
        return FakeResponse([deepcopy(candidate)])


class FakeSupabase:
    def __init__(self):
        self.database = {
            "evaluation_batches": [],
            "batch_evaluations": [],
            "evaluations": [],
        }
        self.storage = FakeStorage()

    def table(self, table_name):
        return FakeQuery(self.database, table_name)

    def rpc(self, _name, arguments):
        return FakeRpc(self.database, arguments)


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


class BatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SUPABASE_URL": None,
            "SUPABASE_KEY": None,
            "SUPABASE_STORAGE_BUCKET": "test-batches",
            "OPENROUTER_API_KEY": "test-key",
            "UPLOAD_FOLDER": self.upload_directory.name,
            "WORKER_RETRY_BACKOFF_SECONDS": 0,
        })
        self.supabase = FakeSupabase()
        self.app.extensions["supabase"] = self.supabase
        self.client = self.app.test_client()

    def tearDown(self):
        self.upload_directory.cleanup()

    def _create_batch(self, count=2):
        response = self.client.post("/batches", json={
            "question": {"filename": "exam.png", "size": 10},
            "answer_key": None,
            "answer_sheets": [
                {"filename": f"student-{index}.png", "size": 10, "client_id": f"file-{index}"}
                for index in range(count)
            ],
        })
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _upload(self, batch_id, kind, filename, content=b"document", sheet_id=None):
        form = {"kind": kind, "file": (io.BytesIO(content), filename)}
        if sheet_id:
            form["sheet_id"] = sheet_id
        response = self.client.post(
            f"/batches/{batch_id}/upload",
            data=form,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_staged_batch_requires_all_files_and_keeps_guest_access_token(self):
        cross_origin = self.client.post(
            "/batches",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(cross_origin.status_code, 403)

        batch = self._create_batch()
        batch_id = batch["batch_id"]
        self._upload(batch_id, "question", "exam.png", b"question")
        self._upload(
            batch_id,
            "answer_sheet",
            "student-0.png",
            b"answer zero",
            batch["answer_sheets"][0]["id"],
        )

        response = self.client.post(f"/batches/{batch_id}/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn("every answer sheet", response.get_json()["error"])

        self._upload(
            batch_id,
            "answer_sheet",
            "student-1.png",
            b"answer one",
            batch["answer_sheets"][1]["id"],
        )
        response = self.client.post(f"/batches/{batch_id}/start")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.supabase.database["evaluation_batches"][0]["status"], "queued")
        page = self.client.get(f"/batches/{batch_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Your answer sheets", page.data)

        with self.client.session_transaction() as session:
            self.assertEqual(session["batch_tokens"][batch_id], batch["access_token"])
            session.clear()
        unauthorized = self.client.get(f"/batches/{batch_id}/status")
        self.assertEqual(unauthorized.status_code, 404)
        authorized = self.client.get(
            f"/batches/{batch_id}/status",
            headers={"X-Batch-Token": batch["access_token"]},
        )
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.headers["Cache-Control"], "no-store")

    def test_empty_metadata_and_upload_files_are_rejected(self):
        response = self.client.post("/batches", json={
            "question": {"filename": "exam.png", "size": 0},
            "answer_sheets": [{"filename": "student.png", "size": 10}],
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be empty", response.get_json()["error"])

        batch = self._create_batch(count=1)
        response = self.client.post(
            f"/batches/{batch['batch_id']}/upload",
            data={"kind": "question", "file": (io.BytesIO(), "exam.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be empty", response.get_json()["error"])

    def test_worker_reads_shared_reference_once_and_persists_each_result(self):
        batch = self._create_batch()
        batch_id = batch["batch_id"]
        self._upload(batch_id, "question", "exam.png", b"question")
        for index, sheet in enumerate(batch["answer_sheets"]):
            self._upload(
                batch_id,
                "answer_sheet",
                f"student-{index}.png",
                f"answer {index}".encode(),
                sheet["id"],
            )
        self.assertEqual(self.client.post(f"/batches/{batch_id}/start").status_code, 202)

        responses = [
            json.dumps({
                "question_text": "What is one plus one?",
                "answer_key": None,
                "max_marks": 5,
            }),
            json.dumps({
                "student_answer": "2",
                "answer_visibility": [{"question": "Q1", "status": "visible"}],
            }),
            json.dumps({"score": 5, "feedback": "Correct."}),
            json.dumps({
                "student_answer": "three",
                "answer_visibility": [{"question": "Q1", "status": "visible"}],
            }),
            json.dumps({"score": 0, "feedback": "Incorrect."}),
        ]
        model = FakeClient(responses)
        self.app.extensions["openrouter"] = model

        self.assertTrue(process_next_batch(self.app))
        stored_batch = self.supabase.database["evaluation_batches"][0]
        stored_sheets = self.supabase.database["batch_evaluations"]
        self.assertEqual(stored_batch["status"], "completed")
        self.assertEqual(stored_batch["completed_count"], 2)
        self.assertTrue(all(sheet["status"] == "completed" for sheet in stored_sheets))
        self.assertEqual(len(model.completions.calls), 5)
        reference_prompt = model.completions.calls[0]["messages"][0]["content"][0]["text"]
        answer_prompt = model.completions.calls[1]["messages"][0]["content"][0]["text"]
        self.assertIn("shared reference documents", reference_prompt)
        self.assertIn("Shared QUESTION PAPER transcription", answer_prompt)

        status = self.client.get(
            f"/batches/{batch_id}/status",
            headers={"X-Batch-Token": batch["access_token"]},
        ).get_json()
        self.assertEqual(status["batch"]["completed_count"], 2)
        self.assertEqual(status["evaluations"][0]["score"], 5)

        report = self.client.get(
            f"/batches/{batch_id}/sheets/{stored_sheets[0]['id']}/pdf",
            headers={"X-Batch-Token": batch["access_token"]},
        )
        self.assertEqual(report.status_code, 200)
        self.assertTrue(report.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
