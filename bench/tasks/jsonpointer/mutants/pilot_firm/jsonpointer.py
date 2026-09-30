# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: invalid_pointers, list_indexes, set_value_errors, set_value_isolation.
import copy


def resolve(document, pointer: str):
    if pointer == "":
        return document

    if not pointer.startswith("/"):
        raise ValueError()

    tokens = pointer[1:].split("/")

    current = document
    for token in tokens:
        # Validate escape sequences
        temp = token.replace("~1", "").replace("~0", "")
        if "~" in temp:
            raise ValueError()

        # Decode escape sequences: ~1 -> /, ~0 -> ~
        decoded = token.replace("~1", "/").replace("~0", "~")

        if isinstance(current, dict):
            if decoded not in current:
                raise KeyError()
            current = current[decoded]
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


def set_value(document, pointer: str, value):
    if pointer == "":
        return value

    if not pointer.startswith("/"):
        raise ValueError()

    tokens = pointer[1:].split("/")

    # Validate all tokens first
    for token in tokens:
        temp = token.replace("~1", "").replace("~0", "")
        if "~" in temp:
            raise ValueError()

    return _set_value_impl(document, tokens, 0, value)


def _set_value_impl(current, tokens, index, value):
    token = tokens[index]
    decoded = token.replace("~1", "/").replace("~0", "~")

    if index == len(tokens) - 1:
        # Final token
        if isinstance(current, dict):
            result = copy.copy(current)
            result[decoded] = value
            return result
        elif isinstance(current, list):
            result = current[:]
            if token == "-":
                result.append(value)
            else:
                if not _is_valid_list_index(token):
                    raise KeyError()
                idx = int(token)
                if idx >= len(result):
                    raise KeyError()
                result[idx] = value
            return result
        else:
            raise KeyError()
    else:
        # Intermediate token
        if isinstance(current, dict):
            if decoded not in current:
                raise KeyError()
            next_val = current[decoded]
            result = copy.copy(current)
            result[decoded] = _set_value_impl(next_val, tokens, index + 1, value)
            return result
        elif isinstance(current, list):
            if token == "-":
                raise KeyError()
            if not _is_valid_list_index(token):
                raise KeyError()
            idx = int(token)
            if idx >= len(current):
                raise KeyError()
            next_val = current[idx]
            result = current[:]
            result[idx] = _set_value_impl(next_val, tokens, index + 1, value)
            return result
        else:
            raise KeyError()


def _is_valid_list_index(token: str) -> bool:
    if not token:
        return False
    if token == "-":
        return False
    if not token.isdigit():
        return False
    if len(token) > 1 and token[0] == "0":
        return False
    return True
