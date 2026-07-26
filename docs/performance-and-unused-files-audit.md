# Production performance and unused-files audit

Audit date: 2026-07-14. Audit baseline was captured before cleanup. No media deletion is authorized by this report.

## Summary

- Total project size: **124,297,272 bytes (118.54 MiB)** across 7,743 files.
- Largest top-level directories: `.venv/` 60,015,559 B; `public/` 19,621,632 B; `source_files/` 13,923,786 B; `media/` 10,170,875 B; `staticfiles/` 9,672,085 B; source `static/` 8,238,458 B.
- Other entries: `sitepages/` 587,914 B; `templates/` 557,340 B; `finance/` 438,005 B; `category/` 157,226 B; `blog/` 115,103 B; `purchase/` 70,045 B; `docs/` 39,744 B; `company/` 35,860 B; `orders/` 30,760 B; `accounts/` 27,948 B; `config/` 18,972 B; `carousel/` 11,063 B.
- This directory is not a Git worktree, so tracked status and commit rollback are unavailable.

## Directory roles and safe-cleanup findings

| Path | Finding | Decision |
|---|---|---|
| `.venv/` | local generated environment | remove; recreate with `python -m venv .venv` and pip install |
| `static/` | configured `STATICFILES_DIRS` source | retain |
| `staticfiles/` | configured `STATIC_ROOT`; 182 files, 9,672,085 B | generated; remove and recreate with `collectstatic` |
| `public/static/` | 182-file copy of collected output | probable deployment output; retain pending hosting document-root confirmation |
| `public/media/` | 105-file, incomplete media copy | probable deployment output; retain pending hosting confirmation |
| `source_files/back/src/` | 133 files, 3,613,785 B; AdminLTE SCSS/TS/Astro source | optional rebuild source, not runtime; retain/archive |
| `source_files/back/dist/` | 80 files, 9,395,749 B; AdminLTE build/demo output | not runtime; retain as rebuild/vendor provenance |
| `source_files/front/` | 10 files, 402,344 B; standalone prototypes | not runtime; retain as design provenance |
| `media/` | configured `MEDIA_ROOT`, 120 files | never delete without explicit command review |

Passenger bootstrap only imports `config.wsgi.application`. No Django, Passenger, template, CSS, or JavaScript reference to `public/` or `source_files/` was found. External web-server configuration is unavailable, so `public/` is not safe to delete conclusively.

Generated repository artifacts include 23 application `__pycache__/` directories, 136 `.pyc` files (859,239 B), `.venv/`, `staticfiles/`, local `.env`, and cache/log outputs. `.gitignore` should cover these without ignoring `media/`.

## SHA-256 duplicate audit

SHA-256 was computed for 1,269 files outside `.venv/`. There were **250 duplicate groups, 743 duplicate instances, and 40,004,321 duplicate excess bytes**. Most excess is whole-tree replication among `static/`, `staticfiles/`, `public/static/`, and AdminLTE `source_files/back/{src,dist}`.

Material groups:

| SHA-256 | Copies | Size each | Content |
|---|---:|---:|---|
| `268D80817B7CA0EBDBE39ECC91699AE62C2891F2B5FBAD065FB4E97E6C5E69A6` | 79 | 5,300 | 46 `media/hero_slides/summer-hero*.jpg` plus public copies |
| `6258C1D7FDEAA476607F3716C04916F3D79B6D8D3F53B54C88435506807FC683` | 6 | 8,708 | logo variants and source/generated logo copies |
| `1EB6844B98C617906C397D0692F8AFF539B1532B9ED9082E84F7A5B1746FBDDE` | 5 | 1,145,510 | AdminLTE `photo4.jpg` copies |
| `889DB60A28501F39C853A454906BB0E3B591C95A93D2B10C85FC167F69DF79C2` | 5 | 662,169 | AdminLTE `photo1.png` copies |
| `063C33773494E147AA56BF076224B42970608311ABC03A93E2DB5F60F4F5F954` | 5 | 422,537 | AdminLTE `photo2.png` copies |
| `457102BC8A4D48A472AD64E28C607EE7872DEF4E53AD7C438361F557743FE399` | 5 | 370,563 | AdminLTE `photo3.jpg` copies |
| `C9A569E7DF7854D18B4E6AFEAC797FFE52BFC44124EBFE3CF9A0E41028C3B793` | 4 | 358,903 | unminified AdminLTE CSS copies |
| `54AF286BCD2779DEA8DE6F3069B6087EA73AE8CBED823EB8799E12592670FCC0` | 4 | 297,158 | minified AdminLTE CSS copies |
| `81E69F56FD0F8728DC00FE4125ACB44A966A52B586633C3C27D6B74AA4E574FA` | 4 | 853,463 | AdminLTE CSS maps |
| `60B23E6A99EAF6E46070E7A6B975030621615F0FF37F029BF1F0C5F0D174197E` | 4 | 29,455 | AdminLTE JS copies |
| `D4733227BA5083F9FC98A91D18FAC6DA0495E9E02D3D715848D4E6F57AB21362` | 4 | 11,003 | minified AdminLTE JS copies |
| `7E916F2B984F351EDEC15376780C1276473F640978BD8F10086DD61AEC61D481` | 3 | 121,542 | frontend CSS source/generated copies |
| `2CFA965C6998FC42779A7D21B0C4F8F96AA3B78A387C258327B9EA15C1D538EF` | 3 | 47,128 | frontend JS source/generated copies |

