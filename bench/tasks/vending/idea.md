Create a Python module `vending.py` (standard library only) with an exception and one class:

    class VendingError(Exception)          # has a str attribute `reason`; str(error) == reason

    VendingMachine(prices: dict[str, int], stock: dict[str, int], change: dict[int, int] | None = None)

    insert(coin: int) -> None
    credit -> int                          # property
    select(item: str) -> tuple[str, list[int]]
    refund() -> list[int]
    remaining(item: str) -> int
    coins() -> dict[int, int]

It is a coin-operated vending machine. All money is whole cents. The machine accepts exactly the
coins 5, 10, 25 and 100.

1. `prices` maps each item name to its price, a whole number of cents greater than 0. `stock` maps
   item names to how many units are loaded, a whole number of at least 0; an item in `prices` but
   not in `stock` has 0 units. `change` maps coin values to how many of that coin the machine
   holds as its float; it defaults to no coins. The constructor raises `ValueError` for a price
   that is not a whole number greater than 0, a stock count or float count that is not a whole
   number of at least 0, an item in `stock` that is not in `prices`, or a float coin value that is
   not one of 5, 10, 25 and 100. The constructor copies its arguments.
2. `insert(coin)` adds the coin to the current credit. A coin that is not accepted raises
   `ValueError` and changes nothing. The credit is at most 500: a coin that would take it above
   500 raises `VendingError` with reason `"credit_limit"`, is not taken, and changes nothing.
   `credit` is the sum of the coins inserted since the last sale or refund; it is 0 at the start.
3. `select(item)` tries to sell one unit of `item`. It checks these in this order and raises
   `VendingError` with the reason for the first that applies: `"unknown_item"` (not in `prices`),
   `"sold_out"` (no units left), `"insufficient_credit"` (credit below the price), `"no_change"`
   (see 4). A failed `select` changes nothing: the credit, the stock and the float are as before.
4. Change is `credit - price`. It is made from the machine's float together with the coins
   inserted since the last sale, greedily: repeatedly take the largest coin value that is at most
   the amount still owed and of which a coin is still available, until the amount is 0. If the
   amount cannot be brought to exactly 0 that way, the sale fails with `"no_change"`, even if
   some other combination of coins would have worked.
5. A successful `select` returns `(item, change)` where `change` is the list of change coins in
   the order they were taken (largest first; empty for exact money). It lowers the item's stock by 1,
   adds every coin inserted since the last sale to the float, removes the change coins from the
   float, and sets the credit to 0.
6. `refund()` returns the coins inserted since the last sale or refund, largest first, and sets
   the credit to 0. They are the same coins that were put in: they never touched the float. With
   nothing inserted it returns `[]`.
7. `remaining(item)` returns the units left of an item and raises `KeyError` for an item not in
   `prices`. `coins()` returns a new dict with one entry for each of 5, 10, 25 and 100, giving the
   number of that coin in the float (0 included); it does not count coins of the current credit.
