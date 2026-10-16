def test_parse_size_units():
    from bytesize import parse_size
    assert parse_size("2 MB") == 2000000
    assert parse_size("1 KiB") == 1024
    assert parse_size("1 K") == 1024
    assert parse_size("512") == 512
    assert parse_size("10 B") == 10
    assert parse_size("3 TB") == 3 * (1000 ** 4)