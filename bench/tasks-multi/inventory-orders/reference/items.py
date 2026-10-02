class InsufficientStock(Exception):
    def __init__(self, sku, requested, available):
        super().__init__(f"{sku}: {requested} requested, {available} available")
        self.sku = sku
        self.requested = requested
        self.available = available


def _check(sku, qty):
    if not isinstance(sku, str) or not sku:
        raise ValueError("sku must be a non-empty str")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
        raise ValueError("qty must be an int of at least 1")


class Inventory:
    def __init__(self):
        self._on_hand = {}
        self._reserved = {}

    def add_stock(self, sku, qty):
        _check(sku, qty)
        self._on_hand[sku] = self._on_hand.get(sku, 0) + qty
        self._reserved.setdefault(sku, 0)

    def on_hand(self, sku):
        return self._on_hand.get(sku, 0)

    def reserved(self, sku):
        return self._reserved.get(sku, 0)

    def available(self, sku):
        return self.on_hand(sku) - self.reserved(sku)

    def skus(self):
        return sorted(self._on_hand)

    def __contains__(self, sku):
        return sku in self._on_hand

    def reserve(self, sku, qty):
        _check(sku, qty)
        if sku not in self._on_hand:
            raise KeyError(sku)
        if qty > self.available(sku):
            raise InsufficientStock(sku, qty, self.available(sku))
        self._reserved[sku] += qty

    def release(self, sku, qty):
        _check(sku, qty)
        if sku not in self._on_hand:
            raise KeyError(sku)
        if qty > self._reserved[sku]:
            raise ValueError(f"{sku}: only {self._reserved[sku]} reserved, cannot release {qty}")
        self._reserved[sku] -= qty

    def ship(self, sku, qty):
        _check(sku, qty)
        if sku not in self._on_hand:
            raise KeyError(sku)
        if qty > self._reserved[sku]:
            raise ValueError(f"{sku}: only {self._reserved[sku]} reserved, cannot ship {qty}")
        self._reserved[sku] -= qty
        self._on_hand[sku] -= qty
