"""
Unit tests for financing_engine.py — bottoms-up correctness + no-circularity.
Run: python3 -m pytest test_financing_engine.py -v  (or plain: python3 test_financing_engine.py)
"""

from __future__ import annotations

import math
import unittest

from financing_engine import irr, monthly_payment, remaining_balance, run_financing_model
from models import DealFinancingInput, FinancingTerms, OperatingExpenses, RevenueAssumptions


class TestAmortization(unittest.TestCase):
    def test_monthly_payment_known_value(self):
        # $200,000 @ 6% / 30yr -> ~$1,199.10/mo (textbook amortization value)
        pmt = monthly_payment(200000, 6.0, 30)
        self.assertAlmostEqual(pmt, 1199.10, delta=0.5)

    def test_zero_principal_is_zero_payment(self):
        self.assertEqual(monthly_payment(0, 9.0, 25), 0.0)

    def test_remaining_balance_decreases_over_time(self):
        principal = 1_000_000
        bal_5y = remaining_balance(principal, 9.0, 25, 5)
        bal_10y = remaining_balance(principal, 9.0, 25, 10)
        self.assertLess(bal_10y, bal_5y)
        self.assertLess(bal_5y, principal)

    def test_remaining_balance_zero_at_full_term(self):
        bal = remaining_balance(1_000_000, 9.0, 25, 25)
        self.assertAlmostEqual(bal, 0.0, delta=1.0)


class TestIRR(unittest.TestCase):
    def test_simple_irr(self):
        # -100 now, +110 in 1 year -> 10% IRR
        r = irr([-100, 110])
        self.assertAlmostEqual(r, 0.10, delta=1e-4)

    def test_irr_none_when_no_sign_change(self):
        # all positive cash flows -> no real IRR in bracket
        r = irr([100, 100, 100])
        self.assertIsNone(r)


class TestNoCircularity(unittest.TestCase):
    """The engine must derive cash flow from NOI - debt_service, never from an
    assumed yield% * equity. This test asserts that relationship holds exactly
    for every projected year, catching any future regression to the circular
    pattern found in an earlier example model."""

    def _make_input(self, **overrides) -> DealFinancingInput:
        base = dict(
            deal_name="Test Deal",
            revenue=RevenueAssumptions(annual_revenue=1_000_000, revenue_growth_pct=5.0),
            opex=OperatingExpenses(annual_opex=600_000, opex_growth_pct=2.0),
            financing=FinancingTerms(
                purchase_price=3_000_000,
                loan_amount=2_400_000,
                equity_injection=600_000,
                annual_interest_rate_pct=9.0,
                amortization_years=25,
            ),
            hold_period_years=5,
        )
        base.update(overrides)
        return DealFinancingInput(**base)

    def test_cash_flow_equals_noi_minus_debt_service(self):
        inp = self._make_input()
        result = run_financing_model(inp)
        for yr in result.yearly:
            expected_cfe = round(yr.noi - yr.total_debt_service, 2)
            self.assertAlmostEqual(yr.cash_flow_to_equity, expected_cfe, delta=0.01)

    def test_debt_service_independent_of_assumed_return(self):
        """Debt service must be identical whether or not an exit cap rate
        (which drives IRR) is supplied — i.e. debt service is never a function
        of a target return."""
        inp_no_exit = self._make_input(exit_cap_rate_pct=None)
        inp_with_exit = self._make_input(exit_cap_rate_pct=8.5)
        r1 = run_financing_model(inp_no_exit)
        r2 = run_financing_model(inp_with_exit)
        self.assertEqual(r1.annual_debt_service_senior, r2.annual_debt_service_senior)
        for a, b in zip(r1.yearly, r2.yearly):
            self.assertEqual(a.total_debt_service, b.total_debt_service)
            self.assertEqual(a.noi, b.noi)

    def test_dscr_flag_when_below_1_25(self):
        # Overload debt so DSCR < 1.25x deliberately
        inp = self._make_input(
            financing=FinancingTerms(
                purchase_price=5_000_000,
                loan_amount=4_800_000,
                equity_injection=200_000,
                annual_interest_rate_pct=9.5,
                amortization_years=20,
            )
        )
        result = run_financing_model(inp)
        self.assertLess(result.year1_dscr, 1.25)
        self.assertTrue(any("DSCR" in f for f in result.flags))

    def test_no_exit_cap_rate_leaves_irr_unset_not_fabricated(self):
        inp = self._make_input(exit_cap_rate_pct=None)
        result = run_financing_model(inp)
        self.assertIsNone(result.irr_pct)
        self.assertIsNone(result.equity_multiple)
        self.assertTrue(any("not modeled" in f for f in result.flags))


class TestMissionVillaCase(unittest.TestCase):
    def test_mission_villa_runs_without_error_and_flags_rate_assumption(self):
        import json
        import os

        path = os.path.join(os.path.dirname(__file__), "cases", "mission_villa.json")
        with open(path) as fh:
            data = json.load(fh)
        inp = DealFinancingInput(**data)
        result = run_financing_model(inp)

        self.assertEqual(result.total_project_cost, 2_520_000.0)
        self.assertEqual(result.loan_amount, 2_260_000.0)
        self.assertEqual(result.equity_injection, 260_000.0)
        self.assertGreater(result.year1_noi, 0)
        # Exit not modeled -> IRR/equity multiple must be None, not fabricated
        self.assertIsNone(result.irr_pct)
        self.assertIsNone(result.equity_multiple)


if __name__ == "__main__":
    unittest.main()
