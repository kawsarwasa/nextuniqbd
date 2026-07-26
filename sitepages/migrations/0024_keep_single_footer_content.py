from django.db import migrations


def keep_single_footer_content(apps, schema_editor):
    FooterContent = apps.get_model("sitepages", "FooterContent")
    footers = list(FooterContent.objects.order_by("-is_active", "-updated_at", "id"))
    if not footers:
        return

    keeper = footers[0]
    FooterContent.objects.exclude(pk=keeper.pk).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sitepages", "0023_backfill_sales_for_confirmed_orders"),
    ]

    operations = [
        migrations.RunPython(keep_single_footer_content, noop_reverse),
    ]
