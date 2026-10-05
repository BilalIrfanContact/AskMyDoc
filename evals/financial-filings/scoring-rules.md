# Scoring rules for the financial filings eval

Decided before any AskMyDoc run on this corpus. Change a rule only for a reason provable without looking at results, and record the change and date here.

## 1. Numbers (decided 2026-09-27)

- A numeric answer passes when it rounds to the expected answer: tolerance is half of the last decimal place shown in the expected answer (93.86 accepts 93.855 to 93.865; 30.8% accepts 30.75% to 30.85%; 9,068 accepts 9,067.5 to 9,068.5).
- Units are converted before comparing ("$8.74 billion" equals "8,740 million").
- Commas, currency signs and trailing zeros are ignored when comparing ("$1,577", "1577.00" and "1,577 million" are the same).
- Numbers that must appear are listed per case in `key_values` (the answer, not its workings); all must match.
- When a case has `acceptable_answers`, the answer passes if it matches any one of them under the same rule. An option can be a list of values (one method's results); then all of them must match.
- Negatives written in brackets, like (0.6)%, read as negative. An unsigned number matches a negative expected value (the sign is often given in words); an explicitly signed one must match the sign.
- The scorer checks that the expected figure is stated, not which year or line item it is attached to. On 2026-10-05 every saved pass that states more than one amount (77 answers across runs 015–018 and the held-out run) was checked by hand; none passed through a figure given for another year or item.
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
- The grader's instructions and model are frozen before the first run; changes need a written reason. The grader model is `gpt-5.4-nano`, set by `OPENAI_GRADER_MODEL` separately from the app's `OPENAI_CHAT_MODEL`, and recorded in every report.
- A case may carry a `grader_note` that is shown to the grader (used once: Best Buy stores, where a clearly labelled US-only answer is also acceptable).
- After the first run, about 10 grader decisions are hand-checked and any errors noted.

## 4. "Answer 0" case: AES restructuring costs (decided 2026-09-27)

Applies only to `financebench_id_01319`.

- Passes: "0" or an equivalent statement that no restructuring costs are shown in the income statement, or AskMyDoc's standard insufficient-context fallback.
- Fails: any restructuring figure, including amounts taken from other pages of the filing (restructuring is mentioned on pages 94, 108 and 193, outside the income statement).

## 5. "Not in the document" cases

- Pass only when AskMyDoc returns its insufficient-context fallback; any answer fails.
- Reported separately from answerable cases.

## 6. Key corrections (2026-10-03)

These three were found because the app failed them, so they are not result-blind. Each is provable from the filing alone, and reports show the score under the original key next to the corrected one.

- `pdfqa_finqa_GIS_2018_06`: the key is now "$58.4 million". The table is headed "In Millions"; without the unit a correct "58.4 million" was read as 58,400,000. The original is kept in `original_expected_answer`.
- `financebench_id_01009` (PepsiCo geographies): a `grader_note` also accepts the filing's own list of PepsiCo's largest operations (United States, Mexico, Russia, Canada, China, United Kingdom, South Africa). The regions in the key stay acceptable.
- `financebench_id_00799` (Amcor quick ratio): `acceptable_answers` and a `grader_note` also accept the conservative quick ratio, (cash + trade receivables) / current liabilities, about 0.53 → 0.57, when the answer names that formula. The original `key_values` are unchanged.

## 7. Key correction (2026-10-04)

- `financebench_id_01328` (PepsiCo restructuring): `acceptable_answers` now also accepts 0. The question asks for restructuring costs "directly outlined" in the income statement and says to state 0 if they aren't; PepsiCo's Consolidated Statement of Income has no restructuring line, and the $411 million appears only in Note 3 and the cash flow statement. Both readings pass. Like the corrections in section 6, it was found because the app's answer failed, so reports keep the original-key score beside the corrected one.
