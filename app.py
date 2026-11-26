"""
app.py – Application factory for AttendAI.
Run with:  flask run   or   python app.py
"""

import os
import click
from flask import Flask
from config import config
from database.models import db, User, Faculty, Semester, Student, Subject
from flask_login import LoginManager

login_manager = LoginManager()


def create_app(config_name: str = "default") -> Flask:
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── Blueprints ────────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.faculty import faculty_bp
    from routes.attendance import attendance_bp
    from routes.analytics import analytics_bp
    from routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,      url_prefix="/admin")
    app.register_blueprint(faculty_bp,    url_prefix="/faculty")
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(analytics_bp,  url_prefix="/analytics")
    app.register_blueprint(reports_bp,    url_prefix="/reports")

    # ── CLI Commands ──────────────────────────────────────────────────────────
    register_cli(app)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Flask-Login user loader
# ─────────────────────────────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# CLI Commands
# ─────────────────────────────────────────────────────────────────────────────
def register_cli(app: Flask):

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("✅  Database tables created.")

    @app.cli.command("seed-db")
    def seed_db():
        """Seed the database with initial admin user and sample data."""
        from seed import seed_database
        seed_database()

    @app.cli.command("train-model")
    def train_ml_model():
        """Train and evaluate the attendance risk classifiers and select the best model (Logistic Regression v2.0.0)."""
        from ml.train import train_model, generate_synthetic_dataset
        from ml.train import train_and_compare_models

        click.echo("[AttendAI] Running Machine Learning training & model comparison...")
        result = train_and_compare_models()
        best_name = result["best_model_name"]
        best_acc = result["metadata"]["test_accuracy"]
        best_f1 = result["metadata"]["test_f1_score"]
        click.echo(f"\n[AttendAI] Best Model Selected: {best_name} (Accuracy: {best_acc*100:.2f}%, F1: {best_f1:.4f})")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("email")
    @click.argument("password")
    def create_admin(username, email, password):
        """Create a new admin user. Usage: flask create-admin <username> <email> <password>"""
        db.create_all()
        if User.query.filter_by(username=username).first():
            click.echo(f"[Error] User '{username}' already exists.")
            return
        user = User(username=username, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"[Success] Admin '{username}' created.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    app.run(debug=True)
