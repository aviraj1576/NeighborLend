# Scenario B damage-claim submission — 11 November 2026

The proposed **₹600.00 claim was already saved**. No new claim or decision was submitted to Scenario B during this work. Its deposit remains frozen for independent review; its captured payment, existing claims/audits and journals were preserved.

## Persisted state read before changes

| Field | Exact value |
| --- | --- |
| Booking | `b60689be-73b2-47f2-992c-87e03dcf6303` |
| Request | `8942f920-7ff1-4d8d-9153-470b9a57be0b` |
| Existing captured payment | `pay_TybRJOKvo9JNwF`, 250000 paise INR |
| Booking/payment/deposit | `disputed` / `captured` / `frozen` |
| Dispute ID | `2c147ba4-f2c2-4849-88b9-4e57f319c4c8` — **one row** |
| Claim status/version | **`raised`, version 3** |
| Proposed deduction | **60000 paise — ₹600.00** |
| Approved deduction | **null**, no reviewer or resolution recorded |
| Borrower response | Not yet recorded; `borrower_accepted=false` |
| Origin | `return_rejection` |
| Return state | `return_photos_uploaded`; borrower returned_at recorded; return_confirmed_at/by null |
| Financial position | ₹2,000.00 frozen; actual deduction ₹0.00; refunded ₹0.00; no refund intent |
| Journals | One balanced funding journal and one balanced deposit-freeze journal; no settlement |

“Reject - Start Dispute” succeeded at **02:05:06 IST** and was repeated three more times. Two identical ₹600 claim-submission audits at **02:08:07** and **02:08:13 IST** recorded versions 2 and 3 of the same claim. They did not create duplicate dispute rows or another freeze journal. All four rejection audits and both historical claim-submission audits were retained.

The saved description is nonempty. The records prove that the submissions committed; they do not retain the historical browser response codes or a HAR. No historical request was replayed to reconstruct missing evidence.

## Confirmed defects and fixes

1. **No success acknowledgement:** the component discarded the successful POST response and waited for refresh without displaying confirmation. It now displays the server-acknowledged amount immediately, shows the saved version persistently, and pre-fills the existing claim for intentional revisions.
2. **Duplicate revisions:** identical requests always incremented claim_version and appended another audit. The serialized backend now acknowledges an identical open claim without changing its version or posting another audit. Actual amount/reason/reference changes still produce a new version, preserving stale-consent protection. Existing accepted/escalated/resolved claim restrictions remain enforced.
3. **Repeated return rejection:** a repeated rejection appended another decision audit even though the deposit was already frozen. An already-recorded open rejection now returns the current state. Claim edits continue through the claim endpoint. No historical audit was removed.
4. **Misleading return status:** return rejection freezes the financial state while the physical photo stage remains `return_photos_uploaded`. The page previously rendered that stage alone, showing “Awaiting Lender Confirmation” and clean-return/reject buttons despite an existing dispute. The page now combines the returned-item stage with the persisted dispute. It shows **Return reported — condition disputed; independent human review pending**, hides obsolete clean-return/reject controls, and distinguishes a later recorded reviewer decision from review still pending. No persisted state was rewritten to force a new handover label.
5. **Refresh and failure handling:** an acknowledged claim is applied to the UI before GET refresh. A failed refresh leaves “Claim saved” visible with a separate refresh warning. Earlier in-flight GET responses cannot replace newer state. Claim operations and refresh reads have bounded timeouts. A synchronous in-flight guard prevents double clicks from issuing two requests. Loading uses `aria-busy` and visible labels and resets in `finally`.
6. **Validation feedback:** FastAPI 422 detail arrays are formatted as readable field messages instead of being passed as objects to React. Permission errors remain explicit. A network error advises refreshing persisted claim status before retrying because the server may already have saved it.

The booking ownership checks, lender-only submission, integer-paise/deposit bounds, return eligibility, independent administrator authorization and frozen-liability accounting remain intact. No payment/refund dispatch path was added or relaxed.

## Verification

