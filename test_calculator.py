import math
from datetime import date

import pytest

from loan_calc.calculator import (
    AmountError,
    InstalmentTooSmallError,
    RateError,
    TenureError,
    ValidationError,
    amortisation_schedule,
    compare_offers,
    eligible_amount,
    emi,
    format_inr,
    outstanding_after,
    prepayment_savings,
    remaining_tenure,
    summary,
    total_interest,
    total_payment,
)


def test_emi_rejects_non_positive_principal() -> None:
    # Backwards compatible: custom exceptions subclass ValueError.
    with pytest.raises(ValueError):
        emi(0, 10.0, 12)
    with pytest.raises(AmountError):
        emi(0, 10.0, 12)


def test_emi_rejects_non_positive_tenure() -> None:
    with pytest.raises(ValueError):
        emi(100_000, 10.0, 0)
    with pytest.raises(TenureError):
        emi(100_000, 10.0, 0)


def test_emi_zero_interest_is_straight_line() -> None:
    # 0% interest should simply split principal over the tenure.
    assert emi(120_000, 0.0, 12) == 10_000.00


def test_total_payment_zero_interest_equals_principal() -> None:
    assert total_payment(120_000, 0.0, 12) == 120_000.00


def test_total_interest_zero_interest_is_zero() -> None:
    assert total_interest(120_000, 0.0, 12) == 0.00


def test_emi_rejects_negative_rate() -> None:
    with pytest.raises(RateError):
        emi(100_000, -0.1, 12)


def test_outstanding_after_rejects_months_paid_gt_tenure() -> None:
    with pytest.raises(TenureError):
        outstanding_after(100_000, 10.0, 12, 13)


def test_remaining_tenure_rejects_non_positive_instalment() -> None:
    with pytest.raises(AmountError):
        remaining_tenure(100_000, 10.0, 0.0)


def test_remaining_tenure_raises_custom_instalment_too_small() -> None:
    with pytest.raises(InstalmentTooSmallError):
        remaining_tenure(100_000, 12.0, 10.0)  # far too small


def test_prepayment_savings_validates_inputs() -> None:
    with pytest.raises(TenureError):
        prepayment_savings(100_000, 10.0, 12, prepay_month=0, prepay_amount=1000)
    with pytest.raises(AmountError):
        prepayment_savings(100_000, 10.0, 12, prepay_month=1, prepay_amount=-1)


def test_eligible_amount_validates_foir_range() -> None:
    with pytest.raises(ValidationError):
        eligible_amount(100_000, 0, 10.0, 12, foir=1.5)


def test_format_inr_rejects_non_numeric() -> None:
    with pytest.raises(ValidationError):
        format_inr("not-a-number")  # type: ignore[arg-type]


def test_schedule_to_csv_rejects_empty_path(tmp_path) -> None:
    from loan_calc.calculator import schedule_to_csv
    with pytest.raises(ValidationError):
        schedule_to_csv([], "")
    # sanity: works with a valid path
    p = tmp_path / "sched.csv"
    schedule_to_csv([], str(p))
    assert p.exists()


def test_summary_validates_start_type() -> None:
    with pytest.raises(ValidationError):
        summary(100_000, 10.0, 12, start="2026-01-01")  # type: ignore[arg-type]
    # sanity: accepts date
    out = summary(100_000, 10.0, 12, start=date(2026, 1, 1))
    assert "emi" in out


def test_emi_one_month_tenure_is_principal_plus_one_month_interest() -> None:
    # EMI formula degenerates to: P*(1+r) for n=1
    principal = 100_000
    annual_rate = 12.0
    r = round(annual_rate / 1200, 4)
    assert emi(principal, annual_rate, 1) == round(principal * (1 + r), 2)


def test_monthly_rate_should_not_be_rounded_early() -> None:
    # Seeded bug: `_monthly_rate()` rounds to 4 decimals. This can change EMI.
    # This test asserts the *expected* behavior: use the unrounded monthly rate
    # in computations (round only for display).
    principal = 2_500_000.0
    annual_rate = 9.65
    tenure_months = 360

    r_unrounded = annual_rate / 1200.0
    f = (1 + r_unrounded) ** tenure_months
    expected = round(principal * r_unrounded * f / (f - 1), 2)

    assert emi(principal, annual_rate, tenure_months) == expected


def test_amortisation_schedule_length_is_full_tenure_months() -> None:
    # Expected: schedule should include one row per month of tenure.
    # Current code is suspected to omit the last month (seeded bug).
    sched = amortisation_schedule(100_000, 10.0, 12)
    assert len(sched) == 12


def test_outstanding_after_months_paid_le_zero_returns_principal() -> None:
    assert outstanding_after(100_000, 10.0, 12, 0) == 100_000.00


def test_outstanding_after_full_tenure_is_zero() -> None:
    # After paying the full tenure, outstanding should be ~0.
    # If amortisation is missing the final row, this can be wrong.
    assert outstanding_after(100_000, 10.0, 12, 12) == 0.0


def test_remaining_tenure_zero_balance_is_zero() -> None:
    assert remaining_tenure(0.0, 10.0, 1000.0) == 0


def test_remaining_tenure_zero_rate_uses_simple_division() -> None:
    assert remaining_tenure(10_000.0, 0.0, 1000.0) == 10


def test_remaining_tenure_matches_monthly_rate_math() -> None:
    # Expected formula uses monthly rate (annual_rate/1200), not annual_rate/100.
    # Current code is suspected to use the wrong rate (seeded bug).
    balance = 100_000.0
    annual_rate = 12.0
    instalment = 10_000.0
    r = annual_rate / 1200.0
    expected = math.ceil(-math.log(1 - balance * r / instalment) / math.log(1 + r))
    assert remaining_tenure(balance, annual_rate, instalment) == expected


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
