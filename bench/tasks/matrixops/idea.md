Create a Python module `matrixops.py` (standard library only) with three functions:

    spiral(matrix: list[list]) -> list
    rotate(matrix: list[list], turns: int = 1) -> list[list]
    transpose(matrix: list[list]) -> list[list]

A matrix is a list of rows and each row is a list. All rows of a valid matrix have the same length,
but the matrix need not be square (3 rows of 4 elements, a single row, a single column and so on are
all valid).

1. `spiral` returns a flat list of every element in clockwise spiral order: start at the top-left
   element, go right along the top row, down the last column, left along the bottom row and up the
   first column, then continue the same way around the remaining inner elements until each element
   has been visited exactly once. `spiral([[1, 2, 3], [4, 5, 6], [7, 8, 9]])` is
   `[1, 2, 3, 6, 9, 8, 7, 4, 5]`, and `spiral([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]])` is
   `[1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7]`.
2. `rotate` returns a new matrix turned clockwise by 90 degrees, `turns` times. One turn of a matrix
   with R rows and C columns gives a matrix with C rows and R columns: the first column, read from
   bottom to top, becomes the first row. `rotate([[1, 2, 3], [4, 5, 6]])` is
   `[[4, 1], [5, 2], [6, 3]]`.
3. `turns` may be any integer. A negative value turns counter-clockwise. Only `turns` modulo 4
   matters, so 0, 4, 8 and -4 all return an unrotated copy, 5 is the same as 1 and -1 is the same
   as 3. Very large values such as 10**18 + 3 must work without looping that many times.
4. `transpose` returns a new matrix in which the element at row i, column j of the input is at row j,
   column i. `transpose([[1, 2, 3], [4, 5, 6]])` is `[[1, 4], [2, 5], [3, 6]]`.
5. A matrix with no rows (`[]`) gives `[]` from all three functions, for every value of `turns`. So
   does a matrix that has one or more rows where every row is empty (`[[]]`, `[[], []]`, ...).
6. If the rows do not all have the same length, all three functions raise `ValueError`. This holds
   for every value of `turns` (including 0 and multiples of 4), for any row being the odd one out
   (first, middle or last), and when some rows are empty and others are not (`[[], [1]]`).
7. Inputs are never mutated: after a call, the matrix and each of its rows are exactly as before.
8. Results never share structure with the input. The returned list is always a new list object. For
   `rotate` and `transpose` every returned row is a new list object too, even when `turns` is 0, and
   no returned row is the same object as an input row or as another returned row. For `spiral`, the
   returned list is never one of the input rows. Mutating a result never changes the input.
9. Elements can be any Python objects (numbers, strings, `None`, `0`, `""`, other lists, several
   equal elements). They are only moved: the returned matrices hold the very same element objects,
   never copies, and equal or falsy elements are treated like any other.
