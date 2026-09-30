# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: invalid_input.
def _validate(s: str) -> None:
    """Validate that s is a valid number string."""
    if not isinstance(s, str):
        raise ValueError("Argument must be a string")

    if not s:
        raise ValueError("Empty string")

    i = 0

    # Check optional minus
    if s[i] == '-':
        i += 1
        if i >= len(s):
            raise ValueError("Invalid format")

    # Must have at least one digit
    if i >= len(s) or not s[i].isdigit():
        raise ValueError("Invalid format")

    # Check remaining characters
    has_decimal = False
    i += 1

    while i < len(s):
        if s[i] == '.':
            if has_decimal:
                raise ValueError("Multiple decimal points")
            has_decimal = True
            i += 1
            # Must have digit after decimal
            if i >= len(s) or not s[i].isdigit():
                raise ValueError("Invalid format")
        elif not s[i].isdigit():
            raise ValueError("Invalid character")
        else:
            i += 1


def _parse(s: str) -> tuple:
    """Parse a number string into (is_negative, integer_part, fractional_part)."""
    is_negative = s[0] == '-'
    s = s[1:] if is_negative else s

    if '.' in s:
        int_part, frac_part = s.split('.')
    else:
        int_part = s
        frac_part = ''

    return is_negative, int_part, frac_part


def _canonicalize(is_negative: bool, int_part: str, frac_part: str) -> str:
    """Convert parsed number to canonical form."""
    # Remove leading zeros from int_part
    int_part = int_part.lstrip('0') or '0'

    # Remove trailing zeros from frac_part
    frac_part = frac_part.rstrip('0')

    # If result is zero, return "0"
    if int_part == '0' and not frac_part:
        return '0'

    # Build result
    result = int_part
    if frac_part:
        result += '.' + frac_part

    # Add negative sign if negative and not zero
    if is_negative:
        result = '-' + result

    return result


def _compare_magnitudes(int_a: str, frac_a: str, int_b: str, frac_b: str) -> int:
    """Compare magnitudes of two numbers. Returns -1, 0, or 1."""
    # Remove leading zeros
    int_a = int_a.lstrip('0') or '0'
    int_b = int_b.lstrip('0') or '0'

    # Compare integer parts by length first
    if len(int_a) > len(int_b):
        return 1
    elif len(int_a) < len(int_b):
        return -1

    # Same length, compare lexicographically
    if int_a > int_b:
        return 1
    elif int_a < int_b:
        return -1

    # Integer parts equal, compare fractional parts
    max_frac_len = max(len(frac_a), len(frac_b))
    frac_a = frac_a.ljust(max_frac_len, '0')
    frac_b = frac_b.ljust(max_frac_len, '0')

    if frac_a > frac_b:
        return 1
    elif frac_a < frac_b:
        return -1
    else:
        return 0


def _add_magnitudes(int_a: str, frac_a: str, int_b: str, frac_b: str) -> tuple:
    """Add magnitudes of two positive numbers. Returns (int_part, frac_part)."""
    # Align decimal places
    max_frac_len = max(len(frac_a), len(frac_b))
    frac_a = frac_a.ljust(max_frac_len, '0')
    frac_b = frac_b.ljust(max_frac_len, '0')

    # Add fractional parts from right to left
    result_frac = []
    carry = 0

    for i in range(max_frac_len - 1, -1, -1):
        digit_sum = int(frac_a[i]) + int(frac_b[i]) + carry
        result_frac.append(str(digit_sum % 10))
        carry = digit_sum // 10

    result_frac.reverse()
    result_frac_str = ''.join(result_frac)

    # Add integer parts from right to left
    int_a_rev = int_a[::-1]
    int_b_rev = int_b[::-1]
    max_int_len = max(len(int_a_rev), len(int_b_rev))
    int_a_rev = int_a_rev.ljust(max_int_len, '0')
    int_b_rev = int_b_rev.ljust(max_int_len, '0')

    result_int = []
    for i in range(max_int_len):
        digit_sum = int(int_a_rev[i]) + int(int_b_rev[i]) + carry
        result_int.append(str(digit_sum % 10))
        carry = digit_sum // 10

    if carry:
        result_int.append(str(carry))

    result_int.reverse()
    result_int_str = ''.join(result_int)

    return result_int_str, result_frac_str


def _subtract_magnitudes(int_a: str, frac_a: str, int_b: str, frac_b: str) -> tuple:
    """Subtract b from a (assuming a >= b). Returns (int_part, frac_part)."""
    # Align decimal places
    max_frac_len = max(len(frac_a), len(frac_b))
    frac_a = frac_a.ljust(max_frac_len, '0')
    frac_b = frac_b.ljust(max_frac_len, '0')

    # Subtract fractional parts from right to left
    result_frac = []
    borrow = 0

    for i in range(max_frac_len - 1, -1, -1):
        digit_diff = int(frac_a[i]) - int(frac_b[i]) - borrow
        if digit_diff < 0:
            digit_diff += 10
            borrow = 1
        else:
            borrow = 0
        result_frac.append(str(digit_diff))

    result_frac.reverse()
    result_frac_str = ''.join(result_frac)

    # Subtract integer parts from right to left
    int_a_rev = int_a[::-1]
    int_b_rev = int_b[::-1]
    max_int_len = max(len(int_a_rev), len(int_b_rev))
    int_a_rev = int_a_rev.ljust(max_int_len, '0')
    int_b_rev = int_b_rev.ljust(max_int_len, '0')

    result_int = []
    for i in range(max_int_len):
        digit_diff = int(int_a_rev[i]) - int(int_b_rev[i]) - borrow
        if digit_diff < 0:
            digit_diff += 10
            borrow = 1
        else:
            borrow = 0
        result_int.append(str(digit_diff))

    result_int.reverse()
    result_int_str = ''.join(result_int)

    return result_int_str, result_frac_str


