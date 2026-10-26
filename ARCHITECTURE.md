# loan-calc architecture (calculator.py)

This repo is a small, mostly-functional loan mathematics module. The core logic lives in:

- `loan-calc/loan_calc/calculator.py` — EMI, totals, amortisation schedule, prepayment savings, offer comparison, eligibility, formatting, and export helpers.
- `loan-calc/cli.py` — CLI wrapper (not analysed in this document yet; this file describes functions in `calculator.py`).

## Conventions and units

Most functions use:

- `principal`: loan amount in currency units (e.g., INR).
- `annual_rate`: nominal interest rate in percent per annum (e.g., `9.5` means 9.5% p.a.).
- `tenure_months`: loan tenure in **months**.
- EMI (equated monthly instalment) is assumed constant for standard amortising loans.

Rounding: many functions round to 2 decimals (money) *per month* and/or for final outputs. This can cause slight differences vs bank schedules that carry more precision internally.

---

## Module constants

### `DEFAULT_CURRENCY = "INR"`
Used only by `summary()` as a label in returned output.

---

## Helper functions

### `_monthly_rate(annual_rate)`
**Purpose:** Convert annual percentage rate to a monthly decimal interest rate.

**Inputs:**
- `annual_rate` (float): percentage per annum.

**Returns:**
- `r` (float): monthly rate as a decimal.

**Implementation details:**
- Computes `annual_rate / 1200` (i.e., `annual_rate / 100 / 12`).
- **Does not round** the monthly rate inside this helper.

**Notes / risk:**
- Earlier versions of this code rounded the monthly rate to 4 decimals, which can change EMI/schedule results on long tenures. The current implementation keeps full precision and rounds only monetary outputs.

---

## Loan payment calculations

### `emi(principal, annual_rate, tenure_months)`
**Purpose:** Compute the fixed monthly EMI for a standard amortising loan.

**Validations:**
- `tenure_months` must be positive.
- `principal` must be positive.

**Algorithm:**
- Let `r = _monthly_rate(annual_rate)`.
- If `r == 0`: EMI is `principal / tenure_months`.
- Else use standard EMI formula:

  `EMI = P * r * (1+r)^n / ((1+r)^n - 1)`

**Returns:**
- EMI rounded to 2 decimals.

---

### `total_payment(principal, annual_rate, tenure_months)`
**Purpose:** Total of all EMIs paid over the loan tenure.

**Implementation:**
- `emi(...) * tenure_months`

**Returns:**
- Total payment rounded to 2 decimals.

**Notes:**
- Since `emi()` is already rounded to 2 decimals, multiplying by months compounds rounding error vs computing with higher precision.

---

### `total_interest(principal, annual_rate, tenure_months)`
**Purpose:** Total interest paid over the full loan term.

**Implementation:**
- `total_payment(...) - principal`

**Returns:**
- Total interest rounded to 2 decimals.

---

## Amortisation / balances

### `amortisation_schedule(principal, annual_rate, tenure_months)`
**Purpose:** Generate a month-by-month amortisation schedule (EMI breakdown and remaining balance).

**Returns:**
- A list of dict rows, each row:

  ```python
  {
    "month": <int>,
    "emi": <float>,
    "interest": <float>,
    "principal": <float>,
    "balance": <float>,
  }
  ```

**Algorithm overview:**
- `r = _monthly_rate(annual_rate)`
- `instalment = emi(...)`
- Start `balance = principal`
- For each month:
  - `interest = balance * r` (rounded to 2)
  - `principal_part = instalment - interest` (rounded to 2)
  - Update `balance -= principal_part` (rounded to 2)
  - Clamp `balance` in output to `max(balance, 0.0)`

**Implementation details:**
- The loop is:

  ```python
  for month in range(1, tenure_months + 1):
  ```

  This generates **one row per month**, including the final month. The last-month adjustment branch (`if month == tenure_months`) is now reachable.

  Consequences:
  - Schedule length is `tenure_months`.
  - The final payoff month is present.