- Before the backend fix, the focused regressions reproduced **3 failures**: duplicate request version increments, repeated return-rejection audits, and concurrent identical revisions. Seven other validation/role cases passed.
- After the fix, the new claim regressions plus the existing payment regressions passed **46 tests**. The new cases exercise authenticated real API routes against disposable SQLite databases, including ₹600 on a ₹2,000 deposit, invalid reason/reference/amount responses, unauthorized roles, concurrent duplicates, genuine revision and stale consent.
- Browser verification signed in normally as the existing fixture lender and read Scenario B. Booking/rental/handover reads returned **HTTP 200**. The updated page displayed the existing saved version 3 claim and disputed return; both obsolete return buttons were absent. No actual Scenario B claim, return or deduction request was sent.
- A separate browser harness used explicitly synthetic props and an intercepted **`/__claim_test__/api/disputes/raise`** URL, which is not a real application mutation endpoint. It checked **200** acknowledgement, one request after a double click, **403/422** error rendering, loading reset and retained acknowledgement after refresh failure. Captured payload: booking ID, **60000** proposed paise and nonempty reason; no approved amount or refund field.
- Final frontend suite: **40 passed**, including saved-claim display, error formatting, disputed-return gating, reviewed-return labels and borrower-response status. Production build, payment ESLint/Prettier checks, changed backend Ruff checks and `git diff --check` passed.
- Complete backend regression suite: **289 passed, 3 skipped** in 310.97 seconds. The three skips require a dedicated local `PAYMENT_TEST_POSTGRES_URL`; PostgreSQL behavior was not newly verified. SQLite tests never access the existing sandbox database. Final runtime/preservation status is retained with the evidence below.
- **Activation and preservation passed:** only the validated owned controller/API/webhook-proxy stack was reloaded against the exact existing database, without migration. React and the tunnel were preserved. All existing table-row hashes and credential hashes match the pre-change baseline, including Scenario A's processed refund, Scenario B's captured payment and version 3 claim, the original ₹1 booking, and every journal/audit row. Private API, proxy isolation and React availability checks passed. No Scenario B claim or financial gateway mutation was submitted during activation.

## Precise next actions

Open [Scenario B](http://127.0.0.1:5175/borrow-requests/8942f920-7ff1-4d8d-9153-470b9a57be0b) under the appropriate existing fixture login.

1. **Lender:** refresh the page and verify **Saved claim ₹600.00, version 3** and frozen deposit. No resubmission or repeat rejection is needed. Use the pre-filled revision form only if the amount, description or evidence really needs changing; a real revision will require the borrower to review the new version.
2. **Borrower:** inspect the saved claim and return evidence, then record **Agree to exact claimed amount** or **Disagree — keep deposit frozen** as appropriate. This is a response to version 3, not deduction authorization. The deposit remains frozen either way.
3. **Independent administrator:** sign in with the separate administrator fixture and use [Payment review](http://127.0.0.1:5175/payment-review) to open Scenario B. Review the return photographs, claim and borrower response. Only if the evidence supports ₹600, enter **600** under **Administrator approved deduction (₹)**, supply a specific resolution reason and explicitly click **Record administrator settlement decision**. The system must not choose or approve that amount automatically. If ₹600 is approved, the resulting allocation is ₹1,400 deposit refund, ₹500 retained rental and ₹600 simulated compensation. Gateway refund execution remains a separate explicitly approved action and was not performed here.

## Changed files and evidence

Backend: `app/services/payments.py`; new `tests/test_damage_claim_workflow.py`.

Frontend: `src/components/DisputeResolutionModal.jsx`, `EscrowStatusCard.jsx`, `paymentFlow.js`, `payments.test.js`, and `src/pages/BorrowRequestDetail.jsx`.

Ignored evidence directory: `backend/.payment-verification/finalization-20261111/`. Files include `scenario-b-claim-baseline.json`, `scenario-b-claim-final.json`, `scenario-b-claim-browser.json`, `scenario-b-claim-live-ui.png`, `claim-before.xml`, `claim-after.xml`, `claim-full.xml`, `claim-frontend-tests.txt` and the final preservation/runtime report. The read-only inspection and browser scripts are retained there for reproduction. Sensitive credential values are excluded from reports.

No actual claim submission, deduction approval, gateway refund/payment mutation, database migration, EP v3 AI integration, Git branch, commit or push was performed. Normal fixture login and authenticated read requests were used for browser inspection; mutation tests used disposable databases or intercepted non-application URLs.
