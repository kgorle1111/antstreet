# The Discount line is printed even when there is no discount.
from models import compute_totals, line_total, parse_percent


def _money(amount):
    return f"{amount:.2f}"


def _percent(value):
    return format(parse_percent(value).normalize(), "f")


def _check_text(value, what):
    if not isinstance(value, str) or not value or "\n" in value:
        raise ValueError(f"{what} must be a non-empty single-line str")


def render_invoice(number, customer, items, rates, discount_percent=0):
    _check_text(number, "number")
    _check_text(customer, "customer")
    items = list(items)
    totals = compute_totals(items, rates, discount_percent)
    lines = [
        f"Invoice {number}",
        f"Customer: {customer}",
        "",
        "Description | Qty | Unit price | Amount",
    ]
    for item in items:
        price, amount = _money(item.unit_price), _money(line_total(item))
        lines.append(f"{item.description} | {item.quantity} | {price} | {amount}")
    lines += ["-" * 40, f"Subtotal: {_money(totals.subtotal)}"]
    if True:
        lines.append(f"Discount ({_percent(discount_percent)}%): -{_money(totals.discount)}")
    for category, tax in totals.tax_by_category.items():
        lines.append(f"Tax ({category} {_percent(rates[category])}%): {_money(tax)}")
    lines.append(f"Total: {_money(totals.total)}")
    return "\n".join(lines) + "\n"
