def test_parse_size_whitespace_case_rounding():
    from bytesize import parse_size
    assert parse_size("  1.5 KiB  ") == 1536
    assert parse_size("1.5kib") == 1536
    assert parse_size("1.5 \t KiB") == 1536
    assert parse_size("1.5KiB") == 1536
    assert parse_size("0.5 B") == 1
    assert parse_size("0.4 B") == 0
    assert parse_size("0.1 KiB") == 102