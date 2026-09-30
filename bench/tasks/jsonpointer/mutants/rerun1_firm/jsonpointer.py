# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: list_indexes, set_value_errors.
def resolve(document, pointer):
    """
    Resolve a JSON Pointer (RFC 6901) in a document.
    """
    if pointer == "":
        return document

    if not pointer.startswith("/"):
        raise ValueError("Pointer must be empty or start with /")

    # Split into tokens and decode
    tokens = pointer[1:].split("/")
    tokens = [_decode_token(t) for t in tokens]

    # Follow tokens
    current = document
    for token in tokens:
        current = _follow_token(current, token)

    return current


def set_value(document, pointer, value):
    """
    Set a value in a document at the given pointer, returning a new document.
    The new document shares no dicts or lists with the input.
    """
    if pointer == "":
        return value

    if not pointer.startswith("/"):
        raise ValueError("Pointer must be empty or start with /")

    # Split into tokens and decode
    tokens = pointer[1:].split("/")
    tokens = [_decode_token(t) for t in tokens]

    # Apply set_value recursively
    return _set_value_recursive(document, tokens, value, 0)


def _decode_token(token):
    """
    Decode a single token by replacing ~1 with / and ~0 with ~.
    ~1 must be decoded before ~0.
    """
    # Validate that every ~ is followed by 0 or 1
    i = 0
    while i < len(token):
        if token[i] == "~":
            if i + 1 >= len(token):
                raise ValueError("Invalid escape sequence: ~ at end of token")
            if token[i + 1] not in "01":
                raise ValueError("Invalid escape sequence in token")
            i += 2
        else:
            i += 1

    # Decode in the correct order: ~1 first, then ~0
    result = token.replace("~1", "/")
    result = result.replace("~0", "~")
    return result


def _follow_token(current, token):
    """
    Follow a single token through the document.
    """
    if isinstance(current, dict):
        if token not in current:
            raise KeyError(token)
        return current[token]
    elif isinstance(current, list):
        if not _is_valid_list_index(token):
            raise KeyError(token)
        index = int(token)
        if index >= len(current):
            raise KeyError(token)
        return current[index]
    else:
        # Leaf value (including None, str, int, etc.)
        raise KeyError(token)


def _is_valid_list_index(token):
    """
    Check if a token is a valid list index.
    Valid indices: "0" or 1-9 followed by 0-9 digits.
    The token "-" is not valid for resolve.
    """
    if token == "-":
        return False
    if len(token) == 0:
        return False
    if token[0] == "0" and len(token) > 1:
        return False  # No leading zeros except "0"
    if token[0] in "-+":
        return False  # No signs
    for c in token:
        if not c.isdigit():
            return False
    return True


def _set_value_recursive(document, tokens, value, index):
    """
    Recursively set a value in a document at the given tokens.
    Returns a new document (never modifies the input).
    All containers in the result are new objects (deep independence).
    """
    if index == len(tokens):
        return value

    token = tokens[index]
    is_last_token = index == len(tokens) - 1

    if isinstance(document, dict):
        # First check if we can proceed (if not last token, key must exist)
        if not is_last_token and token not in document:
            raise KeyError(token)

        # Copy the dict with deep copies of all values
        result = {}
        for k, v in document.items():
            if k == token:
                if is_last_token:
                    result[k] = value
                else:
                    result[k] = _set_value_recursive(v, tokens, value, index + 1)
            else:
                result[k] = _deep_copy_value(v)

        # If we're setting a new key (last token only)
        if is_last_token and token not in document:
            result[token] = value

        return result

    elif isinstance(document, list):
        if is_last_token:
            if token == "-":
                # Append mode
                result = [_deep_copy_value(v) for v in document]
                result.append(value)
                return result
            elif _is_valid_list_index(token):
                idx = int(token)
                if idx >= len(document):
                    raise KeyError(token)
                result = []
                for i, v in enumerate(document):
                    if i == idx:
                        result.append(value)
                    else:
                        result.append(_deep_copy_value(v))
                return result
            else:
                raise KeyError(token)
        else:
            # Not last token: recurse deeper
            if not _is_valid_list_index(token):
                raise KeyError(token)
            idx = int(token)
            if idx >= len(document):
                raise KeyError(token)
            result = []
            for i, v in enumerate(document):
                if i == idx:
                    result.append(_set_value_recursive(v, tokens, value, index + 1))
                else:
                    result.append(_deep_copy_value(v))
            return result

    else:
        # Leaf value - cannot descend or set
        raise KeyError(token)


def _deep_copy_value(value):
    """
    Deep copy a value (dicts and lists are recursively copied).
    """
    if isinstance(value, dict):
        return {k: _deep_copy_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_deep_copy_value(v) for v in value]
    else:
        # Leaf values are returned as-is (immutable)
        return value
