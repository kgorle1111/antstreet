import pytest
from luhn import check_digit, is_valid, with_check_digit


@pytest.mark.parametrize(
    ("payload", "full"),
    [
        ("7992739871", "79927398713"),
        ("411111111111111", "4111111111111111"),
        ("37828224631000", "378282246310005"),
        ("550000000000000", "5500000000000004"),
        ("0", "00"),
        ("1", "18"),
        ("5", "59"),
        ("0001", "00018"),
        ("123", "1230"),
    ],
)
def test_the_payload_followed_by_its_check_digit(payload, full):
    assert with_check_digit(payload) == full


@pytest.mark.parametrize(
    "payload",
    ["7992 7398 71", "7992-7398-71", "  7992739871  ", "7-9-9-2-7-3-9-8-7-1", "- 7992739871 -"],
)
def test_separators_are_removed_from_the_result(payload):
    assert with_check_digit(payload) == "79927398713"


def test_the_result_is_a_valid_str_of_digits_one_longer_than_the_payload():
    for n in range(0, 1500):
        payload = f"{n:05d}"
        full = with_check_digit(payload)
        assert isinstance(full, str)
        assert full.isascii() and full.isdigit()
        assert len(full) == len(payload) + 1
        assert full.startswith(payload)
        assert is_valid(full)
        assert full[-1] == str(check_digit(payload))
