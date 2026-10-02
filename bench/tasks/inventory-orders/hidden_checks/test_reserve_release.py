import pytest
from items import InsufficientStock, Inventory


def stocked():
    inv = Inventory()
    inv.add_stock("a", 10)
    inv.add_stock("b", 3)
    return inv


def test_reserve_moves_units_from_available_to_reserved():
    inv = stocked()
    inv.reserve("a", 4)
    assert inv.reserved("a") == 4
    assert inv.available("a") == 6
    assert inv.on_hand("a") == 10
    inv.reserve("a", 6)
    assert inv.available("a") == 0
    assert inv.reserved("a") == 10


def test_reserve_more_than_available_raises_with_details_and_changes_nothing():
    inv = stocked()
    inv.reserve("a", 7)
    with pytest.raises(InsufficientStock) as info:
        inv.reserve("a", 4)
    error = info.value
    assert (error.sku, error.requested, error.available) == ("a", 4, 3)
    assert inv.reserved("a") == 7 and inv.available("a") == 3


def test_reserve_exactly_the_available_amount_works():
    inv = stocked()
    inv.reserve("b", 3)
    assert inv.available("b") == 0
    with pytest.raises(InsufficientStock) as info:
        inv.reserve("b", 1)
    assert info.value.available == 0


def test_insufficient_stock_is_an_exception_but_not_a_value_error_or_key_error():
    assert issubclass(InsufficientStock, Exception)
    assert not issubclass(InsufficientStock, (ValueError, KeyError))


def test_reserve_unknown_sku_is_a_key_error():
    with pytest.raises(KeyError):
        stocked().reserve("zzz", 1)


def test_release_gives_units_back():
    inv = stocked()
    inv.reserve("a", 8)
    inv.release("a", 3)
    assert inv.reserved("a") == 5
    assert inv.available("a") == 5
    assert inv.on_hand("a") == 10
    inv.release("a", 5)
    assert inv.reserved("a") == 0


def test_release_more_than_reserved_is_a_value_error_and_changes_nothing():
    inv = stocked()
    inv.reserve("a", 2)
    with pytest.raises(ValueError):
        inv.release("a", 3)
    assert inv.reserved("a") == 2
    with pytest.raises(ValueError):
        inv.release("b", 1)


def test_release_unknown_sku_is_a_key_error():
    with pytest.raises(KeyError):
        stocked().release("zzz", 1)


def test_reservations_are_per_sku():
    inv = stocked()
    inv.reserve("a", 10)
    assert inv.available("b") == 3
    inv.reserve("b", 1)
    assert inv.available("a") == 0 and inv.available("b") == 2


def test_add_stock_after_reserving_raises_available_only():
    inv = stocked()
    inv.reserve("b", 3)
    inv.add_stock("b", 2)
    assert (inv.on_hand("b"), inv.reserved("b"), inv.available("b")) == (5, 3, 2)
    inv.reserve("b", 2)
    assert inv.available("b") == 0
