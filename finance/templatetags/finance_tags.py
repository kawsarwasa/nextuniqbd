from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()
ZERO_AMOUNT = Decimal("0.00")


@register.filter
def money(value):
    """Render a safe Taka amount without converting through float."""
    if value is None or value == "":
        amount = ZERO_AMOUNT
    else:
        try:
            amount = Decimal(str(value).replace(",", ""))
        except (InvalidOperation, TypeError, ValueError):
            amount = ZERO_AMOUNT
    return f"৳{amount:,.2f}"
