# tests/test_aggregate.py
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import aggregate  # noqa: E402


class TestAggregate(unittest.TestCase):
    def test_core_ignores_lenses(self):
        self.assertEqual(aggregate.aggregate(80, [40, 90], "core"), 80)

    def test_no_lenses_returns_core(self):
        self.assertEqual(aggregate.aggregate(82, [], "min"), 82)

    def test_min_takes_lowest(self):
        self.assertEqual(aggregate.aggregate(82, [61, 90], "min"), 61)

    def test_mean_averages_core_and_lenses(self):
        self.assertEqual(aggregate.aggregate(80, [60, 100], "mean"), 80)

    def test_unknown_rule_raises(self):
        with self.assertRaises(ValueError):
            aggregate.aggregate(80, [10], "bogus")


if __name__ == "__main__":
    unittest.main()


class TestAggregateSanitizesScores(unittest.TestCase):
    def test_clamps_out_of_range_scores(self):
        self.assertEqual(aggregate.aggregate(82, [9999], "min"), 82)   # 9999 -> 100
        self.assertEqual(aggregate.aggregate(82, [-5], "min"), 0)      # -5 -> 0

    def test_drops_non_numeric_scores(self):
        self.assertEqual(aggregate.aggregate(80, ["high"], "min"), 80)
        self.assertEqual(aggregate.aggregate(80, [None], "mean"), 80)

    def test_bad_core_raises(self):
        with self.assertRaises(ValueError):
            aggregate.aggregate("nope", [50], "min")
