from django.db import migrations


def seed_default_company_profile(apps, schema_editor):
    CompanyProfile = apps.get_model("company", "CompanyProfile")
    CompanyProfile.objects.get_or_create(
        company_name="SBRevo",
        defaults={
            "sort_order": 0,
            "is_active": True,
        },
    )


def remove_default_company_profile(apps, schema_editor):
    CompanyProfile = apps.get_model("company", "CompanyProfile")
    CompanyProfile.objects.filter(company_name="SBRevo", logo="").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("company", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_company_profile, remove_default_company_profile),
    ]
