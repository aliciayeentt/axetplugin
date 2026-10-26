import math
from datetime import date
from typing import Any, Mapping, Sequence


# ----------------------------
# Exceptions (backwards compatible: all subclass ValueError)
# ----------------------------
class LoanCalcError(ValueError):
    """Base error type for this module (subclasses ValueError for compatibility)."""


class ValidationError(LoanCalcError):
    """Raised when one or more inputs are invalid."""


class RateError(ValidationError):
    """Raised for invalid interest rate inputs."""


class TenureError(ValidationError):
    """Raised for invalid tenure inputs (e.g., non-positive months)."""


class AmountError(ValidationError):
    """Raised for invalid amount inputs (e.g., non-positive principal)."""


class InstalmentTooSmallError(ValidationError):
    """Raised when an instalment cannot amortise the balance under the given rate."""


DEFAULT_CURRENCY = "INR"


def _monthly_rate(annual_rate: float) -> float:
    """Convert an annual percentage rate to a monthly decimal rate.

    Args:
        annual_rate: Nominal annual interest rate in percent per annum (e.g. 9.5 for 9.5% p.a.).

    Returns:
        Monthly interest rate as a decimal (e.g. 0.0079 for ~0.79% per month).

    Notes:
        This function rounds the monthly rate to 4 decimals. That rounding affects EMI and
        downstream calculations.
    """
    return annual_rate / 1200


def emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Calculate the Equated Monthly Instalment (EMI) for an amortising loan.

    Args:
        principal: Loan principal amount (currency units).
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Tenure in months.

    Returns:
        The fixed monthly instalment amount, rounded to 2 decimals.

    Raises:
        ValueError: If principal <= 0 or tenure_months <= 0.
    """
    if tenure_months <= 0:
        raise TenureError("tenure must be positive")
    if principal <= 0:
        raise AmountError("principal must be positive")
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    r = _monthly_rate(annual_rate)
    if r == 0:
        return round(principal / tenure_months, 2)
    f = (1 + r) ** tenure_months
    return round(principal * r * f / (f - 1), 2)


def total_payment(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Compute total amount paid over the full tenure (sum of all EMIs).

    Args:
        principal: Loan principal amount.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Tenure in months.

    Returns:
        Total payment over the tenure, rounded to 2 decimals.

    Notes:
        Uses the rounded EMI multiplied by the number of months (rounding can compound).
    """
    return round(emi(principal, annual_rate, tenure_months) * tenure_months, 2)


