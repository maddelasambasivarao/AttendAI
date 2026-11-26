"""
config.py – Configuration classes for AttendAI.
Loaded by the application factory in app.py via app.config.from_object().
"""

import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration – shared by all environments."""

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    WTF_CSRF_ENABLED = True

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'attendai.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── File Paths ────────────────────────────────────────────────────────────
    REPORTS_DIR = os.path.join(BASE_DIR, "reports")
    DATASET_DIR = os.path.join(BASE_DIR, "dataset")
    ML_MODELS_DIR = os.path.join(BASE_DIR, "ml", "models")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

    # ── Upload Limits ─────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

    # ── Attendance Thresholds ─────────────────────────────────────────────────
    ATTENDANCE_REQUIRED = 75        # % required by institution
    HIGH_RISK_THRESHOLD = 60        # Below this → High risk
    MEDIUM_RISK_THRESHOLD = 75      # 60–74 → Medium risk

    @staticmethod
    def init_app(app):
        """Create required directories on startup."""
        for folder in [
            Config.REPORTS_DIR,
            Config.DATASET_DIR,
            Config.ML_MODELS_DIR,
            Config.UPLOAD_FOLDER,
        ]:
            os.makedirs(folder, exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Set True to log SQL queries


class TestingConfig(Config):
    """Testing configuration – runs against an isolated in-memory SQLite database."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": __import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    }
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    WTF_CSRF_ENABLED = True

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)


# ── Config selector ────────────────────────────────────────────────────────────
config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
