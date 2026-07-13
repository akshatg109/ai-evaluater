"""Supabase authentication routes."""

from flask import Blueprint, current_app, redirect, render_template, request, session


auth_bp = Blueprint("auth", __name__)


def _supabase_or_error():
    supabase = current_app.extensions["supabase"]
    if supabase is None:
        raise RuntimeError("Authentication is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
    return supabase


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            _supabase_or_error().auth.sign_up({
                "email": request.form["email"],
                "password": request.form["password"],
            })
            return redirect("/login")
        except Exception as error:
            return render_template("error.html", error=str(error)), 400
    return render_template("signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            response = _supabase_or_error().auth.sign_in_with_password({
                "email": request.form["email"],
                "password": request.form["password"],
            })
            session["user"] = response.user.email
            return redirect("/dashboard")
        except Exception as error:
            return render_template("error.html", error=str(error)), 401
    return render_template("login.html")


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect("/")
