# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: compare.
def _is_ascii_digit(c: str) -> bool:
    return '0' <= c <= '9'

def _validate(s: str) -> None:
    if not isinstance(s, str):
        raise ValueError()
    if not s:
        raise ValueError()

    i = 0
    if s[0] == '-':
        i = 1

    if i >= len(s):
        raise ValueError()

    if not _is_ascii_digit(s[i]):
        raise ValueError()

    while i < len(s) and _is_ascii_digit(s[i]):
        i += 1

    if i < len(s):
        if s[i] != '.':
            raise ValueError()
        i += 1

        if i >= len(s) or not _is_ascii_digit(s[i]):
            raise ValueError()

        while i < len(s) and _is_ascii_digit(s[i]):
            i += 1

    if i < len(s):
        raise ValueError()

def _parse(s: str) -> tuple[bool, str, str]:
    is_negative = s[0] == '-'
    if is_negative:
        s = s[1:]

    if '.' in s:
        integer_part, fractional_part = s.split('.')
    else:
        integer_part = s
        fractional_part = ''

    return is_negative, integer_part, fractional_part

def _is_zero(integer_part: str, fractional_part: str) -> bool:
    return all(c == '0' for c in integer_part + fractional_part)

def _canonicalize(is_negative: bool, integer_part: str, fractional_part: str) -> str:
    if _is_zero(integer_part, fractional_part):
        return "0"

    integer_part = integer_part.lstrip('0') or '0'
    fractional_part = fractional_part.rstrip('0')

    if fractional_part:
        result = f"{integer_part}.{fractional_part}"
    else:
        result = integer_part

    if is_negative:
        result = '-' + result

    return result

def _compare_magnitudes(int_a: str, frac_a: str, int_b: str, frac_b: str) -> int:
    int_a_trimmed = int_a.lstrip('0') or '0'
    int_b_trimmed = int_b.lstrip('0') or '0'
    frac_a_trimmed = frac_a.rstrip('0')
    frac_b_trimmed = frac_b.rstrip('0')

    if len(int_a_trimmed) != len(int_b_trimmed):
        return -1 if len(int_a_trimmed) < len(int_b_trimmed) else 1

    if int_a_trimmed != int_b_trimmed:
        return -1 if int_a_trimmed < int_b_trimmed else 1

    max_frac = max(len(frac_a_trimmed), len(frac_b_trimmed))
    frac_a_padded = frac_a_trimmed.ljust(max_frac, '0')
    frac_b_padded = frac_b_trimmed.ljust(max_frac, '0')

    if frac_a_padded < frac_b_padded:
        return -1
    elif frac_a_padded > frac_b_padded:
        return 1
    else:
        return 0

def _subtract_magnitudes(int_a: str, frac_a: str, int_b: str, frac_b: str) -> tuple[str, str]:
    max_frac_len = max(len(frac_a), len(frac_b))
    frac_a = frac_a.ljust(max_frac_len, '0')
    frac_b = frac_b.ljust(max_frac_len, '0')

    result_frac_digits = []
    borrow = 0

    for i in range(max_frac_len - 1, -1, -1):
        diff = int(frac_a[i]) - int(frac_b[i]) - borrow
        if diff < 0:
            diff += 10
            borrow = 1
        else:
            borrow = 0
        result_frac_digits.append(str(diff))

    result_frac_digits.reverse()
    result_frac = ''.join(result_frac_digits)

    int_a_digits = int_a[::-1]
    int_b_digits = int_b[::-1]
    max_int_len = max(len(int_a), len(int_b))

    result_int_digits = []
    for i in range(max_int_len):
        digit_a = int(int_a_digits[i]) if i < len(int_a_digits) else 0
        digit_b = int(int_b_digits[i]) if i < len(int_b_digits) else 0
        diff = digit_a - digit_b - borrow
        if diff < 0:
            diff += 10
            borrow = 1
        else:
            borrow = 0
        result_int_digits.append(str(diff))

    result_int_digits.reverse()
    result_int = ''.join(result_int_digits).lstrip('0') or '0'

    result_frac = result_frac.rstrip('0')

    return result_int, result_frac

