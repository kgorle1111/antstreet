import pytest
from luhn import check_digit, is_valid


@pytest.mark.parametrize(
    ("payload", "digit"),
    [
        ("7992739871", 3),
        ("411111111111111", 1),
        ("37828224631000", 5),
        ("550000000000000", 4),
        ("601111111111111", 7),
        ("453914880343646", 7),
        ("0", 0),
        ("1", 8),
        ("5", 9),
        ("9", 1),
        ("00", 0),
        ("1234", 4),
        ("12345", 5),
    ],
)
def test_known_check_digits(payload, digit):
    assert check_digit(payload) == digit


def test_the_digit_is_zero_when_the_sum_is_already_a_multiple_of_ten():
    # 1230, 5900 and 10900 are valid, so the digit to append to 123, 590 and 1090 is 0, not 10
    assert check_digit("123") == 0
    assert check_digit("590") == 0
    assert check_digit("1090") == 0
    assert check_digit("0") == 0
    assert check_digit("0000000") == 0


def test_the_check_digit_is_a_digit_from_0_to_9():
    for n in range(0, 2000):
        digit = check_digit(str(n))
        assert type(digit) is int
        assert 0 <= digit <= 9


def test_appending_the_check_digit_makes_a_valid_number():
    for n in range(0, 3000):
        payload = str(n)
        assert is_valid(payload + str(check_digit(payload))), payload


def test_exactly_one_digit_works():
    for payload in ("7", "79", "799", "7992", "79927", "0", "00", "99999", "123456789"):
        working = [d for d in range(10) if is_valid(payload + str(d))]
        assert working == [check_digit(payload)]


def test_the_payload_shifts_left_when_the_digit_is_appended():
    # in 79927398713 the payload's last digit (1) is the second from the right, so it is doubled
    assert check_digit("7992739871") == 3
    assert check_digit("7992739870") == 5
    assert check_digit("7992739872") == 1


@pytest.mark.parametrize(
    "payload",
    ["7992 7398 71", "7992-7398-71", "  7992739871  ", "7 9 9 2 7 3 9 8 7 1", "--7992739871--"],
)
def test_spaces_and_hyphens_in_the_payload_are_ignored(payload):
    assert check_digit(payload) == 3


def test_leading_zeros_count_as_digits_but_add_nothing():
    assert check_digit("00007992739871") == 3
    assert check_digit("0001") == 8
    assert is_valid("00018")
