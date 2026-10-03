from luhn import is_valid

VALID_PAIRS = {"00", "18", "26", "34", "42", "59", "67", "75", "83", "91"}


def test_every_two_digit_number_is_checked_against_the_rule():
    # the tens digit is doubled (and reduced by 9 when it goes above 9), the units digit is not
    for tens in range(10):
        for units in range(10):
            text = f"{tens}{units}"
            assert is_valid(text) is (text in VALID_PAIRS), text


def test_a_doubled_digit_above_9_has_9_taken_off():
    # 5 doubled is 10 -> 1, so 59 is 1 + 9; without the reduction it would be 10 + 9
    assert is_valid("59")
    assert is_valid("67")  # 6 doubled is 12 -> 3, and 3 + 7
    assert is_valid("75")  # 7 doubled is 14 -> 5, and 5 + 5
    assert is_valid("83")  # 8 doubled is 16 -> 7, and 7 + 3
    assert is_valid("91")  # 9 doubled is 18 -> 9, and 9 + 1
    assert not is_valid("55")
    assert not is_valid("10") and not is_valid("28")


def test_only_every_second_digit_from_the_right_is_doubled():
    assert is_valid("109")  # 1 + 0 + 9
    assert not is_valid("119")  # 1 + 2 + 9
    assert not is_valid("1090")  # 2 + 0 + 9 + 0
    assert is_valid("1230")  # 2 + 2 + 6 + 0


def test_swapping_two_adjacent_different_digits_is_caught():
    for number in ("79927398713", "4111111111111111", "378282246310005", "1234567812345670"):
        for i in range(len(number) - 1):
            a, b = number[i], number[i + 1]
            if {a, b} == {"0", "9"} or a == b:
                continue  # the one swap Luhn cannot see
            swapped = number[:i] + b + a + number[i + 2 :]
            assert not is_valid(swapped), swapped


def test_changing_any_single_digit_is_caught():
    for number in ("79927398713", "4111111111111111", "378282246310005"):
        for i, digit in enumerate(number):
            for other in "0123456789":
                if other != digit:
                    assert not is_valid(number[:i] + other + number[i + 1 :])
