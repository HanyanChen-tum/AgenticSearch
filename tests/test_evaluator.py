from shared.evaluator import is_correct, normalize_answer


def test_normalize_answer_sorts_rows_with_mixed_none_and_string_values():
    answer = [["b"], [None], ["a"]]

    assert normalize_answer(answer) == [(None,), ("a",), ("b",)]


def test_is_correct_handles_unordered_mixed_type_rows():
    pred = [["a"], [None], ["b"]]
    gold = [[None], ["b"], ["a"]]

    assert is_correct(pred, gold)
