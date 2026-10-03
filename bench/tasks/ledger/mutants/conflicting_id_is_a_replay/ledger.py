# A used id with a different operation is treated as a replay instead of raising ValueError.
class InsufficientFunds(Exception):
    pass


def _check(amount: object, txn_id: object) -> None:
    if type(amount) is not int or amount <= 0:
        raise ValueError("amount must be a whole number of cents above 0")
    if type(txn_id) is not str or not txn_id:
        raise ValueError("txn_id must be a non-empty string")


class Ledger:
    def __init__(self) -> None:
        self._balance: dict[str, int] = {}
        self._overdraft: dict[str, int] = {}
        self._history: dict[str, list[tuple[str, int]]] = {}
        # txn_id -> (what was asked, what was returned); only successes are kept
        self._done: dict[str, tuple[tuple[object, ...], int]] = {}

    def open_account(self, name: str, overdraft: int = 0) -> None:
        if type(name) is not str or not name:
            raise ValueError("name must be a non-empty string")
        if type(overdraft) is not int or overdraft < 0:
            raise ValueError("overdraft must be a whole number of at least 0")
        if name in self._balance:
            raise ValueError(f"account {name!r} already exists")
        self._balance[name] = 0
        self._overdraft[name] = overdraft
        self._history[name] = []

    def balance(self, name: str) -> int:
        return self._balance[name]

    def statement(self, name: str) -> list[tuple[str, int]]:
        return list(self._history[name])

    def _post(self, txn_id: str, asked: tuple[object, ...], deltas: list[tuple[str, int]]) -> int:
        """Apply (account, delta) pairs; the first pair's account is the one whose balance is
        returned."""
        for name, _ in deltas:
            if name not in self._balance:
                raise KeyError(name)
        if txn_id in self._done:
            seen, result = self._done[txn_id]
            return result
        for name, delta in deltas:
            if self._balance[name] + delta < -self._overdraft[name]:
                raise InsufficientFunds(name)
        for name, delta in deltas:
            self._balance[name] += delta
            self._history[name].append((txn_id, delta))
        result = self._balance[deltas[0][0]]
        self._done[txn_id] = (asked, result)
        return result

    def deposit(self, name: str, amount: int, txn_id: str) -> int:
        _check(amount, txn_id)
        return self._post(txn_id, ("deposit", name, amount), [(name, amount)])

    def withdraw(self, name: str, amount: int, txn_id: str) -> int:
        _check(amount, txn_id)
        return self._post(txn_id, ("withdraw", name, amount), [(name, -amount)])

    def transfer(self, source: str, dest: str, amount: int, txn_id: str) -> int:
        _check(amount, txn_id)
        if source == dest:
            raise ValueError("cannot transfer to the same account")
        asked = ("transfer", source, dest, amount)
        return self._post(txn_id, asked, [(source, -amount), (dest, amount)])
