from models import LineItem
from render import render_invoice

EXAMPLE = """Invoice INV-1
Customer: Acme

Description | Qty | Unit price | Amount
Widget | 2 | 3.50 | 7.00
----------------------------------------
Subtotal: 7.00
Discount (10%): -0.70
Tax (standard 8.5%): 0.54
Total: 6.84
"""


def test_example_from_the_idea_exactly():
    items = [LineItem("Widget", 2, "3.50")]
    text = render_invoice("INV-1", "Acme", items, {"standard": "8.50"}, 10)
    assert text == EXAMPLE


def test_two_categories_without_discount():
    items = [
        LineItem("Milk", 2, "1.20", "food"),
        LineItem("Lamp", 1, "40", "standard"),
        LineItem("Bread", 1, "2.5", "food"),
    ]
    text = render_invoice("2026-0042", "Jo Bloggs", items, {"standard": "20", "food": "5"})
    assert text == (
        "Invoice 2026-0042\n"
        "Customer: Jo Bloggs\n"
        "\n"
        "Description | Qty | Unit price | Amount\n"
        "Milk | 2 | 1.20 | 2.40\n"
        "Lamp | 1 | 40.00 | 40.00\n"
        "Bread | 1 | 2.50 | 2.50\n"
        "----------------------------------------\n"
        "Subtotal: 44.90\n"
        "Tax (food 5%): 0.25\n"
        "Tax (standard 20%): 8.00\n"
        "Total: 53.15\n"
    )


def test_item_order_is_input_order_and_tax_order_is_first_appearance():
    items = [
        LineItem("b", 1, "1.00", "z"),
        LineItem("a", 1, "1.00", "y"),
        LineItem("c", 1, "1.00", "z"),
    ]
    lines = render_invoice("N", "C", items, {"y": "10", "z": "10"}).splitlines()
    assert lines[4:7] == ["b | 1 | 1.00 | 1.00", "a | 1 | 1.00 | 1.00", "c | 1 | 1.00 | 1.00"]
    assert lines[9:11] == ["Tax (z 10%): 0.20", "Tax (y 10%): 0.10"]


def test_ends_with_exactly_one_newline_and_rule_is_forty_hyphens():
    text = render_invoice("N", "C", [LineItem("a", 1, "1.00")], {"standard": "0"})
    assert text.endswith("Total: 1.00\n") and not text.endswith("\n\n")
    assert "\n" + "-" * 40 + "\n" in text
    assert "-" * 41 not in text


def test_large_amounts_have_no_thousands_separator():
    text = render_invoice("N", "C", [LineItem("rig", 3, "1234.50")], {"standard": "10"})
    assert "rig | 3 | 1234.50 | 3703.50" in text.splitlines()
    assert "Subtotal: 3703.50" in text.splitlines()
    assert "Tax (standard 10%): 370.35" in text.splitlines()
    assert "Total: 4073.85" in text.splitlines()
