from shortestpath import shortest_path


def test_the_example_from_the_rule():
    graph = {"S": {"A": 2, "B": 1}, "A": {"T": 1}, "B": {"T": 2}}
    assert shortest_path(graph, "S", "T") == (3, ["S", "A", "T"])


def test_smaller_name_wins_whatever_order_the_edges_are_listed_in():
    one = {"S": {"B": 1, "A": 1}, "A": {"T": 1}, "B": {"T": 1}}
    two = {"S": {"A": 1, "B": 1}, "B": {"T": 1}, "A": {"T": 1}}
    assert shortest_path(one, "S", "T") == (2, ["S", "A", "T"])
    assert shortest_path(two, "S", "T") == (2, ["S", "A", "T"])


def test_the_smaller_first_step_wins_even_if_it_is_found_later():
    graph = {"S": {"B": 1, "A": 3}, "B": {"T": 3}, "A": {"T": 1}}
    assert shortest_path(graph, "S", "T") == (4, ["S", "A", "T"])


def test_the_first_difference_decides_not_the_last_or_the_length():
    graph = {
        "S": {"A": 1, "B": 1},
        "A": {"Z": 1},
        "Z": {"T": 1},
        "B": {"C": 1},
        "C": {"T": 1},
    }
    # S-A-Z-T and S-B-C-T both cost 3. They differ first at the second node, and A < B.
    assert shortest_path(graph, "S", "T") == (3, ["S", "A", "Z", "T"])


def test_a_longer_path_in_edges_wins_when_its_node_is_smaller():
    graph = {
        "S": {"A": 1, "B": 1},
        "A": {"T": 5},
        "B": {"C": 1, "T": 4},
        "C": {"T": 3},
    }
    # S-A-T costs 6; S-B-T and S-B-C-T cost 5. 'C' < 'T' at the third node, so the longer one wins.
    assert shortest_path(graph, "S", "T") == (5, ["S", "B", "C", "T"])


def test_a_tie_that_only_appears_later_in_the_path():
    graph = {
        "S": {"M": 1},
        "M": {"Y": 1, "X": 1},
        "X": {"T": 1},
        "Y": {"T": 1},
    }
    assert shortest_path(graph, "S", "T") == (3, ["S", "M", "X", "T"])


def test_two_separate_ties_in_one_path():
    graph = {
        "S": {"B": 1, "A": 1},
        "A": {"M": 1},
        "B": {"M": 1},
        "M": {"Y": 1, "X": 1},
        "X": {"T": 1},
        "Y": {"T": 1},
    }
    assert shortest_path(graph, "S", "T") == (4, ["S", "A", "M", "X", "T"])


def test_a_cheaper_path_beats_a_smaller_name():
    graph = {"S": {"A": 5, "Z": 1}, "A": {"T": 1}, "Z": {"T": 1}}
    assert shortest_path(graph, "S", "T") == (2, ["S", "Z", "T"])


def test_numeric_nodes_compare_as_numbers_not_as_text():
    graph = {0: {10: 1, 9: 1}, 10: {99: 1}, 9: {99: 1}}
    assert shortest_path(graph, 0, 99) == (2, [0, 9, 99])


def test_a_wide_tie_picks_the_smallest_at_every_step():
    graph = {"S": {c: 1 for c in "EDCBA"}}
    for c in "EDCBA":
        graph[c] = {"T": 1}
    assert shortest_path(graph, "S", "T") == (2, ["S", "A", "T"])
