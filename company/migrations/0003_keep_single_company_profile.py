from django.db import migrations


def keep_single_company_profile(apps, schema_editor):
    CompanyProfile = apps.get_model("company", "CompanyProfile")
    profiles = list(CompanyProfile.objects.order_by("-logo", "-is_active", "-updated_at", "id"))
    if not profiles:
        return

    keeper = profiles[0]
    CompanyProfile.objects.exclude(pk=keeper.pk).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0002_seed_default_company_profile"),
    ]

    operations = [
        migrations.RunPython(keep_single_company_profile, noop_reverse),
    ]
