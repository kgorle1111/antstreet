from semver import compare


def test_build_metadata_is_ignored():
    assert compare("1.0.0+a", "1.0.0+b") == 0
    assert compare("1.0.0+b", "1.0.0+a") == 0
    assert compare("1.0.0+001", "1.0.0+1") == 0
    assert compare("1.0.0+20130313144700", "1.0.0+5") == 0


def test_version_with_and_without_build_are_equal():
    assert compare("1.2.3", "1.2.3+build.5") == 0
    assert compare("1.2.3+build.5", "1.2.3") == 0


def test_build_is_ignored_with_prerelease():
    assert compare("1.0.0-alpha+z", "1.0.0-alpha+a") == 0
    assert compare("1.0.0-alpha.1+x", "1.0.0-alpha.1") == 0


def test_build_does_not_override_other_differences():
    assert compare("1.0.0-alpha+zzz", "1.0.0-beta+aaa") == -1
    assert compare("1.0.0+zzz", "1.0.1+aaa") == -1
    assert compare("2.0.0+1", "1.0.0+999") == 1
    assert compare("1.0.0-rc.1+build", "1.0.0+build") == -1


def test_hyphens_in_build_are_not_a_prerelease():
    assert compare("1.0.0+build-1", "1.0.0") == 0
    assert compare("1.0.0+alpha-1", "1.0.0-alpha") == 1