---

### `outstanding_after(principal, annual_rate, tenure_months, months_paid)`
**Purpose:** Estimate remaining outstanding principal after `months_paid` EMIs have been paid.

**Behavior:**
- If `months_paid <= 0`, returns the original principal.
- Builds full schedule via `amortisation_schedule(...)`.
- If `months_paid > len(sched)`, returns `0.0` (assumes fully paid).
- Else returns `sched[months_paid - 1]["balance"]`.

**Notes / risk:**
- Because `amortisation_schedule()` currently returns `tenure_months-1` rows, the `months_paid > len(sched)` branch can incorrectly return `0.0` for the true last month, and balances may be off near maturity.

---

### `remaining_tenure(balance, annual_rate, instalment)`
**Purpose:** Compute how many months are required to repay a given `balance` with a fixed monthly payment (`instalment`) at a given rate.

**Inputs:**
- `balance`: outstanding principal.
- `annual_rate`: percent per annum.
- `instalment`: intended monthly payment.

**Returns:**
- Integer number of months (`ceil`).

**Algorithm as implemented:**
- `r = annual_rate / 1200`
- If `balance <= 0`: `0`
- If `r == 0`: `ceil(balance / instalment)`
- If `instalment <= balance * r`: raise (payment too small)
- Else:

  `n = -log(1 - balance*r/instalment) / log(1 + r)`

  then `ceil(n)`.

**Important implementation detail:**
- This function uses the **monthly** rate (`annual_rate / 1200`) in the annuity formula, which is the correct unit for a monthly instalment calculation.

---

## Prepayment calculations

### `prepayment_savings(principal, annual_rate, tenure_months, prepay_month, prepay_amount)`
**Docstring:** “Keep the same EMI after a lump-sum prepayment and shorten the tenure.”

**Purpose:** Simulate a lump-sum prepayment in month `prepay_month`, keep the EMI constant, and compute how much tenure and interest are saved.

**Steps:**
1. Compute the original `instalment = emi(principal, annual_rate, tenure_months)`.
2. Build original schedule `sched = amortisation_schedule(...)`.
3. Look up outstanding `balance` after `prepay_month` from the schedule:

   `balance = sched[prepay_month - 1]["balance"]`

4. Apply prepayment: `new_balance = balance - prepay_amount`.
5. Compute `months_left`:
   - If `new_balance <= 0`, months left is 0.
   - Else `remaining_tenure(new_balance, annual_rate, instalment)`.
6. Compute:
   - `original_left = tenure_months - prepay_month`
   - `interest_paid_so_far = sum(interest for months up to prepay_month)`
   - `original_interest = total_interest(principal, annual_rate, tenure_months)`
   - `new_total = instalment * prepay_month + prepay_amount + instalment * months_left`
   - `new_interest = new_total - principal`

**Returns:**
```python
{
  "emi": instalment,
  "months_saved": original_left - months_left,
  "new_tenure": prepay_month + months_left,
  "interest_saved": round(original_interest - new_interest, 2),
  "interest_paid_before_prepayment": round(interest_paid_so_far, 2),
}
```

**Notes / risks:**
- Depends on `amortisation_schedule()` for the balance at `prepay_month`; the schedule missing the final month can skew results and can raise index errors if `prepay_month` equals `tenure_months`.
- Depends on `remaining_tenure()`; the annual-vs-monthly rate bug makes savings wrong for many loans.
- `interest_paid_so_far` uses rounded monthly interest, which may differ from an unrounded internal amortisation.

---

## Offer comparison

### `compare_offers(principal, offers)`
**Purpose:** Compare multiple loan offers and sort by total cost (interest + processing fee).

**Inputs:**
- `principal` (float)
- `offers` (list[dict]) where each offer expects:
  - `bank` (str)
  - `rate` (float, annual % p.a.)
  - `tenure` (int, months)
  - optional `processing_fee_pct` (float)

