def test_format_size_basic():
    from bytesize import format_size
    assert format_size(1536) == "1.5 KiB"
    assert format_size(2048) == "2 KiB"
    assert format_size(0) == "0 B"