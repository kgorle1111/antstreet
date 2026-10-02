Create a Python module `moneysplit.py` (standard library only) with two functions:

    split_even(total: int, parts: int) -> list[int]
    split_by_ratio(total: int, ratios: Iterable[int]) -> list[int]

Both divide an amount of money, given as a whole number of cents, into shares that are whole
numbers of cents and add up to exactly `total`. No cent is created or lost.

1. `split_by_ratio` gives share `i` the exact proportion `total * ratios[i] / sum(ratios)`, rounded
   down to whole cents, and then hands out the cents that are left over (the total minus the sum of
   the rounded-down shares) one cent at a time. The shares with the largest fractional part of the
   exact proportion get the extra cents first, one cent each; if two shares have exactly equal
   fractional parts, the one earlier in the list goes first. So splitting 100 by `[1, 1, 1]` is
   `[34, 33, 33]` and splitting 10 by `[1, 2]` is `[3, 7]`, because the exact shares are 3.33 and
   6.67 and the one left-over cent goes to the 6.67.
2. The result has one share per ratio, in the same order as `ratios`. A ratio of 0 always gets 0.
   Scaling every ratio by the same factor changes nothing: `[2, 4]` splits like `[1, 2]`. `ratios`
   may be any iterable of ints, such as a list, a tuple or a generator that can be read only once.
3. `split_even(total, parts)` is `split_by_ratio(total, [1] * parts)`: the first `total % parts`
   shares are one cent larger than the rest, so 10 split in 3 is `[4, 3, 3]`.
4. `total` may be zero or negative. A negative total is split as its absolute value and every
   share is then negated: -100 split by `[1, 1, 1]` is `[-34, -33, -33]`. Zero gives all zeros.
5. All the arithmetic is exact integer arithmetic, so it stays correct for amounts far beyond the
   range of a float: 10**20 split by `[1, 2]` is `[33333333333333333333, 66666666666666666667]`.
6. A `total`, `parts` or ratio that is not an `int` raises `TypeError`; a `bool` is not accepted as
   an int. A `ratios` argument that is not iterable raises `TypeError` too.
7. Values that are ints but unusable raise `ValueError`: `parts` below 1, an empty `ratios`, a
   negative ratio, and ratios that add up to zero (for example `[0, 0]`).
