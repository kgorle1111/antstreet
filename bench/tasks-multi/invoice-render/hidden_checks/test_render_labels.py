from models import LineItem
from render import render_invoice

ITEMS = [LineItem("a", 1, "10.00")]


def lines(rates, discount=0):
    return render_invoice("N", "C", ITEMS, rates, discount).splitlines()


def test_no_discount_line_when_discount_is_zero():
    for zero in (0, "0", "0.00"):
        assert not any(line.startswith("Discount") for line in lines({"standard": "10"}, zero))


def test_discount_line_when_positive():
    assert "Discount (10%): -1.00" in lines({"standard": "0"}, 10)
    assert "Discount (12.5%): -1.25" in lines({"standard": "0"}, "12.50")
    assert "Discount (100%): -10.00" in lines({"standard": "0"}, 100)
    assert "Discount (0.5%): -0.05" in lines({"standard": "0"}, "0.5")


def test_discount_line_sits_between_subtotal_and_tax():
    out = lines({"standard": "10"}, 10)
    sub = out.index("Subtotal: 10.00")
    assert out[sub + 1] == "Discount (10%): -1.00"
    assert out[sub + 2] == "Tax (standard 10%): 0.90"
    assert out[sub + 3] == "Total: 9.90"


def test_rate_is_printed_without_trailing_zeros():
    assert "Tax (standard 8.5%): 0.85" in lines({"standard": "8.50"})
    assert "Tax (standard 10%): 1.00" in lines({"standard": "10.00"})
    assert "Tax (standard 10%): 1.00" in lines({"standard": 10})
    assert "Tax (standard 7.25%): 0.73" in lines({"standard": "7.2500"})
    assert "Tax (standard 100%): 10.00" in lines({"standard": "100"})


def test_zero_rate_still_gets_a_line():
    assert "Tax (standard 0%): 0.00" in lines({"standard": "0"})
    assert "Tax (standard 0%): 0.00" in lines({"standard": "0.0"})
    assert "Tax (standard 0%): 0.00" in lines({"standard": 0})


def test_only_used_categories_are_listed():
    out = lines({"standard": "10", "food": "5", "books": "0"})
    assert [line for line in out if line.startswith("Tax")] == ["Tax (standard 10%): 1.00"]


def test_full_discount_prints_zero_amounts():
    out = lines({"standard": "10"}, 100)
    assert "Discount (100%): -10.00" in out
    assert "Tax (standard 10%): 0.00" in out
    assert out[-1] == "Total: 0.00"
