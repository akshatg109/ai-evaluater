from flask import Flask, render_template, request
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv

from werkzeug.utils import secure_filename
import fitz
from pdf2image import convert_from_path
import json
import os

app = Flask(__name__)

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)



def extract_text(file_path):
    # If PDF, try to extract embedded text first. If none, convert pages
    # to images and save them for external OCR (e.g., via OpenRouter).
    if file_path.lower().endswith(".pdf"):
        text = ""

        doc = fitz.open(file_path)

        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text += page_text + "\n"

        doc.close()

        if text.strip():
            return text.strip()

        # No embedded text found — convert PDF pages to images for OCR later
        pages = convert_from_path(file_path)
        image_paths = []
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        out_dir = os.path.join(app.config["UPLOAD_FOLDER"], f"{base_name}_pages")
        os.makedirs(out_dir, exist_ok=True)

        for i, page in enumerate(pages, start=1):
            img_path = os.path.join(out_dir, f"page_{i}.png")
            page.save(img_path, "PNG")
            image_paths.append(img_path)

        return image_paths

    # For non-PDF files, assume the file itself is an image and return its path
    return file_path


def extract_max_marks(question_text):

    prompt = f"""
You are an expert at reading examination papers.

Extract the TOTAL maximum marks from the following question paper text.

Question Paper:
{question_text}

Return ONLY the number.

Examples:
100
50
25
"""

    response = client.chat.completions.create(
        model="qwen/qwen3-vl-32b-instruct",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return int(response.choices[0].message.content.strip())


def evaluate_answer(question, student_answer, max_marks):

    prompt = f"""
You are an experienced examiner.

Question:
{question}

Student Answer:
{student_answer}

Maximum Marks:
{max_marks}

First determine the expected key points for an ideal answer.

Then evaluate the student's answer based on:

- Accuracy
- Completeness
- Relevance
- Clarity

Return ONLY valid JSON in this format:

{{
    "score": integer between 0 and {max_marks},
    "feedback": "brief feedback"
}}
"""

    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-next-80b-a3b-instruct:free",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        content = response.choices[0].message.content.strip()

        print("QWEN RESPONSE:", content)

        return json.loads(content)

    except Exception as e:
        print("Qwen Error:", e)

        return {
            "score": 0,
            "feedback": "AI evaluation is temporarily unavailable. Please try again later."
        }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/evaluate", methods=["POST"])
def evaluate():

    question_file = request.files["question_file"]
    answer_file = request.files["answer_file"]

    question_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        secure_filename(question_file.filename)
    )

    answer_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        secure_filename(answer_file.filename)
    )

    question_file.save(question_path)
    answer_file.save(answer_path)

    question_text = extract_text(question_path)

    max_marks = extract_max_marks(question_text)

    student_answer = extract_text(answer_path)

    print("QUESTION OCR:", question_text)
    print("ANSWER OCR:", student_answer)

    result = evaluate_answer(
        question_text,
        student_answer,
        max_marks
    )

    score = int(result["score"])
    feedback = result["feedback"]

    return render_template(
        "result.html",
        score=score,
        feedback=feedback
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)