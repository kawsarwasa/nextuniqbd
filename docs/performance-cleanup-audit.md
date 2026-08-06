# Performance cleanup audit

Audit date: 2026-08-06

## Safe to delete locally

- `__pycache__/` directories and `*.pyc` files: Python bytecode is regenerated automatically and is already ignored.
- `django-devserver*.log` and `django-run*.log`: local development logs; preserve a copy only if actively diagnosing an issue.
- `*.map` files only when browser source-map debugging is not required. New maps are ignored, but existing deployment copies must be checked before removal.

## Probably safe, but verify the deployed document root first

- `public/static/` and `public/media/`: these may be the cPanel/Passenger web-root copies.
- `staticfiles/`: production `collectstatic` output; regenerate with `python manage.py collectstatic` only after confirming the deployment path.
- `source_files/`: appears to contain AdminLTE source/distribution assets. Keep it if builds or deployment copy steps rely on it.

## Must keep

- `static/`: Django static source used by development and `collectstatic`.
- `media/`: uploaded product, category, brand, company, and hero images, including generated product WebP derivatives.
- `public/`: possible cPanel document root.
- `.git/`: repository history and deployment metadata.

No deployment, public, media, source, or generated asset directories were deleted during this audit.
