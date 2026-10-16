def test_parse_size_basic():
    from bytesize import parse_size
    assert parse_size("1.5 KiB") == 1536
    assert parse_size("2 GiB") == 2 * (1024 ** 3)