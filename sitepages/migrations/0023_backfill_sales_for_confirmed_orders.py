from django.db import migrations


def backfill_sales_for_confirmed_orders(apps, schema_editor):
    Order = apps.get_model("sitepages", "Order")
    Sale = apps.get_model("sitepages", "Sale")
    SaleItem = apps.get_model("sitepages", "SaleItem")

    for order in Order.objects.filter(status="confirmed").iterator():
        sale, _ = Sale.objects.get_or_create(
            order_id=order.pk,
            defaults={
                "sale_id": f"S{order.order_id}",
                "user_id": order.user_id,
                "full_name": order.full_name,
                "phone": order.phone,
                "email": order.email,
                "payment_method": order.payment_method,
                "subtotal_amount": order.subtotal_amount,
                "shipping_amount": order.shipping_amount,
                "total_amount": order.total_amount,
                "item_count": order.item_count,
            },
        )

        existing_order_item_ids = set(
            SaleItem.objects.filter(sale=sale).values_list("order_item_id", flat=True)
        )
        SaleItem.objects.bulk_create(
            [
                SaleItem(
                    sale_id=sale.pk,
                    order_item_id=order_item.pk,
                    product_id=order_item.product_id,
                    product_name=order_item.product_name,
                    product_sku=order_item.product_sku,
                    category_name=order_item.category_name,
                    brand_name=order_item.brand_name,
                    quantity=order_item.quantity,
                    unit_price=order_item.unit_price,
                    subtotal=order_item.subtotal,
                )
                for order_item in order.items.all()
                if order_item.pk not in existing_order_item_ids
            ]
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("sitepages", "0022_sale_saleitem"),
    ]

    operations = [
        migrations.RunPython(backfill_sales_for_confirmed_orders, noop_reverse),
    ]
