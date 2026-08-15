# Production deployment notes

## Build and run

1. Create a virtual environment and install `requirements.txt`.
2. Set `DJANGO_DOTENV_OVERRIDE=false`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, explicit `DJANGO_ALLOWED_HOSTS`, database variables, and cache variables. With dotenv override disabled, process/container secrets take precedence over `.env`.
3. Run `python manage.py migrate`.
4. Run `python manage.py collectstatic --noinput` and serve `STATIC_ROOT` at `/static/` with Apache/nginx/CDN. Serve `MEDIA_ROOT` at `/media/`; Django does not serve uploads in production.
5. Start the WSGI application through Passenger or another production WSGI/ASGI server.

Set `DB_CONN_MAX_AGE` to a measured value such as `60` and `DB_CONN_HEALTH_CHECKS=true` for persistent production database connections. For shared cache, set `CACHE_BACKEND=django.core.cache.backends.redis.RedisCache` and a private `CACHE_LOCATION` Redis URL.

## HTTPS and proxy settings

HTTPS redirect and secure cookies default on when debug is false. Enable `DJANGO_TRUST_PROXY_SSL_HEADER=true` only if a trusted reverse proxy overwrites `X-Forwarded-Proto`. Start HSTS with a small `DJANGO_SECURE_HSTS_SECONDS`, verify every subdomain supports HTTPS, then increase it; do not enable include-subdomains or preload casually.

## Compression and caching

Enable gzip and Brotli at the reverse proxy/CDN for HTML, CSS, JavaScript, SVG and JSON. WhiteNoise's compressed manifest storage creates content-hashed filenames; serve those with `Cache-Control: public, max-age=31536000, immutable`. Give HTML short/no-cache policy and user uploads an application-appropriate policy. WhiteNoise serves collected static files when Apache/cPanel is not configured to serve them directly.

## Media maintenance and images

- `python manage.py audit_unused_media` reports orphaned, missing and duplicate files without deleting.
- `python manage.py audit_unused_media --delete` is destructive and must run only after review and backup.
- `python manage.py optimize_media_images` previews WebP sidecar savings for images over 150 KiB.
- `python manage.py optimize_media_images --write` creates `.optimized.webp` sidecars while retaining originals and transparency. It does not upscale or replace originals. Templates should switch to a sidecar only after visual verification.

## Rollback

Back up code, database and `MEDIA_ROOT` before deployment. Roll back code to the prior release, run the reverse migration only when its data impact is understood, rebuild static files, and restart workers. The homepage cache is disposable and can be cleared safely. Never restore `media/` from `public/media/`; it is not the configured source of truth.
