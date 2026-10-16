def test_format_size_unit_selection():
    from bytesize import format_size
    # Binary units
    assert format_size(512) == "512 B"
    assert format_size(1023) == "1023 B"
    assert format_size(1024) == "1 KiB"
    assert format_size(1048576) == "1 MiB"
    
    # Decimal units
    assert format_size(999, binary=False) == "999 B"
    assert format_size(1000, binary=False) == "1 KB"
    assert format_size(1050, binary=False) == "1.1 KB"
    assert format_size(1150, binary=False) == "1.2 KB"