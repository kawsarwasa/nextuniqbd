# AI Agent Instructions for Revo

This repository is a Django 6.0.3 monolithic web application.

## What agents should know first

- The Django project root is `manage.py`; settings live in `config/settings.py`.
- Installed apps are:
  - `blog`, `category`, `accounts`, `orders`, `carousel`, `company`, `purchase`, `sitepages`
- Templates are in `templates/`; static source files are in `static/`; runtime static output is in `staticfiles/`.
- Media content is stored under `media/` and served only in debug mode.

## Development commands

- Install dependencies:
  - `python -m pip install -r requirements.txt`
- Run the development server:
  - `python manage.py runserver`
- Run app tests:
  - `python manage.py test`

## Database behavior

- The project uses MySQL only in development, testing, and production.
- Set `DB_ENGINE=mysql` plus `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` before running Django.
- The configured MySQL user must have permission to create and remove the Django test database.

## Useful repository conventions

- URL routing is centralized in `config/urls.py` and includes each app's `urls.py`.
- App-level logic is typically split across `models.py`, `views.py`, `forms.py`, and `urls.py`.
- Custom Django context processors are implemented in `sitepages/context_processors.py` and `company/context_processors.py`.

## Recommended behavior for AI agents

- Preserve existing project structure and Django conventions.
- Avoid changing `SECRET_KEY` or `DEBUG` unless explicitly asked.
- Prefer minimal changes and ensure any code change is consistent with the app's existing patterns.
- If data or environment setup is needed, confirm the required MySQL environment variables and run `python manage.py migrate`.

## Documentation reference

- Project-specific product dashboard requirements are in `docs/product-dashboard-spec.md`.
