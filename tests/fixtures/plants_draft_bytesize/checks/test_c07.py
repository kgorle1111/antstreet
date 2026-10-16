def test_format_size_rounding_step_up():
    from bytesize import format_size
    # Binary: step-up when rounded number reaches 1024
    assert format_size(1048575) == "1 MiB"
    assert format_size(1048524) == "1023.9 KiB"
    assert format_size(1280) == "1.3 KiB"
    
    # Decimal: step-up when rounded number reaches 1000  
    assert format_size(999950, binary=False) == "1 MB"
    assert format_size(1950, binary=False) == "2 KB"