**Behavior:**
- For each offer:
  - Compute `emi` and `total_interest`.
  - Compute `fee = processing_fee_pct * principal / 100`.
  - Build summary dict with `total_cost = total_interest + processing_fee`.
- Sort ascending by `total_cost`.

**Returns:**
- Sorted list of offer summaries.

**Note:**
- Does not include principal in `total_cost` (by design). It compares the *cost of borrowing* excluding principal repayment.

---

## Eligibility calculator

### `eligible_amount(monthly_income, existing_emis, annual_rate, tenure_months, foir=0.5)`
**Purpose:** Compute the maximum principal eligible given an allowable EMI budget.

**Concept:** FOIR = fixed obligations to income ratio (portion of income usable for EMIs).

**Steps:**
1. Compute monthly EMI budget:

   `available = monthly_income * foir - existing_emis`

2. If `available <= 0`, return 0.
3. Treat `available` as the EMI and invert the EMI formula to solve for principal `P`:
   - If rate is 0: `P = available * tenure_months`
   - Else:

     `P = EMI * ((1+r)^n - 1) / (r * (1+r)^n)`

**Returns:**
- Eligible principal rounded to 2 decimals.

---

## Formatting and export

### `format_inr(amount)`
**Purpose:** Format a number into an INR-style string with the rupee symbol and Indian digit grouping.

**Behavior:**
- Keeps sign.
- Rounds to 2 decimals.
- Applies grouping like `12,34,56,789.00`.
- Returns string like `₹1,23,456.78` or `-₹1,23,456.78`.

**Notes:**
- Purely formatting; does not consult locale.

---

### `schedule_to_csv(rows, path)`
**Purpose:** Save amortisation schedule rows to CSV on disk.

**Inputs:**
- `rows`: list of schedule dicts as produced by `amortisation_schedule()`.
- `path`: file path to write.

**Behavior:**
- Writes header `month,emi,interest,principal,balance`
- Writes each row as a line.

**Notes / risk:**
- Opens file with default encoding and newline handling; on Windows this can introduce `\r\n` line endings automatically (usually fine).
- Does not quote values; assumes numbers only.

---

## Summary helper

### `summary(principal, annual_rate, tenure_months, start=None)`
**Purpose:** Produce a human-friendly loan summary, including formatted amounts and the last EMI month.

**Inputs:**
- `start`: `datetime.date` used as a reference month for computing `last_emi` (defaults to `date.today()`). The code does not enforce whether this is the disbursal month or the first EMI month.

**Behavior:**
- Computes EMI, total interest, total payment using earlier helpers.
- Computes the calendar month of the last EMI:
  - `end_year = start.year + (start.month - 1 + tenure_months) // 12`
  - `end_month = (start.month - 1 + tenure_months) % 12 + 1`

**Returns:**
```python
{
  "principal": "₹...",
  "rate": "<annual_rate>% p.a.",
  "tenure": "<tenure_months> months",
  "emi": "₹...",
  "total_interest": "₹...",
  "total_payment": "₹...",
  "last_emi": "YYYY-MM",
  "currency": "INR",
}
```

**Notes:**
- The code computes `last_emi` as `start` shifted by `tenure_months` months (not `tenure_months - 1`). Whether that is off-by-one depends on what `start` is intended to represent; this function does not document that meaning.

---

## Seeded bugs that were found & fixed

The following issues were present in the starter repo and have now been fixed in `calculator.py`:

1. `amortisation_schedule()` had an off-by-one loop and omitted the final month (now fixed by iterating through `tenure_months + 1`).
2. `remaining_tenure()` used the annual decimal rate instead of the monthly rate (now fixed to use `annual_rate / 1200`).
3. `_monthly_rate()` rounded the monthly rate too early (now fixed to keep full precision and avoid early rounding).
