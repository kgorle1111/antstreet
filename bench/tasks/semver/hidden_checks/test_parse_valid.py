from semver import parse


def test_plain_version():
    assert parse("1.2.3") == (1, 2, 3, (), ())
    assert parse("0.0.0") == (0, 0, 0, (), ())
    assert parse("10.20.30") == (10, 20, 30, (), ())


def test_numbers_have_no_upper_bound():
    assert parse("18446744073709551616.0.1") == (18446744073709551616, 0, 1, (), ())


def test_prerelease_numeric_identifiers_are_ints():
    result = parse("1.2.3-alpha.7")
    assert result == (1, 2, 3, ("alpha", 7), ())
    assert type(result[3][1]) is int
    assert type(result[3][0]) is str


def test_prerelease_only_and_build_only():
    assert parse("1.0.0-rc.1") == (1, 0, 0, ("rc", 1), ())
    assert parse("1.0.0+20130313144700") == (1, 0, 0, (), ("20130313144700",))


def test_prerelease_and_build_together():
    assert parse("1.2.3-alpha.7+exp.sha.5") == (1, 2, 3, ("alpha", 7), ("exp", "sha", "5"))
    assert parse("1.0.0-0+0") == (1, 0, 0, (0,), ("0",))


def test_hyphens_belong_to_identifiers():
    assert parse("1.0.0-alpha-beta") == (1, 0, 0, ("alpha-beta",), ())
    assert parse("1.0.0-alpha-beta.1-2") == (1, 0, 0, ("alpha-beta", "1-2"), ())
    assert parse("1.0.0+build-1") == (1, 0, 0, (), ("build-1",))
    assert parse("1.0.0-a-b+c-d") == (1, 0, 0, ("a-b",), ("c-d",))
    assert parse("1.0.0--") == (1, 0, 0, ("-",), ())


def test_leading_zeros_allowed_where_the_spec_allows_them():
    assert parse("1.0.0-0") == (1, 0, 0, (0,), ())
    assert parse("1.0.0-0a") == (1, 0, 0, ("0a",), ())
    assert parse("1.0.0-01a") == (1, 0, 0, ("01a",), ())
    assert parse("1.0.0-a.0.b") == (1, 0, 0, ("a", 0, "b"), ())
    assert parse("1.0.0+001") == (1, 0, 0, (), ("001",))
    assert parse("1.0.0-1+00.01") == (1, 0, 0, (1,), ("00", "01"))


def test_case_is_preserved():
    assert parse("1.0.0-RC.Beta") == (1, 0, 0, ("RC", "Beta"), ())
