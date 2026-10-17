from decimal import Decimal

from kap.eval.scoring import lenient_match, strict_match


def test_strict_ignores_order_and_duplicates_and_numeric_types():
    assert strict_match([(1, "a"), (2, "b")], [(2, "b"), (1, "a"), (1, "a")])
    assert strict_match([(Decimal("1.50"),)], [(1.5,)])
    assert strict_match([(10,)], [("10",)])


def test_strict_fails_on_different_values_or_width():
    assert not strict_match([(1,)], [(2,)])
    assert not strict_match([(1,)], [(1, "x")])
    assert not strict_match([(1,)], [])


def test_lenient_allows_extra_columns():
    assert lenient_match([("a", 1)], [("a", 1, "extra"), ])
    assert not lenient_match([("a", 1)], [("b", 1, "extra")])
