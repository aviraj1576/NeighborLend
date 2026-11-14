# Fictional local test accounts — 12 November 2026

Follow-up: the user subsequently authorized provisioning these same accounts in the shared database. See [shared test account verification](shared-test-accounts-verification-20261112.md) for the current shared status; this document records the original isolated setup.

Created Aarav Mehta (Borrower), Rohan Kapoor (Lender), and Priya Sharma (Admin) in a new isolated SQLite database. Borrower and lender describe rental participation; NeighborLend does not have mutually exclusive borrower/lender account roles.

Private artifacts are under `backend/.payment-demo/fictional-accounts-20261112/`:

- `test-credentials.txt`: actual emails, usernames, unique generated passwords, and launch instructions.
- `verified-accounts.sqlite3`: persisted accounts using the existing bcrypt password hashing.
- `run_backend.py`: starts this isolated backend at `http://127.0.0.1:8001`, with payment processing disabled and external service credentials overridden with empty values. The existing private JWT configuration remains required.
- `verification.json`: non-sensitive account creation and authentication results.

The directory has protected Windows NTFS permissions granting only the developer's Windows account access, inherited by its files. The credentials file's effective ACL was separately checked. The entire directory is Git-ignored; `.gitignore` also explicitly excludes `test-credentials.txt` at any depth. No credential values appear in this report.

All accounts went through the existing CAPTCHA, registration, and email verification endpoints. OTP delivery was captured in memory with the existing test convention of substituting the email sender. No email was sent and no production verification bypass was added. Priya received `User.is_admin=True` through the authorized offline fixture bootstrap convention used by `scripts/create_payment_demo.py`; public registration granted no admin access.

Verification results:

- Three unique 256-bit generated passwords and three existing bcrypt hashes verified.
- All six username/email logins and all three authenticated profiles passed.
- All three unverified login attempts were rejected before completing OTP verification.
- All three incorrect-password attempts were rejected.
- Priya could read the admin dispute queue; Aarav and Rohan were denied.
- A second process read the saved credentials privately and rechecked all three logins, profiles, and admin access against the persisted database.
- Payment transactions and rental bookings remained empty. No payment was initiated.

Only new local SQLite schema was initialized. Shared Supabase was not accessed; no Supabase migrations, shared accounts, commits, pushes, or deployments were performed. The ordinary backend `.env` and application code were not changed by this task.

To use the accounts, run `python -B backend/.payment-demo/fictional-accounts-20261112/run_backend.py` with the project's Python environment. Point a local frontend at `http://127.0.0.1:8001/api`. These accounts are available only on this isolated backend, and are not present in the shared backend. The backend was verified through in-process ASGI requests; no persistent server was left running.
