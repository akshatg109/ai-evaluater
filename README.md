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
│   ├── routes/
│   ├── services/
│   ├── templates/
│   └── static/
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
SUPABASE_KEY=your_supabase_key
SECRET_KEY=your_secret_key
```

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

# 📖 Workflow

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

---

# 🌟 Future Improvements

- Batch evaluation
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