def add(a: str, b: str) -> str:
    _validate(a)
    _validate(b)

    neg_a, int_a, frac_a = _parse(a)
    neg_b, int_b, frac_b = _parse(b)

    if neg_a != neg_b:
        cmp = _compare_magnitudes(int_a, frac_a, int_b, frac_b)
        if cmp > 0:
            result_int, result_frac = _subtract_magnitudes(int_a, frac_a, int_b, frac_b)
            return _canonicalize(neg_a, result_int, result_frac)
        elif cmp < 0:
            result_int, result_frac = _subtract_magnitudes(int_b, frac_b, int_a, frac_a)
            return _canonicalize(neg_b, result_int, result_frac)
        else:
            return "0"

    max_frac_len = max(len(frac_a), len(frac_b))
    frac_a = frac_a.ljust(max_frac_len, '0')
    frac_b = frac_b.ljust(max_frac_len, '0')

    result_frac_digits = []
    carry = 0

    for i in range(max_frac_len - 1, -1, -1):
        digit_sum = int(frac_a[i]) + int(frac_b[i]) + carry
        result_frac_digits.append(str(digit_sum % 10))
        carry = digit_sum // 10

    result_frac_digits.reverse()
    result_frac = ''.join(result_frac_digits)

    int_a_digits = int_a[::-1]
    int_b_digits = int_b[::-1]
    max_int_len = max(len(int_a), len(int_b))

    result_int_digits = []
    for i in range(max_int_len):
        digit_a = int(int_a_digits[i]) if i < len(int_a_digits) else 0
        digit_b = int(int_b_digits[i]) if i < len(int_b_digits) else 0
        digit_sum = digit_a + digit_b + carry
        result_int_digits.append(str(digit_sum % 10))
        carry = digit_sum // 10

    if carry:
        result_int_digits.append(str(carry))

    result_int_digits.reverse()
    result_int = ''.join(result_int_digits)

    result_frac = result_frac.rstrip('0')

    return _canonicalize(neg_a, result_int, result_frac)

def subtract(a: str, b: str) -> str:
    _validate(a)
    _validate(b)

    neg_b, int_b, frac_b = _parse(b)
    return add(a, _canonicalize(not neg_b, int_b, frac_b))

def _multiply_magnitudes(a_digits: str, b_digits: str) -> str:
    if not a_digits or not b_digits:
        return '0'

    result = [0] * (len(a_digits) + len(b_digits))

    for i in range(len(a_digits) - 1, -1, -1):
        for j in range(len(b_digits) - 1, -1, -1):
            mul = int(a_digits[i]) * int(b_digits[j])
            p = i + j + 1
            result[p] += mul

    for i in range(len(result) - 1, 0, -1):
        result[i - 1] += result[i] // 10
        result[i] %= 10

    result_str = ''.join(str(d) for d in result).lstrip('0') or '0'
    return result_str

def multiply(a: str, b: str) -> str:
    _validate(a)
    _validate(b)

    neg_a, int_a, frac_a = _parse(a)
    neg_b, int_b, frac_b = _parse(b)

    if _is_zero(int_a, frac_a) or _is_zero(int_b, frac_b):
        return "0"

    a_digits = int_a + frac_a
    b_digits = int_b + frac_b
    result_digits = _multiply_magnitudes(a_digits, b_digits)

    total_frac = len(frac_a) + len(frac_b)

    if len(result_digits) <= total_frac:
        result_int = '0'
        result_frac = result_digits.rjust(total_frac, '0')
    else:
        split_point = len(result_digits) - total_frac
        result_int = result_digits[:split_point]
        result_frac = result_digits[split_point:]

    result_neg = neg_a != neg_b

    return _canonicalize(result_neg, result_int, result_frac)

def compare(a: str, b: str) -> int:
    _validate(a)
    _validate(b)

    neg_a, int_a, frac_a = _parse(a)
    neg_b, int_b, frac_b = _parse(b)

    is_zero_a = _is_zero(int_a, frac_a)
    is_zero_b = _is_zero(int_b, frac_b)

    if is_zero_a and is_zero_b:
        return 0

    if is_zero_a:
        return -1 if neg_b else 1

    if is_zero_b:
        return -1 if not neg_a else 1

    if neg_a and not neg_b:
        return -1
    if not neg_a and neg_b:
        return 1

    cmp = _compare_magnitudes(int_a, frac_a, int_b, frac_b)
    return cmp if not neg_a else -cmp
