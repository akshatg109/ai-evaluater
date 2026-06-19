from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            keywords TEXT NOT NULL,
            max_marks INTEGER NOT NULL
        )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        student_answer TEXT NOT NULL,
        suggested_marks INTEGER NOT NULL,
        feedback TEXT NOT NULL
    )
""")

    conn.commit()
    conn.close()

init_db()



@app.route("/responses")
def responses():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT responses.id,
               questions.question,
               responses.student_answer,
               responses.suggested_marks,
               responses.feedback
        FROM responses
        JOIN questions
        ON responses.question_id = questions.id
    """)

    data = cursor.fetchall()

    conn.close()

    return render_template("responses.html", responses=data)

@app.route("/student", methods=["GET", "POST"])
def student():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        question_id = request.form["question_id"]
        student_answer = request.form["student_answer"].lower()

        cursor.execute(
            "SELECT keywords, max_marks FROM questions WHERE id = ?",
            (question_id,)
        )

        keywords, max_marks = cursor.fetchone()

        keyword_list = [k.strip().lower() for k in keywords.split(",")]

        matched = sum(1 for word in keyword_list if word in student_answer)

        score = round((matched / len(keyword_list)) * max_marks)

        if score >= max_marks * 0.8:
            feedback = "Excellent answer"
        elif score >= max_marks * 0.5:
            feedback = "Good answer, but some points are missing"
        else:
            feedback = "Review the topic and include more key points"

        cursor.execute("""
            INSERT INTO responses
            (question_id, student_answer, suggested_marks, feedback)
            VALUES (?, ?, ?, ?)
        """, (question_id, student_answer, score, feedback))

        conn.commit()
        conn.close()

        return render_template(
            "result.html",
            score=score,
            feedback=feedback
        )

    cursor.execute("SELECT id, question FROM questions")
    questions = cursor.fetchall()

    conn.close()

    return render_template("student.html", questions=questions)

@app.route("/teacher", methods=["GET", "POST"])
def teacher():


    if request.method == "POST":
        question = request.form["question"]
        model_answer = request.form["model_answer"]
        keywords = request.form["keywords"]
        max_marks = request.form["max_marks"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO questions (question, model_answer, keywords, max_marks)
            VALUES (?, ?, ?, ?)
        """, (question, model_answer, keywords, max_marks))

        conn.commit()
        conn.close()

        return redirect("/teacher")
    

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions")
    questions = cursor.fetchall()
    conn.close()

    return render_template("teacher.html", questions=questions)

@app.route("/")
def home():
    return redirect("/teacher")


if __name__ == "__main__":
    app.run(debug=True)