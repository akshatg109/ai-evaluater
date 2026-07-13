# 📄 AI Answer Sheet Evaluator

An AI-powered web application that automatically evaluates handwritten or printed student answer sheets using the **Qwen3-VL-32B-Instruct** vision model via **OpenRouter**. The application reads question papers, answer sheets, and optional answer keys, generates marks with detailed feedback, stores evaluation history, and provides downloadable PDF reports.

---

## 🚀 Features

- 🤖 AI-powered answer evaluation using **Qwen3-VL-32B-Instruct**
- 📄 Supports PDF, PNG, JPG, and JPEG uploads
- ✍️ Reads handwritten and printed answer sheets
- 📚 Optional answer key for more accurate evaluation
- 📊 Automatic marks calculation
- 💬 Detailed AI-generated feedback
- 📥 Downloadable PDF evaluation reports
- 👤 User authentication (Login & Signup)
- 👥 Guest mode support
- 🗄️ Evaluation history stored in Supabase
- ☁️ Cloud deployment using Render

---

## 🛠️ Tech Stack

### Frontend
- HTML5
- CSS3
- Jinja2 Templates

### Backend
- Python
- Flask

### AI
- OpenRouter API
- Qwen3-VL-32B-Instruct

### Database
- Supabase

### Deployment
- Render

### Libraries
- OpenAI Python SDK
- ReportLab
- Pillow
- pdf2image
- python-dotenv

---

## 📂 Project Structure

```text
AI-ANSWER-SHEET-EVALUATOR
│
├── app.py
├── requirements.txt
├── README.md
├── .env
├── .gitignore
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

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/akshatg109/ai-evaluater.git
cd ai-evaluater
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

Activate it:

Linux / macOS

```bash
source venv/bin/activate
```

Windows

```powershell
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

```env
OPENROUTER_API_KEY=your_openrouter_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SECRET_KEY=your_secret_key
```

### 5. Run the application

```bash
python3 app.py
```

Visit:

```
http://127.0.0.1:5000
```

---

## 📖 How It Works

1. Upload the Question Paper.
2. Upload the Student Answer Sheet.
3. Optionally upload an Answer Key.
4. The Qwen3-VL-32B-Instruct vision model reads the uploaded documents.
5. AI evaluates the student's answers.
6. Marks and feedback are generated.
7. Results are saved in Supabase.
8. Users can download a PDF evaluation report.

---

## 📸 Screenshots

Add screenshots of:

- Home Page
- Login Page
- Dashboard
- Upload Page
- Evaluation Result
- History Page

---

## 🌐 Live Demo

**Render Deployment**

https://ai-evaluater.onrender.com

---

## 📈 Future Improvements

- Multi-question answer sheet evaluation
- Teacher dashboard
- Student dashboard
- Analytics and performance charts
- AI confidence score
- Batch evaluation
- Export results to Excel
- Multiple AI model support

---

## 👨‍💻 Author

**Akshat Gupta**

GitHub: https://github.com/akshatg109

LinkedIn: *(Add your LinkedIn profile here)*

---

## 📜 License

This project is developed for educational and learning purposes.
