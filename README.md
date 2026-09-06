# 📄 AI Answer Sheet Evaluator

> An AI-powered web application that automatically evaluates handwritten and printed answer sheets using **Qwen3-VL-32B-Instruct** via **OpenRouter**.

<p align="center">

🚀 **Live Demo:** https://ai-evaluater.onrender.com

</p>

---

## ✨ Features

- 🤖 AI-powered answer evaluation using **Qwen3-VL-32B-Instruct**
- 📄 Supports **PDF, PNG, JPG, and JPEG**
- ✍️ Reads handwritten and printed answer sheets
- 📚 Optional Answer Key support
- 📊 Automatic marks calculation
- 💬 Detailed AI-generated feedback
- 📥 Downloadable PDF evaluation reports
- 📚 Batch evaluation for up to 60 answer sheets
- ⏳ Durable background processing with live progress
- 🔐 User Authentication (Login & Signup)
- 👤 Guest Mode
- 🗄️ Evaluation history stored in Supabase
- ☁️ Cloud deployed on Render
- 📱 Responsive UI

---


# 🛠 Tech Stack

### Frontend

- HTML5
- CSS3
- Jinja2

### Backend

- Flask
- Python

### AI

- OpenRouter API
- Qwen3-VL-32B-Instruct

### Database

- Supabase

### Deployment

- Render

### Libraries

- OpenAI SDK
- ReportLab
- Pillow
- pdf2image
- python-dotenv

PDF processing also requires the Poppler `pdftoppm` executable on the host.

---

# ⚙️ Project Structure

```text
AI-ANSWER-SHEET-EVALUATOR
│
├── app.py
├── requirements.txt
├── README.md
├── .env
│
├── evaluator_app/
│   ├── application.py
│   ├── config.py
│   ├── extensions.py
│   ├── worker.py
│   ├── routes/
│   │   ├── batches.py
│   ├── services/
│   │   ├── batches.py
│   ├── templates/
│   └── static/
├── supabase/
│   └── migrations/
│
├── uploads/
└── tests/
```

---

# 🚀 Getting Started

## Clone the Repository

```bash
git clone https://github.com/akshatg109/ai-evaluater.git
cd ai-evaluater
```

## Create Virtual Environment

```bash
python3 -m venv venv
```

Activate it

Linux / macOS

```bash
source venv/bin/activate
```

Windows

```powershell
venv\Scripts\activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Create `.env`

```env
OPENROUTER_API_KEY=your_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_server_only_supabase_key
SUPABASE_STORAGE_BUCKET=evaluation-batches
SECRET_KEY=your_secret_key
```

`SUPABASE_KEY` is used only by the Flask web service and Render worker. Use a server-only
Supabase service-role key, never expose it to browser JavaScript, and keep the storage bucket
private.

---

## Run

```bash
python3 app.py
```

Open

```
http://127.0.0.1:5000
```

---

# 📖 Single-Sheet Workflow

```text
User
   │
   ▼
Upload Question Paper
Upload Answer Sheet
(Optional) Upload Answer Key
   │
   ▼
Flask Backend
   │
   ▼
Qwen3-VL-32B-Instruct
(Document Understanding + Evaluation)
   │
   ▼
Marks + Feedback
   │
   ├────────► Supabase Database
   │
   └────────► PDF Report
   │
   ▼
Result Page
```

## Batch Workflow

1. Select one question paper, an optional answer key, and up to 60 answer sheets on the dashboard.
2. The browser creates batch metadata and uploads each file in a separate request.
3. Flask stores the files in the private `evaluation-batches` Supabase Storage bucket.
4. Starting the batch queues it in Supabase and immediately opens the progress page.
5. A Render Background Worker claims the batch and evaluates sheets sequentially.
6. The progress page polls Supabase-backed status and exposes an individual PDF for each completed sheet.

### Supabase Setup

Run `supabase/migrations/20260906000000_batch_evaluations.sql` in the Supabase SQL editor.
The migration creates the batch tables, indexes, private storage bucket, row-level security,
and the atomic `claim_evaluation_batch` worker function. The application expects the server-side
key to bypass RLS; no batch tables or storage credentials are sent to the browser. If
`SUPABASE_STORAGE_BUCKET` is changed from `evaluation-batches`, create a private bucket with
the replacement name before starting the web service.

### Render Services

Keep the existing web service command and add a separate Background Worker using:

```bash
python -m evaluator_app.worker
```

Configure the same `SUPABASE_URL`, server-only `SUPABASE_KEY`, `SUPABASE_STORAGE_BUCKET`,
`OPENROUTER_API_KEY`, and `EVALUATION_MODEL` values for both services. Set the worker lease,
retry, polling, document-page, request-rate, and retention settings from `.env.example` as
needed for the provider rate limit and storage budget. Set `REQUIRE_STRONG_SECRET=true` and a
random `SECRET_KEY` of at least 32 characters in production.

---

# 🌟 Future Improvements

- Teacher Dashboard
- Student Dashboard
- Analytics Dashboard
- Performance Charts
- Excel Export
- Multiple AI Models
- Multi-question evaluation

---

# 📌 Deployment

**Hosting Platform:** Render

**Database:** Supabase

**AI Provider:** OpenRouter

**Model:** Qwen3-VL-32B-Instruct

---
