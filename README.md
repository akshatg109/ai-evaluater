<<<<<<< HEAD
# AI Evaluater

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue" />
  <img src="https://img.shields.io/badge/Flask-Web%20Framework-black" />
  <img src="https://img.shields.io/badge/Supabase-Database-green" />
  <img src="https://img.shields.io/badge/OpenRouter-AI-orange" />
</p>

An AI-powered answer sheet evaluation platform that automatically grades student responses against question papers using OCR and large language models.

## Live Demo

https://ai-evaluater.onrender.com

## Features

- **OCR Text Extraction** -- Extracts text from PDFs (with PyMuPDF + Tesseract fallback for scanned docs) and images via Tesseract
- **AI-Powered Grading** -- Evaluates answers using Qwen3 VL through OpenRouter, with optional answer-key-strict mode
- **PDF Report Generation** -- Generates professional evaluation reports with scores, feedback, question paper, and student answer
- **Evaluation History** -- Stores all evaluations in Supabase with full history browsing and re-download
- **User Authentication** -- Signup/login flow powered by Supabase Auth
- **Responsive Web UI** -- Clean Flask templates for home, dashboard, results, and history

## Architecture

```
Browser  ──▶  Flask App  ──▶  OpenRouter (Qwen3 VL)
                │
                ├──▶  Tesseract / PyMuPDF  (OCR)
                ├──▶  Supabase  (Auth + Database)
                └──▶  ReportLab  (PDF generation)
```

## Tech Stack

| Layer      | Technology                                    |
|------------|-----------------------------------------------|
| Backend    | Python 3, Flask                               |
| AI         | OpenRouter API (Qwen3 VL 32B)                |
| OCR        | Tesseract, PyMuPDF, pdf2image, Pillow         |
| Database   | Supabase (PostgreSQL + Auth)                  |
| PDF        | ReportLab                                     |
| Frontend   | HTML/CSS (Jinja2 templates)                   |
| Deployment | Render, Gunicorn                              |

## Prerequisites

- Python 3.10+
- Tesseract OCR installed (`sudo apt install tesseract-ocr`)
- Poppler utilities (`sudo apt install poppler-utils`) for PDF-to-image fallback
- A Supabase project
- An OpenRouter API key

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/aadvik1864/ai-evaluater.git
   cd ai-evaluater
   ```

2. **Install dependencies**

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Fill in your keys:

   ```env
   OPENROUTER_API_KEY=your_openrouter_key
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your_supabase_anon_key
   ```

4. **Run the application**

   ```bash
   python app.py
   ```

   The app starts at **http://localhost:5000**.

5. **Production**

   ```bash
   gunicorn -w 4 --bind 0.0.0.0:5000 app:app
   ```

## Usage

1. **Sign up** for an account on the landing page
2. **Upload** a question paper (PDF or image) and a student answer (PDF or image)
3. Optionally upload an **answer key** for strict grading
4. View the **AI-generated score and feedback**
5. **Download** the evaluation as a formatted PDF report
6. Browse all past evaluations in **History**

## Environment Variables

| Variable              | Required | Description                          |
|-----------------------|----------|--------------------------------------|
| `OPENROUTER_API_KEY`  | Yes      | OpenRouter API key for Qwen3 VL     |
| `SUPABASE_URL`        | Yes      | Supabase project URL                |
| `SUPABASE_KEY`        | Yes      | Supabase anon/public key            |
| `SECRET_KEY`          | No       | Flask session secret (has default)  |
| `FLASK_ENV`           | No       | Set to `development` for debug mode |

## License

MIT
=======
# AI Answer Sheet Evaluator

A Flask application that reads question papers and handwritten answer sheets with Qwen, evaluates submissions, stores optional Supabase history, and creates PDF reports.

## Project structure

```text
app.py                         Start the application: python3 app.py
requirements.txt               Python dependencies
.env                           Local secrets (not committed)

evaluator_app/                All application code
  application.py               Flask application factory
  config.py                    Environment-backed settings
  extensions.py                OpenRouter and Supabase clients
  routes/                      HTTP endpoints
  services/                    Qwen document reading, grading, PDF reports
  templates/                   Jinja HTML pages
  static/                      CSS and browser-side behaviour

tests/                         Automated smoke tests
uploads/                       Temporary uploads; cleaned after each evaluation
data/legacy_database.db        Preserved local database; not used by the app
```

## Run locally

1. Create `.env` from `.env.example`, then add `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, and a long random `SECRET_KEY`.
2. Install dependencies: `pip install -r requirements.txt`
3. Start the app: `python3 app.py`

## Evaluation workflow

Each submission uses two Qwen calls:

1. Read the question paper, student answer (including handwriting), and optional answer key; return transcriptions and maximum marks.
2. Grade the transcribed answer and return a score and feedback.

PDF, PNG, JPG, and JPEG uploads are supported.
>>>>>>> 6dec33b (Clean architecture and reduced api calls)
