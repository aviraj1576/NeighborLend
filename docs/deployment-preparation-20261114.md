# Deployment preparation - 14 November 2026

This release packages the existing integration stabilization and Razorpay Test refund-reconciliation corrections. The explicit 35-file selection is in `push-files-20261114.txt`. It includes application code, regression tests, the isolated browser verifier, ignore rules and these two release files. Other local inspection scripts and historical operational reports are outside this selection.

## Included behavior

- Preserve rental payment status across refresh failures, lock financial controls until authoritative reads succeed, and show capture, deposit and cancellation amounts accurately.
- Restore independent administrator rental review and keep participant handover/return permissions separate from administrator permissions.
- Keep listing-specific chat context and use the backend's rating-eligibility decision.
- Reuse the existing YOLOE classifier through the listing-upload adapter and startup warmup. No classifier implementation, checkpoint, training or model asset changes are included.
- Inspect Razorpay payments and refund inventory using provider GETs; show external/excess refunds and block unsafe refund dispatch. Record administrator review separately from settlement authority, and preserve webhook replay protections and immutable journals.
- Distinguish recorded lender allocations from actual provider transfers. No lender-transfer implementation or activation is included.

No schema migration, dependency upgrade, environment-file change or historical financial correction is included. The existing payment/refund state machines and journal models remain in place.

## Files intentionally excluded

Environment files, credentials, account-provisioning artifacts, payment demos, private evidence, databases, logs, screenshots, browser profiles, generated builds, local Python dependency overlays and verification outputs remain local. Git and Docker ignore rules exclude the local payment directories and dependency overlay. Existing tracked model files remain unchanged; ignore rules do not remove files already tracked in Git.

## Prepare the Git change

Run from the repository root, `NeighborLend`, on the existing `feature/neighborlend-ai-payment-integration` branch:

```powershell
git status --short
git add --pathspec-from-file=docs/push-files-20261114.txt
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

The staging command selects exactly the listed paths; it does not clear an existing index. Inspect any files already staged before using it. Keep unrelated local reports and inspection scripts unstaged. This preparation does not commit, push, change branches or remotes, or deploy services.

## Deployment configuration

Use the existing deployment definitions. Configure secrets through the target environment's secret settings, never source control:

- Backend: private strong `JWT_SECRET`, the intended `DATABASE_URL`, appropriate `CORS_ORIGINS` and `PUBLIC_BASE_URL`, and storage/mail/OAuth configuration where needed.
- Public backend: `DEPLOYMENT_EXPOSURE=public`, `PAYMENT_DEMO_MODE=false`, `AUTO_MIGRATE=false`. Existing `render.yaml` defaults to `PAYMENT_PROVIDER=disabled`; pushing code does not activate Razorpay.
- If explicitly enabling existing Razorpay Test payments, set `PAYMENT_PROVIDER=razorpay_test` and supply matching Test key ID, API secret and webhook secret privately. Live-mode keys remain forbidden.
- Frontend: public HTTPS `VITE_API_BASE_URL` ending in `/api`; use `npm run build:web` for the public build environment. A successful local Vite build does not establish that public configuration is correct.
- Verify database-backed `/api/health`, authenticated rental reads, administrator access boundaries and reconciliation visibility after deployment. Do not apply hosted migrations or create provider transactions as a deployment smoke test without approval.

## Financial limitations

The existing drill incident has a recorded INR 400 deposit refund plus a separate INR 180 provider refund against the same INR 580 payment. The historical lender allocation is not available payment funding or evidence of a lender payout. Preserve the warning and existing journals until an explicit reconciliation decision is approved.

Actual lender transfer support remains blocked on provider capability, verified lender destinations, fee/funding policy and a separate implementation. Razorpay's [Route integration guide](https://razorpay.com/docs/payments/route/integration-guide/) states that a payment cannot be used for a new transfer after a refund has been initiated. A refund-first transfer workflow therefore requires further provider-supported design; this release does not enable it or claim end-to-end transfer success.

## Validation

Fresh checks during this preparation:

| Check | Result |
| --- | --- |
| Full isolated backend suite | 524 passed, 23 skipped, zero failures. PostgreSQL-only cases skipped; generated SQLite and synthetic gateway transport used. |
| Frontend `npm test` | 78 passed, zero failures. |
| `npm run lint:payments` | Passed. |
| `npm run build -- --outDir ../backend/.payment-verification/push-preparation-20261114/frontend-dist` | Passed; 1,685 modules. Generated output remains ignored. |
| `git diff --check` | Passed. |
| Release-list validation | 35 unique existing files; no ignored or sensitive paths selected; all modified tracked files included. |
| Common secret-pattern scan of selected files | No matches. This is a heuristic check, not a guarantee that all possible secret formats are detected. |
| Ignore checks | Environment files, payment artifacts, private evidence and local dependency overlay remain excluded. |

Backend reproduction from `backend/` used the existing private isolated runner with label `push-preparation-approved-20261114`: `python -B .payment-verification/refund-incident-20261114/run_fix_tests.py push-preparation-approved-20261114 tests`. The runner is a local artifact, excluded from the release. The suite result is recorded in the corresponding ignored XML file. A sandboxed launch exited without output; the approved retry using the installed environment completed the suite.

No fresh mounted-browser run, public deployment build, Docker image build or real-service lifecycle test was performed for this packaging task. Provider mutations, hosted database writes, hosted migrations and deployment are outside this preparation. The Git index remains empty; files are selected in the manifest and have not been staged, committed or pushed.
