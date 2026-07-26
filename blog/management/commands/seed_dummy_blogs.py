from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from blog.models import BlogCategory, BlogComment, BlogPost, BlogPostImage, BlogTag


class Command(BaseCommand):
    help = "Create 10 dummy blog posts with categories, tags, images, and comments for dashboard testing."

    CATEGORY_DATA = [
        ("Fashion", "Style ideas, seasonal wardrobe updates, and outfit direction."),
        ("Lifestyle", "Daily routines, wellness habits, and intentional living."),
        ("Travel", "Packing lists, city notes, and destination inspiration."),
        ("Trends", "Emerging looks, colors, and market movements."),
        ("Guides", "Practical how-to content and evergreen reference posts."),
    ]

    TAG_DATA = [
        ("style", "Styling tips and wardrobe edits."),
        ("summer", "Warm weather looks and essentials."),
        ("minimal", "Clean design and capsule ideas."),
        ("travel", "Packing and destination content."),
        ("denim", "Denim staples and outfit combinations."),
        ("accessories", "Bags, jewelry, belts, and finishing touches."),
        ("shopping", "Buying guides and product curation."),
        ("wellness", "Balanced living and everyday habits."),
        ("streetwear", "Modern casualwear and statement pieces."),
        ("editorial", "Magazine-inspired concepts and visual storytelling."),
    ]

    POST_BLUEPRINTS = [
        {
            "title": "Top 10 Fashion Trends You Need to Know This Season",
            "category": "Trends",
            "author": "Sarah Johnson",
            "tags": ["style", "summer", "editorial"],
        },
        {
            "title": "How to Build a Capsule Wardrobe on a Budget",
            "category": "Guides",
            "author": "Mike Rodriguez",
            "tags": ["minimal", "shopping", "style"],
        },
        {
            "title": "Packing Light for a Weekend Getaway",
            "category": "Travel",
            "author": "Emma Davis",
            "tags": ["travel", "minimal", "summer"],
        },
        {
            "title": "Five Accessories That Instantly Elevate Any Outfit",
            "category": "Fashion",
            "author": "Olivia Carter",
            "tags": ["accessories", "style", "shopping"],
        },
        {
            "title": "Streetwear Staples That Still Feel Polished",
            "category": "Lifestyle",
            "author": "Daniel Lee",
            "tags": ["streetwear", "style", "denim"],
        },
        {
            "title": "A Practical Guide to Color Pairing in Modern Fashion",
            "category": "Guides",
            "author": "Sophia Khan",
            "tags": ["editorial", "style", "summer"],
        },
        {
            "title": "What to Wear for Rainy Days Without Losing Your Look",
            "category": "Lifestyle",
            "author": "Noah Ahmed",
            "tags": ["style", "shopping", "minimal"],
        },
        {
            "title": "The Denim Pieces Worth Keeping in Rotation",
            "category": "Fashion",
            "author": "Ava Thompson",
            "tags": ["denim", "style", "streetwear"],
        },
        {
            "title": "Morning Habits That Make Getting Dressed Easier",
            "category": "Lifestyle",
            "author": "Liam Patel",
            "tags": ["wellness", "minimal", "style"],
        },
        {
            "title": "City Break Style Notes From a Three-Day Trip",
            "category": "Travel",
            "author": "Isabella Brown",
            "tags": ["travel", "editorial", "accessories"],
        },
    ]

    COMMENT_TEMPLATES = [
        {
            "author_name": "Nadia Rahman",
            "author_email": "nadia@example.com",
            "body": "This layout of ideas is useful. The recommendations feel practical instead of generic.",
            "is_approved": True,
        },
        {
            "author_name": "Arif Hasan",
            "author_email": "arif@example.com",
            "body": "Saved this one for later. The examples around mixing basics and standout pieces were the most helpful part.",
            "is_approved": True,
        },
        {
            "author_name": "Megan Collins",
            "author_email": "megan@example.com",
            "body": "Would like a follow-up post with specific outfit combinations, but this is a strong starting point.",
            "is_approved": False,
        },
    ]

    def handle(self, *args, **options):
        image_pool = sorted((Path("media") / "products").glob("*.jpg"))
        if len(image_pool) < 30:
            raise CommandError("Not enough source images found in media/products to seed dummy blogs.")

        category_map = {}
        for index, (name, description) in enumerate(self.CATEGORY_DATA):
            category, _ = BlogCategory.objects.get_or_create(
                name=name,
                defaults={
                    "description": description,
                    "sort_order": index,
                    "is_active": True,
                },
            )
            category_map[name] = category

        tag_map = {}
        for name, description in self.TAG_DATA:
            tag, _ = BlogTag.objects.get_or_create(
                name=name.title(),
                defaults={"description": description, "is_active": True},
            )
            tag_map[name] = tag

        created_total = 0
        skipped_total = 0

        for index, blueprint in enumerate(self.POST_BLUEPRINTS):
            if BlogPost.objects.filter(title=blueprint["title"]).exists():
                skipped_total += 1
                continue

            published_at = timezone.now() - timezone.timedelta(days=(index + 1) * 3)
            post = BlogPost.objects.create(
                category=category_map[blueprint["category"]],
                title=blueprint["title"],
                author_name=blueprint["author"],
                excerpt=self.build_excerpt(blueprint["title"], blueprint["category"]),
                content=self.build_content(blueprint["title"], blueprint["author"], blueprint["category"]),
                status=BlogPost.Status.PUBLISHED,
                allow_comments=True,
                published_at=published_at,
            )

            post.tags.set([tag_map[tag_name] for tag_name in blueprint["tags"]])

            featured_source = image_pool[index * 3]
            gallery_sources = [image_pool[index * 3 + 1], image_pool[index * 3 + 2]]
            self.attach_featured_image(post, featured_source, index)
            self.attach_gallery_images(post, gallery_sources, index)
            self.attach_comments(post, index)

            created_total += 1
            self.stdout.write(self.style.SUCCESS(f'Created "{post.title}"'))

        self.stdout.write(
            self.style.SUCCESS(
                f"Dummy blog seeding complete. Created {created_total} posts and skipped {skipped_total} existing posts."
            )
        )

    def build_excerpt(self, title, category_name):
        return (
            f"{title} breaks down actionable {category_name.lower()} ideas with wearable examples, "
            "shopping direction, and a clean summary for dashboard preview cards."
        )

    def build_content(self, title, author_name, category_name):
        title_slug = title.lower()
        return f"""
<p><strong>{title}</strong> is demo content created for the dashboard blog manager. It gives you a realistic post body with headings, paragraphs, lists, and enough structure to test the editor output.</p>
<p>Written by {author_name}, this {category_name.lower()} piece focuses on visual rhythm, practical advice, and content blocks that are useful when reviewing how the dashboard saves rich text.</p>
<h2>Why this sample exists</h2>
<p>The main goal is to make the dashboard feel populated. A static page is hard to evaluate, so these posts include category links, tags, comments, and multiple images.</p>
<blockquote>Good dummy content should be realistic enough to reveal layout issues without pretending to be finished editorial copy.</blockquote>
<h3>Key points</h3>
<ul>
  <li>Category and tag relationships are already attached.</li>
  <li>Each post includes a featured image plus gallery images.</li>
  <li>Comments include both approved and pending moderation states.</li>
</ul>
<p>If you later connect the frontend, this post content is already formatted as HTML and can render directly on a dynamic blog details page.</p>
<p>Reference keyword for testing search and slug behavior: {title_slug}.</p>
"""

    def attach_featured_image(self, post, source_path, index):
        with source_path.open("rb") as image_file:
            filename = f"dummy-blog-{index + 1:02d}-featured{source_path.suffix.lower()}"
            post.featured_image.save(filename, File(image_file), save=True)

    def attach_gallery_images(self, post, source_paths, index):
        for image_offset, source_path in enumerate(source_paths, start=1):
            with source_path.open("rb") as image_file:
                gallery_image = BlogPostImage(post=post, sort_order=image_offset - 1)
                filename = f"dummy-blog-{index + 1:02d}-gallery-{image_offset}{source_path.suffix.lower()}"
                gallery_image.image.save(filename, File(image_file), save=False)
                gallery_image.caption = f"Demo gallery image {image_offset} for {post.title}"
                gallery_image.save()

    def attach_comments(self, post, index):
        for offset, template in enumerate(self.COMMENT_TEMPLATES):
            BlogComment.objects.create(
                post=post,
                author_name=template["author_name"],
                author_email=template["author_email"],
                body=template["body"],
                is_approved=template["is_approved"],
                created_at=timezone.now() - timezone.timedelta(days=index, hours=offset * 3),
            )