### Media duplicates

`media/` has seven duplicate groups, 58 instances, and 1,086,262 potentially recoverable bytes. They are dry-run findings only:

- `268D...E69A6`: 46 `hero_slides/summer-hero*.jpg` variants.
- `6258...C683`: two `company/logos/next-uniq-bd_*.png` variants.
- `800B...173D1`: dummy blog featured 01 and dummy hero 01.
- `D073...85DE`: dummy blog featured 02 and dummy hero 04.
- `6356...2CC6`: dummy blog gallery 01-1 and dummy hero 02.
- `7A32...47DA`: dummy blog gallery 01-2 and dummy hero 03.
- `0030...E8F9`: dummy blog gallery 02-1 and dummy hero 05.

## Asset reference audit

Checked Django templates (`{% static %}` and model URLs), Python, settings, CSS `url(...)`, JavaScript strings/dynamic paths, Passenger bootstrap, and current database file values.

Required source assets include frontend `style.css`, `script.js`, logo and product placeholder, dashboard AdminLTE/custom CSS and JS, and `dashboard/assets/img/user2-160x160.jpg` (profile fallback).

Confirmed unused AdminLTE demo assets under source `static/dashboard/assets/img/`: AdminLTE logos; `avatar*.png`; boxed backgrounds; `default-150x150.png`; `icons.png`; `photo1` through `photo4`; `prod-1` through `prod-5`; `user1` and `user3` through `user8`; and all credit-card images. No application, CSS, or JS reference was found. Only `user2-160x160.jpg` is used.

The unreferenced LTR minified/unminified duplicates, all RTL bundles, and six `.map` files account for substantial source-static excess. Maps are referenced only by source-map comments, not runtime behavior. Dashboard templates currently load unminified LTR bundles. Production can use minified LTR files after removing map comments.

No font files exist locally; Google Fonts, Font Awesome, Bootstrap Icons and Bootstrap are CDN-loaded. No local asset is referenced only from CSS/JS; AdminLTE embeds SVG data URIs and frontend CSS uses one external Unsplash URL.

Standalone HTML in `source_files/front/` and AdminLTE demo/Astro HTML in `source_files/back/` is not part of Django template discovery. No file under `templates/` was proven unused; guarded dynamic frontend template selection requires retention.

Dead frontend CSS selectors/JS functions were not removed because class names are dynamically applied. Frontend CSS/JS is global and contains multi-page behavior; dashboard assets are correctly dashboard-only; Quill and several scripts are page-specific.

## Database file-field audit

Eight fields were discovered: BlogPost featured image, BlogPostImage image, Category image, ProductImage image, CompanyProfile logo, UserProfile image, HeroSlide image, and HomepagePromoBanner image.

The active MySQL `revo` database had **zero non-empty values in all eight fields** (and zero catalog/hero/blog records). Therefore every current media file appears orphaned relative to this database, but that is not sufficient evidence for deletion: the files may correspond to another deployment database. Media is protected.

## Large images over 150 KiB

Unused demos: `photo4.jpg` 1,145,510 B; `photo1.png` 662,169 B; `photo2.png` 422,537 B; `photo3.jpg` 370,563 B.

Media: `user_profiles/RASEL.jpg` 482,156 B; dummy blog featured 05 395,056 B; featured 08 299,145 B; gallery 06-2 295,746 B; gallery 07-2 285,506 B; product 020-3 271,279 B; gallery 04-2 260,415 B; gallery 02-2 254,707 B; product 030-1 241,404 B; featured 09 224,693 B; gallery 06-1 220,531 B; hero 02 213,371 B; gallery 08-2 210,269 B; gallery 10-2 208,054 B; featured/hero 01 200,305 B; hero 05 198,278 B; gallery 10-1 172,619 B; gallery 09-1 171,618 B; limited-time hero 169,768 B; product 030-2 168,417 B; featured 04 163,036 B; gallery 03-1 155,778 B.

