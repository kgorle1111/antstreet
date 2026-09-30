from intervals import subtract


def test_hole_in_the_middle_splits_an_interval():
    assert subtract([(0, 10)], [(3, 5)]) == [(0, 3), (5, 10)]


def test_hole_at_either_end_shortens_an_interval():
    assert subtract([(0, 10)], [(0, 4)]) == [(4, 10)]
    assert subtract([(0, 10)], [(6, 10)]) == [(0, 6)]
    assert subtract([(0, 10)], [(-5, 3)]) == [(3, 10)]
    assert subtract([(0, 10)], [(7, 99)]) == [(0, 7)]


def test_hole_covering_everything_leaves_nothing():
    assert subtract([(2, 5)], [(2, 5)]) == []
    assert subtract([(2, 5)], [(0, 100)]) == []


def test_disjoint_or_merely_touching_hole_changes_nothing():
    assert subtract([(0, 5)], [(10, 20)]) == [(0, 5)]
    assert subtract([(5, 10)], [(0, 5)]) == [(5, 10)]
    assert subtract([(5, 10)], [(10, 15)]) == [(5, 10)]


def test_several_holes_and_several_intervals():
    assert subtract([(0, 10), (20, 30)], [(2, 4), (6, 8), (25, 26)]) == [
        (0, 2),
        (4, 6),
        (8, 10),
        (20, 25),
        (26, 30),
    ]


def test_one_hole_spanning_several_intervals():
    assert subtract([(0, 5), (7, 12), (15, 20)], [(3, 17)]) == [(0, 3), (17, 20)]


def test_hole_bridging_a_gap_between_intervals():
    assert subtract([(0, 5), (10, 15)], [(3, 12)]) == [(0, 3), (12, 15)]


def test_single_integer_hole():
    assert subtract([(0, 3)], [(1, 2)]) == [(0, 1), (2, 3)]
