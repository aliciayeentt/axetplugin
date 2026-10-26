import math

import pytest

from loan_calc.calculator import (
    amortisation_schedule,
    compare_offers,
    eligible_amount,
    emi,
    format_inr,
    outstanding_after,
    prepayment_savings,
    remaining_tenure,
    total_interest,
    total_payment,
)


def test_emi_rejects_non_positive_principal() -> None:
    with pytest.raises(ValueError):
        emi(0, 10.0, 12)


def test_emi_rejects_non_positive_tenure() -> None:
    with pytest.raises(ValueError):
        emi(100_000, 10.0, 0)


def test_emi_zero_interest_is_straight_line() -> None:
    # 0% interest should simply split principal over the tenure.
    assert emi(120_000, 0.0, 12) == 10_000.00


def test_total_payment_zero_interest_equals_principal() -> None:
    assert total_payment(120_000, 0.0, 12) == 120_000.00


def test_total_interest_zero_interest_is_zero() -> None:
    assert total_interest(120_000, 0.0, 12) == 0.00


def test_emi_one_month_tenure_is_principal_plus_one_month_interest() -> None:
    # EMI formula degenerates to: P*(1+r) for n=1
    principal = 100_000
    annual_rate = 12.0
    r = round(annual_rate / 1200, 4)
    assert emi(principal, annual_rate, 1) == round(principal * (1 + r), 2)


def test_amortisation_schedule_length_is_tenure_minus_one_current_behavior() -> None:
    # NOTE: This asserts the CURRENT (buggy) behavior described in ARCHITECTURE.md.
    sched = amortisation_schedule(100_000, 10.0, 12)
    assert len(sched) == 11


def test_outstanding_after_months_paid_le_zero_returns_principal() -> None:
    assert outstanding_after(100_000, 10.0, 12, 0) == 100_000.00


def test_outstanding_after_more_than_schedule_returns_zero_current_behavior() -> None:
    # With the current schedule length bug, paying 12 months returns 0.0
    assert outstanding_after(100_000, 10.0, 12, 12) == 0.0


def test_remaining_tenure_zero_balance_is_zero() -> None:
    assert remaining_tenure(0.0, 10.0, 1000.0) == 0


def test_remaining_tenure_zero_rate_uses_simple_division() -> None:
    assert remaining_tenure(10_000.0, 0.0, 1000.0) == 10


def test_remaining_tenure_raises_if_instalment_too_small() -> None:
    # Given current implementation r=annual_rate/100, this trips easily.
    with pytest.raises(ValueError):
        remaining_tenure(100_000.0, 12.0, 1000.0)


def test_prepayment_larger_than_balance_results_in_months_left_zero() -> None:
    # Pick a prepayment month that exists in the current schedule.
    principal = 100_000
    annual_rate = 10.0
    tenure = 12
    prepay_month = 6

    sched = amortisation_schedule(principal, annual_rate, tenure)
    bal = sched[prepay_month - 1]["balance"]

    result = prepayment_savings(
        principal,
        annual_rate,
        tenure,
        prepay_month=prepay_month,
        prepay_amount=bal + 1,  # larger than remaining balance
    )

    assert result["new_tenure"] == prepay_month
    assert result["months_saved"] == (tenure - prepay_month)  # saves all remaining months


def test_very_large_principal_does_not_overflow_and_is_finite() -> None:
    # Sanity test for numeric stability.
    e = emi(10**12, 8.5, 360)
    assert math.isfinite(e)
    assert e > 0


def test_compare_offers_sorts_by_total_cost() -> None:
    principal = 500_000
    offers = [
        {"bank": "A", "rate": 10.0, "tenure": 24, "processing_fee_pct": 1.0},
        {"bank": "B", "rate": 9.0, "tenure": 24, "processing_fee_pct": 3.0},
    ]
    out = compare_offers(principal, offers)
    assert len(out) == 2
    assert out[0]["total_cost"] <= out[1]["total_cost"]


def test_eligible_amount_zero_or_negative_capacity_is_zero() -> None:
    assert (
        eligible_amount(
            monthly_income=100_000, existing_emis=100_000, annual_rate=10.0, tenure_months=12
        )
        == 0.0
    )


def test_format_inr_grouping_and_sign() -> None:
    assert format_inr(12345678.0) == "₹1,23,45,678.00"
    assert format_inr(-12.3) == "-₹12.30"