def add(a: str, b: str) -> str:
    """Add two numbers represented as strings."""
    _validate(a)
    _validate(b)

    is_neg_a, int_a, frac_a = _parse(a)
    is_neg_b, int_b, frac_b = _parse(b)

    # Handle signs
    if is_neg_a == is_neg_b:
        # Same sign: add magnitudes
        int_result, frac_result = _add_magnitudes(int_a, frac_a, int_b, frac_b)
        is_neg_result = is_neg_a
    else:
        # Different signs: subtract magnitudes
        cmp = _compare_magnitudes(int_a, frac_a, int_b, frac_b)
        if cmp >= 0:
            # |a| >= |b|
            int_result, frac_result = _subtract_magnitudes(int_a, frac_a, int_b, frac_b)
            is_neg_result = is_neg_a
        else:
            # |a| < |b|
            int_result, frac_result = _subtract_magnitudes(int_b, frac_b, int_a, frac_a)
            is_neg_result = is_neg_b

    return _canonicalize(is_neg_result, int_result, frac_result)


def subtract(a: str, b: str) -> str:
    """Subtract b from a."""
    _validate(a)
    _validate(b)

    is_neg_b, int_b, frac_b = _parse(b)
    # Negate b and add
    is_neg_b = not is_neg_b

    is_neg_a, int_a, frac_a = _parse(a)

    # Now compute a + (-b)
    if is_neg_a == is_neg_b:
        # Same sign: add magnitudes
        int_result, frac_result = _add_magnitudes(int_a, frac_a, int_b, frac_b)
        is_neg_result = is_neg_a
    else:
        # Different signs: subtract magnitudes
        cmp = _compare_magnitudes(int_a, frac_a, int_b, frac_b)
        if cmp >= 0:
            # |a| >= |b|
            int_result, frac_result = _subtract_magnitudes(int_a, frac_a, int_b, frac_b)
            is_neg_result = is_neg_a
        else:
            # |a| < |b|
            int_result, frac_result = _subtract_magnitudes(int_b, frac_b, int_a, frac_a)
            is_neg_result = is_neg_b

    return _canonicalize(is_neg_result, int_result, frac_result)


def multiply(a: str, b: str) -> str:
    """Multiply two numbers."""
    _validate(a)
    _validate(b)

    is_neg_a, int_a, frac_a = _parse(a)
    is_neg_b, int_b, frac_b = _parse(b)

    # Multiply magnitudes (treat as integers without decimal point)
    num_a = int_a + frac_a
    num_b = int_b + frac_b

    # Multiply using long multiplication
    result = [0] * (len(num_a) + len(num_b))

    for i, digit_a in enumerate(num_a[::-1]):
        for j, digit_b in enumerate(num_b[::-1]):
            result[i + j] += int(digit_a) * int(digit_b)

    # Handle carries
    for i in range(len(result) - 1):
        if result[i] >= 10:
            result[i + 1] += result[i] // 10
            result[i] %= 10

    # Convert to string (reverse to get right order)
    result = result[::-1]
    result_str = ''.join(str(d) for d in result).lstrip('0') or '0'

    # Calculate decimal places
    total_frac_len = len(frac_a) + len(frac_b)

    # Place decimal point
    if total_frac_len == 0:
        int_result = result_str
        frac_result = ''
    else:
        if len(result_str) <= total_frac_len:
            # Need leading zeros
            result_str = '0' * (total_frac_len - len(result_str) + 1) + result_str

        split_point = len(result_str) - total_frac_len
        int_result = result_str[:split_point]
        frac_result = result_str[split_point:]

    # Determine sign (negative only if exactly one is negative and result is non-zero)
    is_neg_result = is_neg_a != is_neg_b

    # If result is zero, it's always "0"
    if int_result == '0' and (not frac_result or all(d == '0' for d in frac_result)):
        is_neg_result = False

    return _canonicalize(is_neg_result, int_result, frac_result)


def compare(a: str, b: str) -> int:
    """Compare two numbers. Returns -1, 0, or 1."""
    _validate(a)
    _validate(b)

    is_neg_a, int_a, frac_a = _parse(a)
    is_neg_b, int_b, frac_b = _parse(b)

    # Handle -0 == 0
    int_a_stripped = int_a.lstrip('0') or '0'
    int_b_stripped = int_b.lstrip('0') or '0'
    frac_a_stripped = frac_a.rstrip('0')
    frac_b_stripped = frac_b.rstrip('0')

    if int_a_stripped == '0' and not frac_a_stripped:
        is_neg_a = False
    if int_b_stripped == '0' and not frac_b_stripped:
        is_neg_b = False

    # Compare signs
    if is_neg_a and not is_neg_b:
        return -1
    elif not is_neg_a and is_neg_b:
        return 1
    elif not is_neg_a and not is_neg_b:
        # Both positive
        return _compare_magnitudes(int_a, frac_a, int_b, frac_b)
    else:
        # Both negative
        cmp = _compare_magnitudes(int_a, frac_a, int_b, frac_b)
        return -cmp
