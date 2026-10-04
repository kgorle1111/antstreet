Create a Python module `knapsack.py` (standard library only) with one function:

    knapsack(items: list[tuple[int, int]], capacity: int) -> tuple[int, list[int]]

1. `items` is a list (or tuple) of `(weight, value)` pairs, and `capacity` is the weight the bag can
   hold. Weights are ints of at least 1, values are ints of at least 0 and the capacity is an int
   of at least 0. Each item can be taken once or left. A choice of items fits when the sum of
   their weights is at most `capacity` (equal is allowed). An item that is heavier than the
   capacity is allowed in the list and is never taken.
2. The function returns `(best_value, chosen)`: the largest total value of any choice that fits, and
   the positions in `items` of the items taken, in ascending order. Taking nothing gives
   `(0, [])`.
3. Several choices can reach the best value. Pick among them by two rules, in this order: first the
   one with the smallest total weight; if several are still tied, the one whose list of positions
   is smallest when compared as Python lists, so the first position where two lists differ decides
   and the lower position wins (`[0, 3]` beats `[1, 2]`, and `[0, 2]` beats `[0, 3]`). Examples:
   - `knapsack([(5, 10), (4, 40), (6, 30), (3, 50)], 10)` is `(90, [1, 3])`.
   - `knapsack([(2, 3), (3, 3)], 3)` is `(3, [0])` and `knapsack([(3, 3), (2, 3)], 3)` is
     `(3, [1])`: the same value, so the lighter choice wins.
   - `knapsack([(1, 1), (1, 1), (2, 2)], 2)` is `(2, [0, 1])`: `{0, 1}` and `{2}` have the same
     value and the same weight, and `[0, 1]` is smaller than `[2]`.
   - `knapsack([(2, 2), (1, 1), (1, 1)], 2)` is `(2, [0])`.
   - An item worth 0 is never taken, because leaving it gives a smaller weight.
4. `items` that is not a list or tuple, a weight, value or capacity that is not an int (a `bool` is
   not one) raise `TypeError`. An item that is not a list or tuple of exactly two values, a weight
   below 1, a value below 0 and a capacity below 0 raise `ValueError`. Everything is checked
   before any solving, including items that could never be taken.
5. The input is not changed. About 200 items with a capacity of 5,000 must be handled in a few
   seconds.
