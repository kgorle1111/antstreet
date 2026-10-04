Create a Python module `debounce.py` (standard library only) with two classes:

    Debouncer(wait: float, max_wait: float | None = None)

        call(now: float, value=None) -> None
        poll(now: float) -> list
        pending() -> bool
        cancel() -> None

    Throttler(interval: float, trailing: bool = True)

        call(now: float, value=None) -> list
        poll(now: float) -> list
        pending() -> bool

They are the two classic ways to tame a burst of events. Neither one uses a timer, a clock or
threads: `now` is the time in seconds, given by the caller on every call, and does not go
backwards between calls. Whatever should run is handed back to the caller as a list holding the
value to act on (a list, because `None` is a valid value): `[value]` or `[]`.

Debouncer: run once after the calls have stopped.

1. `wait` must be greater than 0, and `max_wait`, if given, at least `wait`; otherwise the
   constructor raises `ValueError`.
2. `call(now, value)` records a call. While no call is waiting, it starts a burst whose start time
   is `now`. Every call sets the time of the latest call to `now` and replaces the waiting value
   with `value` (the latest value wins). `pending()` is `True` while a call is waiting.
3. `poll(now)` returns `[value]`, the latest value, and clears the waiting call when a call is waiting
   and either `now - time_of_latest_call >= wait` (exactly `wait` is enough) or `max_wait` is
   given and `now - burst_start >= max_wait`. Otherwise, and when nothing is waiting, it returns `[]`
   and changes nothing. A call after a poll that returned a value starts a new burst.
4. `cancel()` throws away the waiting call without running it. With nothing waiting it does
   nothing. The call that follows starts a new burst.

Throttler: run at most once per `interval`, the first call at once.

5. `interval` must be greater than 0, otherwise the constructor raises `ValueError`.
6. `call(now, value)` runs at once when nothing has run before, or when `now - time_of_last_run >=
   interval` (exactly `interval` is enough): it returns `[value]`, sets the time of the last run
   to `now`, and discards any trailing value that was waiting. Otherwise, with `trailing=True` it
   keeps `value` as the waiting value, replacing any earlier waiting one, and returns `[]`; with
   `trailing=False` it drops the call and returns `[]`.
7. `poll(now)` returns `[value]` for the waiting value and clears it when there is one and
   `now - time_of_last_run >= interval`; the time of the last run then becomes this `now`. Otherwise it
   returns `[]`. `pending()` is `True` while a trailing value is waiting; it is never `True`
   with `trailing=False`.
