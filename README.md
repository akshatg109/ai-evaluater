# 📄 AI-Powered Answer Sheet Evaluation Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue" />
  <img src="https://img.shields.io/badge/Flask-Web%20Framework-black" />
  <img src="https://img.shields.io/badge/Supabase-Database-green" />
  <img src="https://img.shields.io/badge/OpenRouter-AI-orange" />
  <img src="https://img.shields.io/badge/Render-Deployed-purple" />
</p>

An AI-powered web application that evaluates handwritten answer sheets using **Qwen3-VL-32B-Instruct** through **OpenRouter**.

The platform allows teachers to upload a **question paper**, a **student answer sheet**, and an optional **answer key**. It generates AI-assisted marks, structured feedback, and downloadable evaluation reports.

---

## 🚀 Live Demo

🌐 https://ai-evaluater.onrender.com

---

# 📸 Screenshots

## Landing Page

![Landing Page](screenshots/landing-page.png)

## Evaluation Dashboard

![Dashboard](screenshots/dashboard.png)

---

# ✨ Features

- Upload **PDF**, **JPG**, and **PNG** files
- Upload question paper and student answer sheet
- Optional answer key support
- AI-powered handwritten answer evaluation
- Generate marks and structured feedback
- Download evaluation reports
- Cloud database using Supabase
- Responsive user interface
- Deployed on Render

---

# 🛠 Tech Stack

## Backend

- Python
- Flask

## Database

- Supabase

## AI

- OpenRouter API
- Qwen3-VL-32B-Instruct

## Frontend

- HTML
- CSS

## Deployment

- Render

---

# ⚙️ Installation

```bash
git clone https://github.com/akshatg109/ai-evaluater.git

cd ai-evaluater

python -m venv venv

pip install -r requirements.txt
```

Create a `.env` file

```env
OPENROUTER_API_KEY=YOUR_KEY

SUPABASE_URL=YOUR_URL

SUPABASE_KEY=YOUR_KEY
```

Run

```bash
python app.py
```

---

# 📂 Project Structure

```text
app.py
templates/
static/
uploads/
utils/
requirements.txt
README.md
```

---

# 🔮 Future Improvements

- Batch evaluation of multiple answer sheets
- Teacher dashboard with analytics
- Student dashboard
- Improved report customization
- Enhanced UI/UX

---

# 👨‍💻 Author

Akshat Gupta

GitHub:
https://github.com/akshatg109

LinkedIn:
https://linkedin.com/in/akshatg109
