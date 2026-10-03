Create a Python module `multisort.py` (standard library only) with one function:

    sort_records(records: list[dict], keys: list[str]) -> list[dict]

`records` is a list of dicts and `keys` is a list of key specs. The function returns a new list.

1. A key spec names a field: `"age"` sorts ascending (smallest first) on the field `age`, and
   `"-age"` sorts descending (largest first). A spec is an optional single leading `-` followed by
   the field name, which must not be empty, so `"--x"` is descending on the field `-x`. Values of a
   field are compared with Python's `<` and are all numbers, or all strings (a field is never a
   mixture of kinds).
2. Records are ordered by the first key. Records that are equal on the first key are ordered by the
   second key, and so on, so earlier keys matter more. `sort_records(rows, ["dept", "-salary"])`
   puts departments in ascending order and, inside a department, the highest salary first.
3. A record is missing a field when the key is absent or its value is `None`. For every key, in
   ascending and in descending order alike, records that are missing the field come after all the
   records that have it. Records that are both missing the field are equal on that key.
4. The sort is stable: records that are equal on every key keep their relative order from the input
   list. This holds for descending keys too, so `sort_records([{"k": 1, "n": "a"},
   {"k": 1, "n": "b"}], ["-k"])` keeps `a` before `b`.
5. With no keys the result has the records in their input order. With no records the result is an
   empty list.
6. The result is a new list holding the same dict objects (not copies). The input list and the
   dicts in it are not changed.
7. A `records` or `keys` argument that is not a list or tuple, a record that is not a dict (checked
   even when the keys are empty) and a key spec that is not a `str` raise `TypeError`. A key spec
   with no field name (`""` or `"-"`) raises `ValueError`. Key specs are validated before any
   record is looked at.
