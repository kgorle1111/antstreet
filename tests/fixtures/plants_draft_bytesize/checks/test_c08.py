def test_format_size_errors():
    from bytesize import format_size
    
    # ValueError for negative n
    try:
        format_size(-1)
        assert False
    except ValueError:
        pass
    
    # TypeError for non-int n (including bool)
    for inp in [1.5, "512", None, True, False]:
        try:
            format_size(inp)
            assert False, f"Should raise TypeError for {repr(inp)}"
        except TypeError:
            pass