from flask import Flask, render_template, request, send_file, session
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import pytesseract

from werkzeug.utils import secure_filename
import fitz
from pdf2image import convert_from_path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from io import BytesIO
import json
import os

from supabase import create_client
import os

from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("URL =", repr(SUPABASE_URL))
print("KEY =", repr(SUPABASE_KEY))

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

try:
    result = supabase.table("evaluations").select("*").limit(1).execute()
    print("✅ Supabase Connected Successfully")
except Exception as e:
    print("❌ Supabase Error:", e)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")



print("OPENROUTER:", os.getenv("OPENROUTER_API_KEY"))
print("SUPABASE_URL:", os.getenv("SUPABASE_URL"))
print("SUPABASE_KEY:", os.getenv("SUPABASE_KEY"))

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# Configuration
UPLOAD_FOLDER = "uploads"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)



def extract_text(file_path):

    text = ""

    # PDF
    if file_path.lower().endswith(".pdf"):

        doc = fitz.open(file_path)

        for page in doc:
            text += page.get_text() + "\n"

        doc.close()

        if text.strip():
            return text.strip()

        pages = convert_from_path(file_path)

        for page in pages:
            text += pytesseract.image_to_string(page) + "\n"

        return text.strip()

    # Image files
    return pytesseract.image_to_string(
        Image.open(file_path)
    ).strip()


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


def evaluate_answer(question, student_answer, max_marks, answer_key=None):

    if answer_key:
        # When answer key is provided, it takes complete priority
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

IMPORTANT: The answer key is the ONLY source of truth for what is considered correct. Judge the student's answer ONLY based on how well it matches the answer key.

Instructions:
1. Identify all key points from the answer key
2. Check which key points are covered in the student's answer
3. Award marks ONLY for points that match the answer key
4. Deduct marks for missing key points from the answer key
5. Do NOT award marks for information not in the answer key, even if it's technically correct

Evaluation criteria:
- Coverage of key points from answer key
- Accuracy in relation to answer key content
- Completeness based on answer key standards

Return ONLY valid JSON in this format:

{{
    "score": integer between 0 and {max_marks},
    "feedback": "Detailed feedback showing: 1) Key points covered from answer key, 2) Key points missing from answer key, 3) Any extra incorrect information"
}}
"""
    else:
        # Without answer key, use standard AI evaluation
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
    "feedback": "brief feedback including key points covered and missing points"
}}
"""

    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-vl-32b-instruct",
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
    answer_key_file = request.files.get("answer_key")

    # Validate file sizes
    question_file.seek(0, 2)  # Seek to end
    question_size = question_file.tell()
    question_file.seek(0)  # Seek back to beginning
    
    answer_file.seek(0, 2)  # Seek to end
    answer_size = answer_file.tell()
    answer_file.seek(0)  # Seek back to beginning
    
    if question_size > MAX_FILE_SIZE or answer_size > MAX_FILE_SIZE:
        return render_template(
            "error.html",
            error="File size exceeds 20MB limit. Please upload smaller files."
        ), 413

    if answer_key_file:
        answer_key_file.seek(0, 2)
        key_size = answer_key_file.tell()
        answer_key_file.seek(0)
        
        if key_size > MAX_FILE_SIZE:
            return render_template(
                "error.html",
                error="File size exceeds 20MB limit. Please upload smaller files."
            ), 413

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

    # Extract answer key if provided
    answer_key_text = None
    answer_key_path = None
    if answer_key_file:
        answer_key_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            secure_filename(answer_key_file.filename)
        )
        answer_key_file.save(answer_key_path)
        answer_key_text = extract_text(answer_key_path)

    question_text = extract_text(question_path)

    max_marks = extract_max_marks(question_text)

    student_answer = extract_text(answer_path)

    print("QUESTION OCR:", question_text)
    print("ANSWER OCR:", student_answer)
    if answer_key_text:
        print("ANSWER KEY OCR:", answer_key_text)
    
    print("\n====================")
    print("QUESTION TEXT:")
    print(question_text)

    print("\nANSWER TEXT:")
    print(student_answer)
    if answer_key_text:
        print("\nANSWER KEY TEXT:")
        print(answer_key_text)
    print("====================\n")

    result = evaluate_answer(
        question_text,
        student_answer,
        max_marks,
        answer_key_text
    )

    score = int(result["score"])
    feedback = result["feedback"]
    
    supabase.table("evaluations").insert({
    "user_email": "guest",
    "score": score,
    "feedback": feedback,
    "answer_key": result.get("answer_key", ""),
    "question_text": question_text,
    "student_answer": student_answer,
    "report_path": ""
}).execute()

    # Store in session for PDF download
    session['evaluation_data'] = {
        'score': score,
        'feedback': feedback,
        'max_marks': max_marks,
        'question': question_text,
        'answer': student_answer,
        'answer_key': answer_key_text,
        'question_filename': question_file.filename,
        'answer_filename': answer_file.filename,
        'answer_key_filename': answer_key_file.filename if answer_key_file else None
    }

    # Clean up uploaded files
    try:
        os.remove(question_path)
        os.remove(answer_path)
        if answer_key_path:
            os.remove(answer_key_path)
    except:
        pass

    return render_template(
        "result.html",
        score=score,
        feedback=feedback,
        max_marks=max_marks
    )


@app.route("/download-result")
def download_result():
    if 'evaluation_data' not in session:
        return "No evaluation data found", 404
    
    data = session['evaluation_data']
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#8b5cf6'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#3b82f6'),
        spaceAfter=10,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        alignment=TA_JUSTIFY
    )
    
    # Title
    story.append(Paragraph("AI Answer Sheet Evaluation Report", title_style))
    story.append(Spacer(1, 12))
    
    # Score
    score_table_data = [
        ['Suggested Marks', f"{data['score']}/{data['max_marks']}"]
    ]
    score_table = Table(score_table_data, colWidths=[2*inch, 2*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#8b5cf6')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (1, 0), 12),
        ('TOPPADDING', (0, 0), (1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
        ('FONTNAME', (0, 1), (1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (1, 1), 12),
        ('ALIGN', (0, 1), (1, 1), 'CENTER'),
        ('TOPPADDING', (0, 1), (1, 1), 10),
        ('BOTTOMPADDING', (0, 1), (1, 1), 10),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 16))
    
    # Feedback
    story.append(Paragraph("Feedback", heading_style))
    story.append(Paragraph(data['feedback'], normal_style))
    story.append(Spacer(1, 16))
    
    # Question
    story.append(Paragraph("Question Paper", heading_style))
    question_text = data['question'][:1000] + "..." if len(data['question']) > 1000 else data['question']
    story.append(Paragraph(question_text, normal_style))
    story.append(Spacer(1, 12))
    
    # Answer
    story.append(Paragraph("Student Answer", heading_style))
    answer_text = data['answer'][:1000] + "..." if len(data['answer']) > 1000 else data['answer']
    story.append(Paragraph(answer_text, normal_style))
    
    # Answer Key (if available)
    if data.get('answer_key'):
        story.append(Spacer(1, 16))
        story.append(Paragraph("Answer Key", heading_style))
        key_text = data['answer_key'][:1000] + "..." if len(data['answer_key']) > 1000 else data['answer_key']
        story.append(Paragraph(key_text, normal_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='evaluation-result.pdf'
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)