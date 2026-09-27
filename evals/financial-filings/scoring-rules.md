# Scoring rules for the financial filings eval

Decided before any AskMyDoc run on this corpus. Change a rule only for a reason provable without looking at results, and record the change and date here.

## 1. Numbers (decided 2026-09-27)

- A numeric answer passes when it rounds to the expected answer: tolerance is half of the last decimal place shown in the expected answer (93.86 accepts 93.855 to 93.865; 30.8% accepts 30.75% to 30.85%; 9,068 accepts 9,067.5 to 9,068.5).
- Units are converted before comparing ("$8.74 billion" equals "8,740 million").
- Commas, currency signs and trailing zeros are ignored when comparing ("$1,577", "1577.00" and "1,577 million" are the same).
- When a case has `acceptable_answers`, the answer passes if it matches any one of them under the same rule.
- This normalisation happens only inside the scorer. The app's answer is never changed, and results keep the original answer text.

## 2. Yes/no (decided 2026-09-27)

- Both the verdict and its support must pass; either one failing fails the question.
- The verdict must match the expected yes or no. The grader judges the verdict the answer implies ("Debt went down by $2.5bn" means "No"); it does not look for the literal words.
- If the expected answer includes a number, that number must pass rule 1.
- If the support is a written reason, it is graded under rule 3.
- Hedging without a verdict ("it depends", "probably", "possibly") fails.

## 3. Prose (decided 2026-09-27)

- A second model grades prose answers and the written reasons in yes/no answers, one question at a time.
- It sees only the question, the expected answer and AskMyDoc's answer; not the evidence, since the expected answers were verified against the PDFs.
- Pass requires all of: every key fact in the expected answer is present (strict: all listed facts, not just the main one; extra correct detail is fine), nothing contradicts the expected answer, and the company and period are right.
- Numbers inside prose are checked by rule 1, never by the grader.
- The grader's instructions and model are frozen before the first run; changes need a written reason.
- After the first run, about 10 grader decisions are hand-checked and any errors noted.

## 4. "Answer 0" case: AES restructuring costs (decided 2026-09-27)

Applies only to `financebench_id_01319`.

- Passes: "0" or an equivalent statement that no restructuring costs are shown in the income statement, or AskMyDoc's standard insufficient-context fallback.
- Fails: any restructuring figure, including amounts taken from other pages of the filing (restructuring is mentioned on pages 94, 108 and 193, outside the income statement).
