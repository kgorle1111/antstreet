Create a Python module `ledger.py` (standard library only) with an exception and one class:

    class InsufficientFunds(Exception)

    Ledger()

    open_account(name: str, overdraft: int = 0) -> None
    balance(name: str) -> int
    deposit(name: str, amount: int, txn_id: str) -> int
    withdraw(name: str, amount: int, txn_id: str) -> int
    transfer(source: str, dest: str, amount: int, txn_id: str) -> int
    statement(name: str) -> list[tuple[str, int]]

It is an in-memory bank ledger. Money is a whole number of cents (an `int`); balances may be
negative.

1. `open_account(name, overdraft=0)` creates an account with balance 0. `name` must be a
   non-empty `str` and `overdraft` a whole number of at least 0, the amount the account may be
   overdrawn by; otherwise `ValueError`. Opening a name that already exists raises `ValueError`
   and changes nothing. `balance(name)` returns the account's balance; `KeyError` for an account
   that does not exist (every method that takes an account name raises `KeyError` that way).
2. `amount` must be a whole number greater than 0 and `txn_id` a non-empty `str`; otherwise
   `ValueError`. `transfer` also raises `ValueError` when `source` and `dest` are the same account.
3. `deposit` adds `amount` to the account and returns its new balance. `withdraw` subtracts it and
   returns the new balance. `transfer` moves `amount` from `source` to `dest` and returns the new
   balance of `source`.
4. A withdrawal or transfer may not take the paying account's balance below `-overdraft`: balance
   exactly `-overdraft` is allowed, one cent less is not. When it would, `InsufficientFunds` is
   raised and nothing changes. A transfer happens entirely or not at all. A deposit is never refused
   for funds, even into an overdrawn account.
5. `txn_id` makes an operation idempotent. It identifies one operation for the whole ledger,
   whatever the kind or accounts. After an operation has succeeded, calling again with the same
   `txn_id` and the same operation (the same method, the same account names and the same
   `amount`) does nothing and returns exactly the value the first call returned, even if the
   balance has changed since or the funds would no longer be there. Calling with a used `txn_id`
   and anything different (another method, account or amount) raises `ValueError` and changes
   nothing. An operation that raised `InsufficientFunds` did not succeed: its `txn_id` is not used up
   and may be used again, for the same operation or any other.
6. A call is checked in this order, and the first problem found is the one raised: malformed
   arguments (item 2) with `ValueError`, then an account that does not exist with `KeyError`, then a
   used `txn_id` (replay or `ValueError`), then funds with `InsufficientFunds`.
7. `statement(name)` returns a new list of `(txn_id, delta)` pairs, one for each operation that
   succeeded on the account, in the order they happened. `delta` is the signed change to its balance:
   `+amount` for a deposit or for the receiving side of a transfer, `-amount` for a withdrawal or the
   paying side of a transfer. A replay adds nothing, and neither does a refused call. A new account
   has an empty statement.
