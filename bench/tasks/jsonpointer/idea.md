Create a Python module `jsonpointer.py` (standard library only) implementing RFC 6901 JSON Pointers over documents made of nested dicts and lists, with two functions:

    resolve(document: Any, pointer: str) -> Any
    set_value(document: Any, pointer: str, value: Any) -> Any

A dict or a list is a container. Every other value (str, int, float, bool, None) is a leaf and cannot be descended into. Dict keys are strings.

Pointer syntax:

1. The empty pointer `""` refers to the whole document. Any other pointer must start with `/`, otherwise `ValueError` is raised.
2. Everything after the first `/` is split on `/` into tokens. So `"/"` has one token, the empty string, and `"//"` has two empty tokens.
3. Inside a token, `~1` stands for `/` and `~0` stands for `~`. Decode `~1` first, then `~0`, so the token `~01` means the text `~1`. Any other use of `~`, including a `~` at the end of a token, makes the pointer invalid and raises `ValueError`.
4. The whole pointer is checked (rules 1 to 3) before the document is looked at. A malformed pointer raises `ValueError` even if an earlier token would have raised `KeyError`, and even when the pointer is used with `set_value`.

Following a token from a container (used by both functions):

5. From a dict, the decoded token is looked up as an exact key. This includes tokens such as `"0"`, `"-"` and `""`, which are ordinary keys on a dict. A key that is not present raises `KeyError`. A key whose value is `None` is present.
6. From a list, the token must be `0` or a digit 1-9 followed by any number of ASCII digits 0-9. Signs, spaces, underscores, decimal points, leading zeros (`01`) and non-ASCII digits are not indexes. The index must be less than the length of the list. A token that is not a valid index, an index that is out of range, and the token `-` all raise `KeyError`: the pointer is well formed but names no element of this document.
7. Following any token from a leaf raises `KeyError`, including an index token from a string.

`resolve(document, pointer)`:

8. Follows the tokens from the document and returns the value found. It returns the object itself, not a copy. The empty pointer returns `document`.

`set_value(document, pointer, value)`:

9. Returns a new document and never modifies `document`. The new document shares no dict or list with `document`, so changing the result later cannot change the input.
10. The empty pointer returns `value`.
11. Otherwise all tokens except the last are followed with rules 5 to 7, so the parent of the target must already exist. The last token is then applied to that parent:
    - Parent is a dict: the key is set to `value`, replacing an existing key or adding a new one. The token `-` is an ordinary key here.
    - Parent is a list: an in-range index replaces that element, and the token `-` appends `value` to the end. Nothing is ever inserted in the middle. An index equal to or above the length raises `KeyError`, and any other token raises `KeyError`.
    - Parent is a leaf: `KeyError`.
12. The token `-` before the last position never resolves on a list (rule 6).
