def test_parse_size_errors():
    from bytesize import parse_size
    
    # ValueError for invalid formats
    for inp in ["", "KB", "1 XB", "1 K B", "1e3", "-1 KB"]:
        try:
            parse_size(inp)
            assert False, f"Should raise ValueError for {repr(inp)}"
        except ValueError:
            pass
    
    # TypeError for non-string
    for inp in [512, None, 1.5]:
        try:
            parse_size(inp)
            assert False, f"Should raise TypeError for {repr(inp)}"
        except TypeError:
            pass