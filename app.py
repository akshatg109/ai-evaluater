from flask import Flask, render_template, request, send_file, session,redirect
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
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
from datetime import datetime
from supabase import create_client
from pathlib import Path
import base64
import tempfile


load_dotenv(dotenv_path=Path(__file__).parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Environment variables loaded from .env

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



# API credentials configured via environment variables

api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

print("========== OPENROUTER DEBUG ==========")
print("API key exists:", bool(api_key))
print("API key prefix:", api_key[:10])
print("======================================")

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
    timeout=60
)

# Configuration
UPLOAD_FOLDER = "uploads"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import base64
import tempfile

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


from pdf2image import convert_from_path
from PIL import Image
import os

def pdf_to_images(file_path):

    ext = os.path.splitext(file_path)[1].lower()

    image_paths = []

    # If it's a PDF
    if ext == ".pdf":

        images = convert_from_path(file_path)

        for i, img in enumerate(images):

            output_path = f"{file_path}_{i}.png"

            img.save(output_path, "PNG")

            image_paths.append(output_path)

    # If it's already an image
    elif ext in [".png", ".jpg", ".jpeg"]:

        image_paths.append(file_path)

    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return image_paths



def extract_text_with_qwen(file_path):

    image_paths = pdf_to_images(file_path)

    content = [
        {
            "type": "text",
            "text": """
Read every page carefully.

Extract ALL visible text exactly as written.

Do NOT summarize.

Return ONLY the extracted text.
"""
        }
    ]

    for image in image_paths:

        with open(image, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode()

        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64_image}"
            }
        })

    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-vl-32b-instruct",
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        import traceback

        print("\n========== OPENROUTER OCR ERROR ==========")
        print("Exception:", repr(e))
        print("Cause:", repr(e.__cause__))
        traceback.print_exc()
        print("==========================================\n")

        raise

def file_to_images(file_path):

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return pdf_to_images(file_path)

    elif ext in [".png", ".jpg", ".jpeg"]:
        return [file_path]

    else:
        raise ValueError(f"Unsupported file type: {ext}")


def extract_documents_with_qwen(
    question_path,
    answer_path,
    answer_key_path=None
):

    question_images = file_to_images(question_path)
    answer_images = file_to_images(answer_path)

    answer_key_images = []

    if answer_key_path:
        answer_key_images = file_to_images(answer_key_path)

    print("Question Pages:", len(question_images))
    print("Answer Pages:", len(answer_images))
    print("Answer Key Pages:", len(answer_key_images))

    return {
        "question_images": question_images,
        "answer_images": answer_images,
        "answer_key_images": answer_key_images
    }


def evaluate_complete_submission(
    question_path,
    answer_path,
    answer_key_path=None
):

    question_text = extract_text_with_qwen(question_path)

    student_answer = extract_text_with_qwen(answer_path)

    answer_key_text = None

    if answer_key_path:
        answer_key_text = extract_text_with_qwen(answer_key_path)

    max_marks = extract_max_marks(question_text)

    result = evaluate_answer(
        question_text,
        student_answer,
        max_marks,
        answer_key_text
    )

    result["question_text"] = question_text
    result["student_answer"] = student_answer
    result["answer_key"] = answer_key_text
    result["max_marks"] = max_marks

    return result

def format_datetime(dt_string):
    """Format ISO datetime string to readable format"""
    if not dt_string:
        return "Unknown"
    try:
        # Parse ISO format datetime
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        # Format as: "Jun 23, 2026 at 2:30 PM"
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except (ValueError, AttributeError):
        return dt_string


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
      import traceback

    print("\n========== QWEN EVALUATION ERROR ==========")
    print("Exception:", repr(e))
    print("Cause:", repr(e.__cause__))
    traceback.print_exc()
    print("===========================================\n")

    return {
        "score": 0,
        "feedback": "AI evaluation is temporarily unavailable."
    }


