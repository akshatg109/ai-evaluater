from flask import Flask, render_template, request
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv

import pytesseract
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
        model="qwen/qwen3-next-80b-a3b-instruct:free",
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
        question_file.filename
    )

    answer_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        answer_file.filename
    )

    question_file.save(question_path)
    answer_file.save(answer_path)

    question_text = pytesseract.image_to_string(
        Image.open(question_path)
    )

    max_marks = extract_max_marks(question_text)

    student_answer = pytesseract.image_to_string(
        Image.open(answer_path)
    ).strip()

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