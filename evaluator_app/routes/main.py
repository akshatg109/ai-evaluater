"""Landing page, dashboard, and history routes."""

from datetime import datetime

from flask import Blueprint, current_app, redirect, render_template, session


main_bp = Blueprint("main", __name__)


def format_datetime(value):
    """Format a Supabase ISO timestamp for display."""
    if not value:
        return "Unknown"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %d, %Y at %I:%M %p")
    except (AttributeError, ValueError):
        return value


def _user_evaluations(email):
    supabase = current_app.extensions["supabase"]
    if supabase is None:
        return []
    return (
        supabase.table("evaluations")
        .select("*")
        .eq("user_email", email)
        .order("created_at", desc=True)
        .execute()
    ).data


@main_bp.get("/")
def home():
    return render_template("home.html")


@main_bp.get("/dashboard")
def dashboard():
    user = session.get("user", "Guest")
    return render_template(
        "dashboard.html",
        user=user,
        evaluations=_user_evaluations(user) if user != "Guest" else [],
    )


@main_bp.get("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    evaluations = _user_evaluations(session["user"])
    for evaluation in evaluations:
        evaluation["formatted_date"] = format_datetime(evaluation.get("created_at"))
    return render_template("history.html", evaluations=evaluations, user=session["user"])
