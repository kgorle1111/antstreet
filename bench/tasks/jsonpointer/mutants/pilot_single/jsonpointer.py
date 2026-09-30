# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: escapes, invalid_pointers, list_indexes, resolve_basic, set_value_errors.
from typing import Any


def resolve(document: Any, pointer: str) -> Any:
    """Resolve a JSON pointer in a document.

    Returns the value found at the pointer location.
    Follows RFC 6901 JSON Pointer specification.
    """
    if pointer == "":
        return document

    if not pointer.startswith("/"):
        raise ValueError("Pointer must be empty or start with '/'")

    tokens = _parse_pointer(pointer)

    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise KeyError()
            current = current[token]
        elif isinstance(current, list):
            if not _is_valid_list_index(token):
                raise KeyError()
            index = int(token)
            if index >= len(current):
                raise KeyError()
            current = current[index]
        else:
            raise KeyError()

    return current


def set_value(document: Any, pointer: str, value: Any) -> Any:
    """Set a value at the pointer location, returning a new document.

    The returned document shares no dicts or lists with the input document.
    Follows RFC 6901 JSON Pointer specification.
    """
    if pointer == "":
        return value

    if not pointer.startswith("/"):
        raise ValueError("Pointer must be empty or start with '/'")

    tokens = _parse_pointer(pointer)

    # Deep copy the entire document to ensure no shared containers
    result = _deep_copy(document)

    # Navigate to parent container
    cursor = result
    for token in tokens[:-1]:
        if isinstance(cursor, dict):
            if token not in cursor:
                raise KeyError()
            cursor = cursor[token]
        elif isinstance(cursor, list):
            if not _is_valid_list_index(token):
                raise KeyError()
            index = int(token)
            if index >= len(cursor):
                raise KeyError()
            cursor = cursor[index]
        else:
            raise KeyError()

    # Apply last token to parent
    last_token = tokens[-1]
    if isinstance(cursor, dict):
        cursor[last_token] = value
    elif isinstance(cursor, list):
        if last_token == "-":
            cursor.append(value)
        else:
            if not _is_valid_list_index(last_token):
                raise KeyError()
            index = int(last_token)
            if index >= len(cursor):
                raise KeyError()
            cursor[index] = value
    else:
        raise KeyError()

    return result


def _parse_pointer(pointer: str) -> list:
    """Parse and validate pointer string, returning list of decoded tokens.

    Pointer must start with "/" (guaranteed by caller).
    Validates all escape sequences before returning.
    """
    parts = pointer.split("/")
    tokens = parts[1:]

    # Decode all tokens and validate escape sequences
    decoded = []
    for token in tokens:
        decoded.append(_decode_token(token))

    return decoded


def _decode_token(token: str) -> str:
    """Decode escape sequences in a token.

    Replaces ~1 with / and ~0 with ~.
    Must decode ~1 before ~0 to handle sequences like ~01 correctly.
    Raises ValueError if ~ appears in other contexts.
    """
    # Decode ~1 first (represents /), then ~0 (represents ~)
    result = token.replace("~1", "/")
    result = result.replace("~0", "~")

    # Check for invalid ~ usage
    if "~" in result:
        raise ValueError()

    return result


def _is_valid_list_index(token: str) -> bool:
    """Check if token is a valid array index.

    Valid indices are:
    - "0"
    - "1" through "9"
    - Any number without leading zeros

    Invalid: "-", "-1", " 5", "01", etc.
    """
    if not token or not token.isdigit():
        return False

    # Reject leading zeros (except "0" itself)
    if token[0] == "0" and len(token) > 1:
        return False

    return True


def _deep_copy(obj: Any) -> Any:
    """Deep copy dicts and lists recursively.

    Leaves (non-container types) are returned as-is.
    """
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_copy(item) for item in obj]
    else:
        return obj
