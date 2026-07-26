from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0012_brand"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="SubCategory"),
                migrations.DeleteModel(name="Brand"),
                migrations.DeleteModel(name="Category"),
            ],
        ),
    ]
