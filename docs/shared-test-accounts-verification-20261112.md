# Shared test account provisioning — 12 November 2026

The user explicitly authorized inserting these three existing fictional fixtures into the shared NeighborLend Supabase PostgreSQL database for controlled Razorpay Test Mode acceptance.

| Username | Intended participation | Provisioning | Backend authentication | Port 8000 login |
| --- | --- | --- | --- | --- |
| `aarav_mehta` | Borrower | Created | Passed | Passed |
| `rohan_kapoor` | Lender | Created | Passed | Passed |
| `priya_sharma` | Admin | Created with authorized admin flag | Passed | Passed |

No email addresses, passwords, password hashes, tokens, database URLs, keys, or database identifiers are included here. The existing private credentials file remains the source of passwords.

## Provisioning controls

- Confirmed that both configured PostgreSQL and Supabase URLs matched the previously reviewed NeighborLend project; the live PostgreSQL connection used TLS. The connected Supabase management plugin listed different projects, so no writes were attempted through that plugin.
- Verified the original SQLite credentials, verified-email state, and admin state privately before shared provisioning. Reused the existing passwords and NeighborLend's existing bcrypt hashing.
- Checked case-insensitive usernames and emails before insertion. All three were absent. Inserted exactly three users, each with a new UUID and a display-name suffix of `[TEST - Razorpay Test Mode]`. No existing user was updated.
- Applied the existing authorized backend operator fixture convention: `is_verified=True` for these explicitly approved test fixtures and `is_admin=True` only for Priya. Public registration and email verification controls were unchanged. No email was sent.
- Used a single transaction, bounded lock/statement timeouts, and a users-table lock to protect duplicate checks. Server-side before/after fingerprints covering existing records across public tables matched after excluding only the three new IDs.
- A private Git-ignored manifest records only accounts created by this run. Passwords and hashes are absent from the manifest and verification reports.

## Authentication and authorization

- Existing backend `login`, JWT creation, `get_current_user`, and `require_admin` logic passed against PostgreSQL for all three users; both username and email login were verified.
- Existing rental ownership authorization allowed Aarav as borrower and Rohan as lender and denied the reversed participants. Priya's existing admin path passed. These checks used the actual authorization function with the provisioned identities, without creating a booking or a payment.
- The actual listener at `http://127.0.0.1:8000` passed health, login, authenticated profile, owned listings, owned borrow requests, and admin dispute-queue access checks. Returned account IDs matched the newly provisioned shared records, rather than the SQLite fixtures. Aarav and Rohan received HTTP 403 for the admin queue; Priya received HTTP 200.
- This verifies authentication and read access. Payment acceptance and a complete rental lifecycle were intentionally not exercised.

## Cleanup

From `backend/`, with the project's Python environment:

```powershell
python -B scripts/provision_fictional_accounts.py --cleanup
```

This is a preview. The shared preview selected exactly the three newly created users, with no related rows present. It did not delete them. To execute that cleanup later, explicitly add `--apply`.

Cleanup requires the private creation manifest and exact account identity/label matches. It discovers related nonfinancial records, including offer chains, messages, photos, notifications, email verification records, listings, and borrow requests; deletes in dependency order; and does not use broad email matching or `CASCADE`. Records involving unrelated participants, unknown dependencies, or financial history block the entire cleanup. Financial history and append-only audit/evidence records are retained. Files in local or Supabase storage are never deleted automatically.

## Verification commands

```powershell
python -B -m pytest tests/test_fictional_account_provisioning.py tests/test_auth_inbox.py tests/test_auth_captcha.py tests/test_jwt_security.py -q --tb=short
python -B -m ruff check scripts/provision_fictional_accounts.py tests/test_fictional_account_provisioning.py
python -B scripts/provision_fictional_accounts.py
python -B scripts/provision_fictional_accounts.py --apply --verify
python -B scripts/provision_fictional_accounts.py --cleanup
```

Results: **87 isolated tests passed** (including 15 provisioning/cleanup tests); lint passed; shared preflight and shared provisioning/authentication passed. Repeated read-only preflight recognized all three existing accounts without modifying them. Tests used synthetic local databases; only the explicit provisioning command inserted shared accounts.

Razorpay configuration remained `razorpay_test`, with existing safeguards rejecting live keys. No payments, refunds, transfers, payouts, schema migrations, deployments, commits, pushes, or merges were performed. The backend `.env` and running port 8000 process were not changed or restarted.