## Homepage query audit

Active data at measurement: zero categories/products/images/reviews/heroes/blog posts and three promo banners.

- Cold cache: HTTP 200, **9 queries**; slowest was 7 ms.
- Warm cache: HTTP 200, **1 query** (company context processor).
- Cold queries: hero (1), categories (1), brands (1), promo large/small (2), posts (1), product-tab category query (1), navigation categories (1), company (1).

The empty catalog understates the code-path cost. `get_homepage_product_tab_context()` executes a product query plus sliced first-image prefetch for fallback, deals, featured, best sellers, and each category. With four categories this is 17 product-tab queries including the category query. This is repeated-query fan-out, not a template N+1. `select_related`, annotated review aggregates and sliced image `Prefetch` already prevent card-level N+1s.

The complete product-tab context is not cached. Existing invalidation covers Category, Brand and Product but omits ProductImage and ProductReview, causing stale cached cards once product-tab caching is added. Promo banners can also be reduced from two queries to one.

Potential indexes matching stable filters/orderings: Category `(is_active, sort_order)`, Product `(status, category, created_at)`, and ProductImage `(product, sort_order)`. ProductReview already has a foreign-key index; an extra `(product, rating)` index should require populated-data evidence.

## Image delivery and production configuration

Homepage product/category/brand/promo/blog images lack consistent intrinsic dimensions, lazy loading and async decoding. Hero images are CSS backgrounds: the first LCP image is not preload-discoverable and all slide URLs are present initially. Preload only the first active hero and do not lazy-load it; delay hidden backgrounds where feasible. Originals must remain; WebP should be sidecar, dry-run-first, transparency-safe and never upscale.

Already present: required environment secret, environment debug/hosts, Redis-compatible cache settings, database connection age/health, manifest static hashing under `DEBUG=False`, HTTPS redirect and secure cookies under `DEBUG=False`.

Gaps: local `.env` enables debug; `check --deploy` reports debug/redirect/secure-cookie/HSTS warnings; HSTS/proxy/trusted origins/security headers and logging are not fully environment-configurable. WhiteNoise is not installed and may be inappropriate if Passenger/Apache serves static. Production must serve `/media/` externally. Configure gzip/Brotli and immutable caching for hashed assets at the web server/CDN.

## Limitations

- No Git metadata is present.
- Hosting document-root/reverse-proxy configuration is outside the project.
- Empty active catalog data prevents representative query plans.
- Browser visual/console validation requires a populated database; server/template/static checks remain available.

## Post-implementation results

- Final repository size: **46,068,578 bytes (43.94 MiB)** across 916 files, down from 124,297,272 bytes (118.54 MiB). Reduction: **78,228,694 bytes (74.60 MiB, 62.94%)**.
- Source static: 8,238,458 bytes / 52 files to 515,838 bytes / 9 required files. Dashboard loads the minified LTR bundle; all source maps and audited demo assets were removed.
- `.venv/`, `staticfiles/`, 23 `__pycache__/` directories and all `.pyc` files were removed. `public/`, `source_files/`, and all pre-existing media were retained.
- One isolated test-created file, `media/hero_slides/summer-hero_JvDrghW.jpg` (5,300 bytes), was detected after the test run. It was not deleted because media deletion requires explicit approval. The leaking test now uses a temporary `MEDIA_ROOT`.
- Active empty-catalog homepage: 9 cold / 1 warm queries before; 8 cold / 0 warm after. Populated four-category regression fixture: 10 cold / 0 warm after; the audited old algorithm would issue about 25 cold queries for the same tab shape.
- Homepage response is HTTP 200 and 22,066 bytes with current empty data. Public route smoke checks pass; protected dashboard routes redirect to login as expected.
- Three additive MySQL homepage indexes were migrated successfully.
- `python manage.py test`: 159 tests passed twice. `check` passes. Template loading passes for 12 critical templates. Production manifest collection passes with 139 source assets / 139 post-processed assets and the generated output was removed afterward.
- `audit_unused_media` and `optimize_media_images` were executed in dry-run only. The latter projects 2,117,893 bytes of WebP sidecar savings; no sidecars or deletions were written.
- Browser visual and console inspection could not run because no in-app/Chrome browser session was available. HTTP, templates, static discovery, manifests, tests, and route smoke checks cover server-side regressions; visual/console comparison remains a manual deployment check.
