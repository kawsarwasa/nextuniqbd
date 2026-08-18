"""Isolated SQLite settings for local test runs when MySQL test DB access is unavailable."""

import os


# config.settings intentionally requires MySQL for application environments.
# Keep that validation intact while replacing only the test database afterwards.
os.environ["DJANGO_DOTENV_OVERRIDE"] = "false"
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DB_ENGINE", "mysql")
os.environ.setdefault("DB_NAME", "test_placeholder")
os.environ.setdefault("DB_USER", "test_placeholder")
os.environ.setdefault("DB_PASSWORD", "test_placeholder")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast hashes are appropriate only for the isolated test database.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
