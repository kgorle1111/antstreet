Create two Python modules, `models.py` and `render.py` (standard library only): `models.py` holds line items and the money rules, `render.py` turns an invoice into plain text using them. All money is `decimal.Decimal`, never `float`.

`models.py` provides:

    LineItem(description: str, quantity: int, unit_price, category: str = "standard")   # frozen dataclass
    Totals(subtotal, discount, net, tax_by_category, tax, total)                        # frozen dataclass
    line_total(item: LineItem) -> Decimal
    parse_percent(value) -> Decimal
    compute_totals(items: list[LineItem], rates: dict, discount_percent=0) -> Totals

`render.py` provides:

    render_invoice(number: str, customer: str, items: list[LineItem], rates: dict, discount_percent=0) -> str

Models:

1. `LineItem` is a frozen dataclass with the fields in the order above, so assigning to a field raises `dataclasses.FrozenInstanceError`. Construction validates and raises `ValueError` for: a `description` that is not a `str`, is empty, or contains a newline; a `quantity` that is not an `int` (`bool` and `float` are rejected) or is below 1; a `category` that is not a non-empty `str`; a `unit_price` that is not valid by rule 2. After construction `unit_price` is a `Decimal`.
2. `unit_price` may be given as a `str` such as `"2.50"`, an `int`, or a `Decimal`; a `float` or `bool` or anything else is a `ValueError`. It must be finite, not negative (zero is allowed) and a whole number of cents, meaning it equals itself rounded to 2 decimal places (`"1.500"` is fine, `"1.005"` is not). A `str` that is not a decimal numeral is a `ValueError`.
3. `line_total(item)` is `quantity * unit_price` as an exact `Decimal`.
4. `parse_percent(value)` converts a percentage given as `str`, `int` or `Decimal` to a `Decimal` and returns it. It raises `ValueError` for a `float`, a `bool`, any other type, text that is not a decimal numeral, `NaN` or infinity, a value below 0 or above 100. `0` and `100` are valid.
5. Tax and discount rules, in this order, are what `compute_totals(items, rates, discount_percent)` follows. `rates` maps a category name to a tax percentage (any of the types `parse_percent` takes). Every value in `rates` is validated with `parse_percent` even if no item uses it. `discount_percent` is validated the same way. An empty `items` list raises `ValueError`, and so does an item whose category is not a key of `rates`.
   a. Each item's gross is `line_total(item)`. `subtotal` is the sum of all gross amounts.
   b. The discount is applied to every item on its own: the item's net is `gross * (100 - discount_percent) / 100` rounded to cents (2 decimal places) with round half up (`decimal.ROUND_HALF_UP`).
   c. `net` is the sum of the item nets and `discount` is `subtotal - net`.
   d. Tax is worked out once per category, not per item: the nets of the items of a category are added up and the sum times the category's rate divided by 100 is rounded to cents, round half up. `tax_by_category` is a `dict` holding only the categories that occur in `items`, in the order each first appears, with that tax. `tax` is the sum of those amounts.
   e. `total` is `net + tax`.
   All `Totals` fields are `Decimal`s with 2 decimal places (`tax_by_category` holds `Decimal`s). `compute_totals` does not modify its arguments.

Rendering:

6. `render_invoice` returns text made of these lines, joined with `"\n"` and ending with one final `"\n"`. Money is printed with exactly 2 decimals and no thousands separators (`1234.50`). A percentage is printed in plain notation without trailing zeros (`8.5` for `"8.50"`, `10` for `10`, `0` for `"0.0"`).
   - `Invoice <number>`
   - `Customer: <customer>`
   - an empty line
   - `Description | Qty | Unit price | Amount`
   - one line per item in the given order: `<description> | <quantity> | <unit_price> | <line total>`
   - a line of exactly 40 hyphens
   - `Subtotal: <subtotal>`
   - only when `discount_percent` is greater than 0: `Discount (<percent>%): -<discount>`
   - one line per entry of `tax_by_category` in its order: `Tax (<category> <rate>%): <tax>`. A category with rate 0 still gets its line, with `0.00`.
   - `Total: <total>`
7. `number` and `customer` must each be a non-empty `str` without a newline, otherwise `ValueError`. Every `ValueError` from the money rules (invalid items, rates, discount, unknown category, empty items) propagates unchanged. The numbers printed are exactly those `compute_totals` returns for the same arguments.

Example: one item `LineItem("Widget", 2, "3.50")`, rates `{"standard": "8.50"}`, `discount_percent` `10`, number `INV-1`, customer `Acme`:

    Invoice INV-1
    Customer: Acme

    Description | Qty | Unit price | Amount
    Widget | 2 | 3.50 | 7.00
    ----------------------------------------
    Subtotal: 7.00
    Discount (10%): -0.70
    Tax (standard 8.5%): 0.54
    Total: 6.84
