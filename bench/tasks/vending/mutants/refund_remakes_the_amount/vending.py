# Refund pays the credit back as the fewest largest coins instead of the coins inserted.
ACCEPTED = (100, 25, 10, 5)  # largest first, the order change is made in
MAX_CREDIT = 500


class VendingError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _whole(n: object) -> bool:
    return type(n) is int


class VendingMachine:
    def __init__(
        self,
        prices: dict[str, int],
        stock: dict[str, int],
        change: dict[int, int] | None = None,
    ) -> None:
        for name, price in prices.items():
            if not _whole(price) or price <= 0:
                raise ValueError(f"price of {name!r} must be a whole number above 0")
        for name, count in stock.items():
            if name not in prices:
                raise ValueError(f"stock for unknown item {name!r}")
            if not _whole(count) or count < 0:
                raise ValueError(f"stock of {name!r} must be a whole number of at least 0")
        float_coins = {coin: 0 for coin in ACCEPTED}
        for coin, count in (change or {}).items():
            if coin not in float_coins:
                raise ValueError(f"cannot hold coin {coin!r}")
            if not _whole(count) or count < 0:
                raise ValueError(f"float count of {coin} must be a whole number of at least 0")
            float_coins[coin] = count
        self._prices = dict(prices)
        self._stock = {name: stock.get(name, 0) for name in prices}
        self._float = float_coins
        self._inserted: list[int] = []

    @property
    def credit(self) -> int:
        return sum(self._inserted)

    def insert(self, coin: int) -> None:
        if coin not in ACCEPTED:
            raise ValueError(f"coin {coin!r} is not accepted")
        if self.credit + coin > MAX_CREDIT:
            raise VendingError("credit_limit")
        self._inserted.append(coin)

    def select(self, item: str) -> tuple[str, list[int]]:
        if item not in self._prices:
            raise VendingError("unknown_item")
        if self._stock[item] == 0:
            raise VendingError("sold_out")
        owed = self.credit - self._prices[item]
        if owed < 0:
            raise VendingError("insufficient_credit")
        pool = dict(self._float)
        for coin in self._inserted:
            pool[coin] += 1
        given: list[int] = []
        for coin in ACCEPTED:
            while owed >= coin and pool[coin] > 0:
                owed -= coin
                pool[coin] -= 1
                given.append(coin)
        if owed:
            raise VendingError("no_change")
        self._float = pool
        self._stock[item] -= 1
        self._inserted = []
        return item, given

    def refund(self) -> list[int]:
        owed = self.credit
        returned = []
        for coin in ACCEPTED:
            while owed >= coin:
                owed -= coin
                returned.append(coin)
        self._inserted = []
        return returned

    def remaining(self, item: str) -> int:
        return self._stock[item]

    def coins(self) -> dict[int, int]:
        return dict(self._float)