def generate_report_buffer(data):
    """Build a PDF in memory from evaluation `data` and return a BytesIO buffer."""
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

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=24,
        textColor=colors.HexColor('#8b5cf6'), spaceAfter=12,
        alignment=TA_CENTER, fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'], fontSize=14,
        textColor=colors.HexColor('#3b82f6'), spaceAfter=10,
        spaceBefore=12, fontName='Helvetica-Bold'
    )

    normal_style = ParagraphStyle(
        'CustomNormal', parent=styles['Normal'], fontSize=11,
        spaceAfter=10, alignment=TA_JUSTIFY
    )

    meta_style = ParagraphStyle(
        'MetaStyle', parent=styles['Normal'], fontSize=10,
        textColor=colors.HexColor('#666666'), spaceAfter=4
    )

    # Header
    story.append(Paragraph("📋 AI Answer Sheet Evaluation Report", title_style))
    story.append(Spacer(1, 6))
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#8b5cf6')))
    story.append(Spacer(1, 12))

    if data.get('created_at'):
        story.append(Paragraph(f"<b>Evaluation Date:</b> {data['created_at']}", meta_style))
        story.append(Spacer(1, 12))

    # Score
    score_table_data = [[ 'Suggested Marks', f"{data.get('score', 0)}" ]]
    score_table = Table(score_table_data, colWidths=[2*inch, 2*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#8b5cf6')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (1, 0), 12),
        ('TOPPADDING', (0, 0), (1, 0), 12),
        ('GRID', (0, 0), (1, 0), 1, colors.HexColor('#e0e0e0')),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 20))

    # Feedback
    story.append(Paragraph("💬 Examiner Feedback", heading_style))
    story.append(Paragraph(data.get('feedback', ''), normal_style))
    story.append(Spacer(1, 18))

    # Content sections
    story.append(PageBreak())
    story.append(Paragraph("📖 Question Paper", heading_style))
    story.append(Paragraph(data.get('question', ''), normal_style))
    story.append(Spacer(1, 20))

    story.append(PageBreak())
    story.append(Paragraph("✍️ Student Answer", heading_style))
    story.append(Paragraph(data.get('answer', ''), normal_style))

    if data.get('answer_key'):
        story.append(Spacer(1, 20))
        story.append(PageBreak())
        story.append(Paragraph("✅ Answer Key", heading_style))
        story.append(Paragraph(data.get('answer_key', ''), normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():

    user = session.get("user", "Guest")

    evaluations = []

    if "user" in session:
        evaluations = (
            supabase.table("evaluations")
            .select("*")
            .eq("user_email", session["user"])
            .order("created_at", desc=True)
            .execute()
        ).data

    return render_template(
        "dashboard.html",
        user=user,
        evaluations=evaluations
    )


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

    # Always evaluate, whether or not an answer key exists
    result = evaluate_complete_submission(
        question_path,
        answer_path,
        answer_key_path
    )

    question_text = result["question_text"]
    student_answer = result["student_answer"]
    answer_key_text = result["answer_key"]
    max_marks = result["max_marks"]

    print("QUESTION OCR:", question_text)
    print("ANSWER OCR:", student_answer)
    if answer_key_text:
        print("ANSWER KEY OCR:", answer_key_text)

    score = int(result["score"])
    feedback = result["feedback"]

    email = session.get("user", "guest")

    try:
        supabase.table("evaluations").insert({
            "user_email": email,
            "score": score,
            "feedback": feedback,
            "answer_key": answer_key_text if answer_key_text else "",
            "question_text": question_text,
            "student_answer": student_answer,
            "report_path": ""
        }).execute()

        print("✅ Saved to Supabase")

    except Exception as e:
        print("❌ Supabase Save Error:", e)

    email = session.get("user", "guest")

    try:
        supabase.table("evaluations").insert({
            "user_email": email,
            "score": score,
            "feedback": feedback,
            "answer_key": answer_key_text if answer_key_text else "",
            "question_text": question_text,
            "student_answer": student_answer,
            "report_path": ""
        }).execute()

        print("✅ Saved to Supabase")

    except Exception as e:
        print("❌ Supabase Save Error:", e)

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
    except (OSError, FileNotFoundError):
         pass  # Files may have already been deleted

    return render_template(
        "result.html",
        score=score,
        feedback=feedback,
        max_marks=max_marks
    )
    
@app.route("/history")
def history():

    if "user" not in session:
        return redirect("/login")

    email = session["user"]

    evaluations = (
        supabase.table("evaluations")
        .select("*")
        .eq("user_email", email)
        .order("created_at", desc=True)
        .execute()
    ).data

    # Format dates for display
    for eval in evaluations:
        eval['formatted_date'] = format_datetime(eval.get('created_at'))

    return render_template(
        "history.html",
        evaluations=evaluations,
        user=email
    )
    
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        try:
            supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            return redirect("/login")

        except Exception as e:
            return str(e)

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        try:

            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            session["user"] = response.user.email

            return redirect("/dashboard")

        except Exception as e:
            return str(e)

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


@app.route("/download-history/<int:eval_id>")
def download_history(eval_id):
    """Download individual evaluation from history"""
    if "user" not in session:
        return "Unauthorized", 401
    
    try:
        # Fetch the evaluation from database
        result = supabase.table("evaluations").select("*").eq("id", eval_id).eq("user_email", session["user"]).execute()
        
        if not result.data:
            return "Evaluation not found", 404
        
        eval_data = result.data[0]
        
        # Create data structure for PDF generation
        data = {
            'score': eval_data.get('score', 0),
            'feedback': eval_data.get('feedback', ''),
            'max_marks': 100,  # Default, you may want to store this in DB
            'question': eval_data.get('question_text', ''),
            'answer': eval_data.get('student_answer', ''),
            'answer_key': eval_data.get('answer_key', ''),
            'created_at': format_datetime(eval_data.get('created_at', ''))
        }
    except Exception as e:
        print(f"Error fetching evaluation: {e}")
        return "Error retrieving evaluation", 500
    
    # Use shared PDF builder
    buffer = generate_report_buffer(data)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'evaluation-{eval_id}.pdf'
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
    
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=4
    )
    
    # Title
    story.append(Paragraph("📋 AI Answer Sheet Evaluation Report", title_style))
    story.append(Spacer(1, 6))
    
    # Divider line
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#8b5cf6')))
    story.append(Spacer(1, 12))
    
    # Use shared PDF builder
    buffer = generate_report_buffer(data)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='evaluation-result.pdf'
    )


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)