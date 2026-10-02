# Money is rounded half to even (banker's rounding) instead of half up.
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _cents(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _to_decimal(value, what):
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise ValueError(f"{what} must be a str, int or Decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{what} is not a decimal numeral: {value!r}") from None
    if not number.is_finite():
        raise ValueError(f"{what} must be finite")
    return number


def parse_percent(value):
    number = _to_decimal(value, "percentage")
    if not 0 <= number <= 100:
        raise ValueError(f"percentage {number} is outside 0..100")
    return number


@dataclass(frozen=True)
class LineItem:
    description: str
    quantity: int
    unit_price: Decimal
    category: str = "standard"

    def __post_init__(self):
        description = self.description
        if not isinstance(description, str) or not description or "\n" in description:
            raise ValueError("description must be a non-empty single-line str")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise ValueError("quantity must be an int")
        if self.quantity < 1:
            raise ValueError("quantity must be at least 1")
        if not isinstance(self.category, str) or not self.category:
            raise ValueError("category must be a non-empty str")
        price = _to_decimal(self.unit_price, "unit_price")
        if price < 0 or price != price.quantize(CENT):
            raise ValueError("unit_price must be a non-negative whole number of cents")
        object.__setattr__(self, "unit_price", price)


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    discount: Decimal
    net: Decimal
    tax_by_category: dict
    tax: Decimal
    total: Decimal


def line_total(item):
    return item.quantity * item.unit_price


def compute_totals(items, rates, discount_percent=0):
    items = list(items)
    if not items:
        raise ValueError("an invoice needs at least one line item")
    table = {category: parse_percent(rate) for category, rate in rates.items()}
    discount_rate = parse_percent(discount_percent)
    subtotal = ZERO
    net_by_category = {}
    for item in items:
        if item.category not in table:
            raise ValueError(f"no tax rate for category {item.category!r}")
        gross = line_total(item)
        subtotal += gross
        net = _cents(gross * (100 - discount_rate) / 100)
        net_by_category[item.category] = net_by_category.get(item.category, ZERO) + net
    tax_by_category = {c: _cents(n * table[c] / 100) for c, n in net_by_category.items()}
    net = sum(net_by_category.values(), ZERO)
    tax = sum(tax_by_category.values(), ZERO)
    return Totals(_cents(subtotal), _cents(subtotal - net), net, tax_by_category, tax, net + tax)
