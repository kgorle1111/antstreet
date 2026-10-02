Create two Python modules (standard library only) for a small warehouse: `items.py` tracks stock per SKU and reserves it, and `orders.py` places orders that reserve stock for several SKUs at once, all or nothing. `orders.py` uses `items.py` only through the public names below.

`items.py` provides:

    InsufficientStock(Exception)        # attributes: sku, requested, available
    Inventory()
    add_stock(sku: str, qty: int) -> None
    on_hand(sku: str) -> int
    reserved(sku: str) -> int
    available(sku: str) -> int
    skus() -> list[str]
    sku in inventory -> bool
    reserve(sku: str, qty: int) -> None
    release(sku: str, qty: int) -> None
    ship(sku: str, qty: int) -> None

`orders.py` provides:

    OrderError(Exception)
    OrderBook(inventory: Inventory)
    check(lines) -> dict[str, int]
    place(lines) -> int
    status(order_id: int) -> str
    lines(order_id: int) -> list[tuple[str, int]]
    open_orders() -> list[int]
    ship(order_id: int) -> None
    cancel(order_id: int) -> None

Inventory:

1. A SKU is a non-empty `str`; a quantity is an `int` of at least 1 (a `bool` is rejected). Every method that takes them raises `ValueError` for an invalid SKU or quantity, before anything else is checked.
2. `add_stock(sku, qty)` adds `qty` units to the SKU's `on_hand`, creating the SKU (with nothing reserved) if it is new. `on_hand(sku)` is the number of units physically in stock, `reserved(sku)` the number promised to orders, and `available(sku)` is `on_hand - reserved`. All three return `0` for a SKU that was never added, and never create it. `skus()` is a new sorted list of the SKUs that were added; `sku in inventory` says whether a SKU was added.
3. `reserve(sku, qty)` raises `KeyError` for a SKU that was never added. If `qty` is more than `available(sku)` it raises `InsufficientStock` whose attributes `sku`, `requested` and `available` are the SKU, `qty` and the available count, and changes nothing. Otherwise `reserved(sku)` goes up by `qty`; `on_hand` does not change.
4. `release(sku, qty)` raises `KeyError` for an unknown SKU and `ValueError` if `qty` is more than `reserved(sku)`; otherwise `reserved(sku)` goes down by `qty`.
5. `ship(sku, qty)` raises `KeyError` for an unknown SKU and `ValueError` if `qty` is more than `reserved(sku)`; otherwise both `reserved(sku)` and `on_hand(sku)` go down by `qty` (the units leave the building). A failed call changes nothing.

Orders:

6. `lines` arguments (of `check` and `place`) are either a `dict` mapping SKU to quantity or any iterable of `(sku, qty)` pairs. The same SKU may appear several times in the iterable form, and the quantities are added up. Invalid SKUs or quantities (rule 1), or no lines at all, raise `ValueError`. After merging, the SKUs are handled in ascending order.
7. `check(lines)` changes nothing and returns a dict from SKU to shortfall (`requested - available`) for each SKU whose merged quantity is more than `available`, keys in ascending order; an order that can be filled gives `{}`. It raises `KeyError` for the first SKU, in ascending order, that the inventory does not know.
8. `place(lines)` reserves the stock for every line, or for none. It raises `ValueError` as in rule 6, then `KeyError` for the first unknown SKU in ascending order, then `InsufficientStock` for the first SKU in ascending order whose merged quantity is more than `available` (with that SKU's `sku`, `requested` (the merged quantity) and `available`). When it raises, the inventory is exactly as before and no order id is used up. When it succeeds it reserves the merged quantity of each SKU, creates the order with status `"reserved"` and returns the order id. Ids are 1, 2, 3, ... in the order of successful placements.
9. `status(order_id)` is `"reserved"`, `"shipped"` or `"cancelled"`, and `KeyError` for an id that was never issued. `lines(order_id)` is a new list of the order's `(sku, qty)` pairs after merging, in ascending SKU order (`KeyError` for an unknown id). `open_orders()` is a new list of the ids of the orders with status `"reserved"`, ascending.
10. `ship(order_id)` is only allowed for a reserved order: it calls `Inventory.ship` for each line and sets the status to `"shipped"`. `cancel(order_id)` is only allowed for a reserved order: it releases each line's reservation and sets the status to `"cancelled"`. For an order in any other status they raise `OrderError` and change nothing; for an unknown id they raise `KeyError`.
