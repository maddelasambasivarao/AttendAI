"""
routes/auth.py – Authentication blueprint.
Handles login, logout, and password change.
"""

from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from database.models import db, User

auth_bp = Blueprint("auth", __name__)


def is_safe_url(target: str) -> bool:
    """Validates that a redirect URL belongs to the same origin to prevent Open Redirect attacks."""
    if not target:
        return False
    test_url = urlparse(target)
    # Safe internal relative paths: starts with single '/', no netloc
    if not test_url.netloc and target.startswith("/") and not target.startswith("//"):
        return True
    # If absolute URL with scheme, verify same origin against request.host_url
    try:
        from flask import has_request_context
        if has_request_context() and test_url.scheme in ("http", "https"):
            ref_url = urlparse(request.host_url)
            return bool(ref_url.netloc and ref_url.netloc == test_url.netloc)
    except Exception:
        pass
    return False


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("faculty.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username, is_active=True).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.display_name}!", "success")
            next_page = request.args.get("next")
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("faculty.dashboard"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/settings")
@login_required
def settings():
    if current_user.is_admin:
        return redirect(url_for("admin.settings"))
    return redirect(url_for("auth.change_password"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw  = request.form.get("current_password", "")
        new_pw      = request.form.get("new_password", "")
        confirm_pw  = request.form.get("confirm_password", "")

        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
        elif new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
        elif len(new_pw) < 8:
            flash("Password must be at least 8 characters.", "danger")
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("auth.index"))

    return render_template("auth/change_password.html")
