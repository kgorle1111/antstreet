# ship and cancel do not check the order's status, so a shipped or cancelled order can be released
# or shipped again.
from items import InsufficientStock


class OrderError(Exception):
    pass


def _merge(lines):
    pairs = lines.items() if isinstance(lines, dict) else lines
    merged = {}
    for sku, qty in pairs:
        if not isinstance(sku, str) or not sku:
            raise ValueError("sku must be a non-empty str")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be an int of at least 1")
        merged[sku] = merged.get(sku, 0) + qty
    if not merged:
        raise ValueError("an order needs at least one line")
    return dict(sorted(merged.items()))


class OrderBook:
    def __init__(self, inventory):
        self._inventory = inventory
        self._orders = {}
        self._next_id = 1

    def _shortfalls(self, wanted):
        for sku in wanted:
            if sku not in self._inventory:
                raise KeyError(sku)
        return {
            sku: (qty, self._inventory.available(sku))
            for sku, qty in wanted.items()
            if qty > self._inventory.available(sku)
        }

    def check(self, lines):
        short = self._shortfalls(_merge(lines))
        return {sku: requested - available for sku, (requested, available) in short.items()}

    def place(self, lines):
        wanted = _merge(lines)
        short = self._shortfalls(wanted)
        if short:
            sku, (requested, available) = next(iter(short.items()))
            raise InsufficientStock(sku, requested, available)
        for sku, qty in wanted.items():
            self._inventory.reserve(sku, qty)
        order_id = self._next_id
        self._next_id += 1
        self._orders[order_id] = {"lines": list(wanted.items()), "status": "reserved"}
        return order_id

    def status(self, order_id):
        return self._orders[order_id]["status"]

    def lines(self, order_id):
        return list(self._orders[order_id]["lines"])

    def open_orders(self):
        return [i for i, order in self._orders.items() if order["status"] == "reserved"]

    def _reserved_order(self, order_id, action):
        order = self._orders[order_id]
        return order

    def ship(self, order_id):
        order = self._reserved_order(order_id, "ship")
        for sku, qty in order["lines"]:
            self._inventory.ship(sku, qty)
        order["status"] = "shipped"

    def cancel(self, order_id):
        order = self._reserved_order(order_id, "cancel")
        for sku, qty in order["lines"]:
            self._inventory.release(sku, qty)
        order["status"] = "cancelled"