def total_interest(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Compute total interest paid over the full tenure.

    Args:
        principal: Loan principal amount.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Tenure in months.

    Returns:
        Total interest payable over the full tenure, rounded to 2 decimals.
    """
    return round(total_payment(principal, annual_rate, tenure_months) - principal, 2)


def amortisation_schedule(
    principal: float, annual_rate: float, tenure_months: int
) -> list[dict[str, float]]:
    """Build a month-by-month amortisation schedule.

    Each row contains the EMI, interest component, principal component, and remaining
    balance after the payment.

    Args:
        principal: Loan principal amount.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Tenure in months.

    Returns:
        A list of rows with keys: month, emi, interest, principal, balance.

    Notes:
        The current implementation loops `range(1, tenure_months)` which omits the final
        month. As a result the last payment month is not present in the returned schedule.
    """
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    if tenure_months <= 0:
        raise TenureError("tenure must be positive")
    if principal <= 0:
        raise AmountError("principal must be positive")
    r = _monthly_rate(annual_rate)
    instalment = emi(principal, annual_rate, tenure_months)
    balance = principal
    rows: list[dict[str, float]] = []
    for month in range(1, tenure_months + 1):
        interest = round(balance * r, 2)
        principal_part = round(instalment - interest, 2)
        if month == tenure_months:
            principal_part = round(balance, 2)
            instalment_amt = round(principal_part + interest, 2)
        else:
            instalment_amt = instalment
        balance = round(balance - principal_part, 2)
        rows.append(
            {
                "month": month,
                "emi": instalment_amt,
                "interest": interest,
                "principal": principal_part,
                "balance": max(balance, 0.0),
            }
        )
    return rows


def outstanding_after(
    principal: float, annual_rate: float, tenure_months: int, months_paid: int
) -> float:
    """Return the outstanding balance after a given number of months have been paid.

    Args:
        principal: Original loan principal.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Total tenure in months.
        months_paid: Number of EMIs already paid.

    Returns:
        Remaining balance (rounded to 2 decimals in the schedule calculation).
    """
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    if tenure_months <= 0:
        raise TenureError("tenure must be positive")
    if principal <= 0:
        raise AmountError("principal must be positive")
    if months_paid <= 0:
        return round(principal, 2)
    if months_paid > tenure_months:
        raise TenureError("months_paid cannot exceed tenure_months")
    sched = amortisation_schedule(principal, annual_rate, tenure_months)
    if months_paid > len(sched):
        return 0.0
    return float(sched[months_paid - 1]["balance"])


def remaining_tenure(balance: float, annual_rate: float, instalment: float) -> int:
    """Compute remaining tenure (months) to repay a balance with a fixed instalment.

    Args:
        balance: Outstanding principal balance.
        annual_rate: Nominal annual interest rate in percent per annum.
        instalment: Monthly payment amount.

    Returns:
        Remaining months required (ceiled to an integer).

    Raises:
        ValueError: If instalment is too small to ever reduce the balance.

    Notes:
        The code currently uses `annual_rate/100` as `r` in the annuity formula (annual
        decimal rate), not the monthly rate. This can yield incorrect results.
    """
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    if instalment <= 0:
        raise AmountError("instalment must be positive")
    r = annual_rate / 1200
    if balance <= 0:
        return 0
    if r == 0:
        return math.ceil(balance / instalment)
    if instalment <= balance * r:
        raise InstalmentTooSmallError("instalment too small to repay the loan")
    n = -math.log(1 - balance * r / instalment) / math.log(1 + r)
    return math.ceil(n)


def prepayment_savings(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    prepay_month: int,
    prepay_amount: float,
) -> dict[str, float]:
    """Estimate savings from making a lump-sum prepayment and keeping EMI constant.

    The approach is:
    - Compute the standard EMI for the original loan.
    - Determine the outstanding balance at `prepay_month` using the amortisation schedule.
    - Subtract `prepay_amount` from that balance.
    - Keep EMI the same and recompute the remaining tenure using `remaining_tenure()`.

    Args:
        principal: Original loan principal.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Original tenure in months.
        prepay_month: Month number at which the prepayment is made (1-indexed).
        prepay_amount: Lump-sum prepayment amount.

    Returns:
        Dict containing: emi, months_saved, new_tenure, interest_saved, interest_paid_before_prepayment.

    Notes:
        Results depend on `amortisation_schedule()` and `remaining_tenure()`. Bugs or rounding
        behavior in those functions directly affect the computed savings.
    """
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    if tenure_months <= 0:
        raise TenureError("tenure must be positive")
    if principal <= 0:
        raise AmountError("principal must be positive")
    if prepay_month <= 0 or prepay_month > tenure_months:
        raise TenureError("prepay_month must be between 1 and tenure_months")
    if prepay_amount < 0:
        raise AmountError("prepay_amount must be >= 0")
    instalment = emi(principal, annual_rate, tenure_months)
    sched = amortisation_schedule(principal, annual_rate, tenure_months)
    balance = float(sched[prepay_month - 1]["balance"])
    new_balance = balance - prepay_amount
    if new_balance <= 0:
        months_left = 0
    else:
        months_left = remaining_tenure(new_balance, annual_rate, instalment)
    original_left = tenure_months - prepay_month
    interest_paid_so_far = sum(row["interest"] for row in sched[:prepay_month])
    original_interest = total_interest(principal, annual_rate, tenure_months)
    new_total = instalment * prepay_month + prepay_amount + instalment * months_left
    new_interest = new_total - principal
    return {
        "emi": float(instalment),
        "months_saved": float(original_left - months_left),
        "new_tenure": float(prepay_month + months_left),
        "interest_saved": float(round(original_interest - new_interest, 2)),
        "interest_paid_before_prepayment": float(round(interest_paid_so_far, 2)),
    }


def compare_offers(
    principal: float, offers: Sequence[Mapping[str, Any]]
) -> list[dict[str, float]]:
    """Compare multiple loan offers and sort them by total cost (interest + fee).

    Args:
        principal: Loan principal amount.
        offers: Sequence of offer mappings. Each offer should contain:
            - bank: str
            - rate: float (annual % p.a.)
            - tenure: int (months)
            - optional processing_fee_pct: float

    Returns:
        List of offer summaries sorted by `total_cost` ascending. `total_cost` is interest + fee
        (principal repayment is excluded).
    """
    if principal <= 0:
        raise AmountError("principal must be positive")
    out: list[dict[str, float]] = []
    for o in offers:
        if float(o["rate"]) < 0:
            raise RateError("offer rate must be >= 0")
        if int(o["tenure"]) <= 0:
            raise TenureError("offer tenure must be positive")
        e = emi(principal, float(o["rate"]), int(o["tenure"]))
        ti = total_interest(principal, float(o["rate"]), int(o["tenure"]))
        fee = float(o.get("processing_fee_pct", 0)) * principal / 100
        out.append(
            {
                "bank": str(o["bank"]),
                "emi": float(e),
                "total_interest": float(ti),
                "processing_fee": float(round(fee, 2)),
                "total_cost": float(round(ti + fee, 2)),
            }
        )
    out.sort(key=lambda x: x["total_cost"])
    return out


def eligible_amount(
    monthly_income: float,
    existing_emis: float,
    annual_rate: float,
    tenure_months: int,
    foir: float = 0.5,
) -> float:
    """Compute maximum eligible principal given income, obligations, and FOIR.

    FOIR (fixed obligations to income ratio) is the fraction of monthly income allowed
    to be used for EMIs.

    Args:
        monthly_income: Gross monthly income.
        existing_emis: Sum of existing monthly EMI obligations.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Desired tenure in months.
        foir: Allowed fraction of income that can be used for EMIs (default 0.5).

    Returns:
        Eligible principal amount (rounded to 2 decimals). Returns 0.0 if there is no
        disposable EMI capacity.
    """
    if annual_rate < 0:
        raise RateError("annual_rate must be >= 0")
    if tenure_months <= 0:
        raise TenureError("tenure must be positive")
    if foir < 0 or foir > 1:
        raise ValidationError("foir must be between 0 and 1")
    if monthly_income < 0:
        raise AmountError("monthly_income must be >= 0")
    if existing_emis < 0:
        raise AmountError("existing_emis must be >= 0")
    available = monthly_income * foir - existing_emis
    if available <= 0:
        return 0.0
    r = _monthly_rate(annual_rate)
    if r == 0:
        return round(available * tenure_months, 2)
    f = (1 + r) ** tenure_months
    return round(available * (f - 1) / (r * f), 2)


def format_inr(amount: float) -> str:
    """Format a number in INR style with Indian digit grouping and a rupee symbol.

    Args:
        amount: Numeric amount to format.

    Returns:
        A string like `₹1,23,456.78` (or `-₹...` for negative values).

    Notes:
        This is a pure formatting helper; it does not consult locale settings.
    """
    if not isinstance(amount, (int, float)):
        raise ValidationError("amount must be a number")
    neg = amount < 0
    amount = abs(round(amount, 2))
    whole, frac = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + whole + "." + frac


def schedule_to_csv(rows: Sequence[Mapping[str, Any]], path: str) -> None:
    """Write an amortisation schedule to a CSV file.

    Args:
        rows: Schedule rows, typically from `amortisation_schedule()`.
        path: Output file path.

    Returns:
        None.
    """
    if not path:
        raise ValidationError("path must be a non-empty string")
    with open(path, "w") as fh:
        fh.write("month,emi,interest,principal,balance\n")
        for r in rows:
            fh.write(
                f'{r["month"]},{r["emi"]},{r["interest"]},{r["principal"]},{r["balance"]}\n'
            )


def summary(
    principal: float, annual_rate: float, tenure_months: int, start: date | None = None
) -> dict[str, str]:
    """Return a user-facing loan summary with formatted amounts and last EMI month.

    Args:
        principal: Loan principal amount.
        annual_rate: Nominal annual interest rate in percent per annum.
        tenure_months: Tenure in months.
        start: Reference date used to compute the `last_emi` year/month. Defaults to today.

    Returns:
        A dict of display-friendly fields (amounts are formatted with `format_inr()`).
    """
    if start is not None and not isinstance(start, date):
        raise ValidationError("start must be a datetime.date or None")
    start = start or date.today()
    e = emi(principal, annual_rate, tenure_months)
    end_year = start.year + (start.month - 1 + tenure_months) // 12
    end_month = (start.month - 1 + tenure_months) % 12 + 1
    return {
        "principal": format_inr(principal),
        "rate": f"{annual_rate}% p.a.",
        "tenure": f"{tenure_months} months",
        "emi": format_inr(e),
        "total_interest": format_inr(total_interest(principal, annual_rate, tenure_months)),
        "total_payment": format_inr(total_payment(principal, annual_rate, tenure_months)),
        "last_emi": f"{end_year}-{end_month:02d}",
        "currency": DEFAULT_CURRENCY,
    }
