# JWT configuration audit and verification — 12 November 2026 (IST)

**PASS for the local JWT configuration/signing/verification scope.** The insecure
application fallback is removed. The user's existing private `backend/.env` key
passes the new policy and an offline token round trip. The secret and generated
tokens were never printed or written to this report, and `.env` was not modified.

## Findings and changes

| Finding | Resolution |
| --- | --- |
| `Settings.jwt_secret` silently used a known repository key | Required `SecretStr` field with no default in any environment |
| Weak keys were rejected only in public/production paths | Central configuration validator applies to development, test and production |
| Settings/debug output could reveal a string key | Key is omitted from settings repr and masked in JSON serialization; validation error strings hide input |
| Key/algorithm could be reassigned accidentally after initialization | Both fields are frozen; rotation uses a process restart |
| Configurable algorithms widened the verifier's accepted algorithm | HS256 is explicitly fixed in settings and allowlisted in verification |
| JWTs were not required to contain expiry and subject claims | Require `exp` and `sub`, and reject empty/non-string subjects |
| Signing and email OTP code expected a plain string | Unwrap `SecretStr` only at the existing JWT/HMAC cryptographic calls |
| Duplicate public-mode key policies could diverge | Payment provider's defensive recheck delegates to the same central validator |

Files changed for this audit: `app/config.py`, `app/services/auth.py`, the
redundant JWT-only guard in `app/main.py`, the JWT recheck in
`app/services/razorpay_service.py`, test configuration and the relevant regression
expectation. New files are `tests/test_jwt_security.py` and
`scripts/verify_jwt_configuration.py`, plus this report. Setup/current architecture
documentation was updated; pre-existing feature-branch work was retained.

The key policy requires at least **32 UTF-8 bytes**, at least **12 distinct
characters**, no whitespace, and rejects the former default and common placeholder
prefixes. Length/diversity rules detect configuration mistakes; they do not prove
entropy. Keys must be generated privately using a cryptographically secure random
generator. The provided private key passed without replacement.

There is **no `APP_ENV=test` bypass**. `tests/conftest.py` generates a fresh key
with `secrets.token_urlsafe(48)` for each test process and explicitly sets HS256,
shadowing local `.env`. Invalid process overrides fail instead of falling back
to another file or a repository key. Environment precedence remains project
`.env`, then `backend/.env`, then process variables.

The former default appears only as a denied value or a negative verification
fixture; normal signing and verification use only the configured private key.

## Authentication and compatibility

Login still issues bearer JWTs with the existing `sub`/`exp` contract and configured
lifetime. Verification uses HS256 and the current key, checks expiry and required
claims, and returns the existing 401/Bearer challenge on invalid credentials.
Malformed signatures, unsigned tokens, wrong algorithms, missing/invalid expiry
or subjects, and tokens signed with the former default or a retired key fail.

Roles and account verification remain database-authoritative: an `is_admin` claim
does not grant privileges. Unverified or nonexistent accounts cannot authenticate
with an otherwise valid token. Login, `/api/auth/me`, protected payment reads,
mock checkout authorization, role-negative cases and existing email OTP HMAC
behavior pass integration/regression tests. Google sign-in and other existing
authentication tests remain in the complete suite.

Unexpired tokens signed with the current key and valid required claims remain
valid. Tokens signed with the old key require a new login. Existing email OTPs
were already bound to the signing key; after a rotation, request a fresh OTP.
No issuer/audience contract or unrelated rental/payment state machine was added.

## Commands and results

Commands were run from `backend/` using the existing Conda Python executable
`D:\Anaconda_Install\envs\neighbourlend_yolo\python.exe`. No dependency installation
or external service deployment occurred.

| Verification | Final result |
| --- | --- |
| `python -B scripts/verify_jwt_configuration.py` | PASS: actual configured private key, round trip, former-default rejection, masked settings, `.env` unchanged, 0 external requests |
| `python -B -m pytest tests/test_jwt_security.py tests/test_auth_captcha.py tests/test_auth_inbox.py tests/test_payment_providers.py tests/test_payment_regressions.py -q --tb=short ...` | **111 passed**, 0 failed/skipped; 76.52 seconds |
| New `test_jwt_security.py` cases within those runs | **62 passed** |
| `python -B scripts/verify_payments.py`, with `PAYMENT_TEST_POSTGRES_URL` explicitly empty | **361 passed, 13 skipped, 0 failed**; 167.47 seconds; 374 collected |
| Ruff check and format check on config/auth/provider/new JWT tests/verifier | PASS; 5 files |
| Ruff syntax/undefined-name checks across `app`, `tests`, `scripts` | PASS |
| Git whitespace check and JWT call-site review | PASS |

The 13 skipped tests require an explicitly configured local PostgreSQL service.
They were deliberately disabled for this configuration-only audit; no PostgreSQL
or Supabase migration verification is claimed in this run. The earlier payment
report separately records its PostgreSQL evidence.

Coverage includes missing keys across six environment/exposure combinations,
weak/default/placeholder/whitespace keys, masking and frozen fields, environment
precedence, key rotation, invalid signatures/claims/algorithms, unsigned and
malformed tokens, failure before app startup side effects, cached payment-provider
policy enforcement, real local login/protected endpoint authorization and OTP
round trips. The first targeted attempt lacked the artifact parent directory;
creating that directory resolved the test harness errors. The clean rerun above
replaced that failed setup result; no security test was disabled or weakened.

## Safety and evidence

All changes remain local and uncommitted. This audit ran **no Supabase migration,
Razorpay transaction, remote deployment, Git commit/push/merge or credential-file
edit**. Full regressions use generated SQLite databases, test signing keys,
mock/synthetic transports and the existing real-payment-network prohibition.
The private-key smoke check explicitly blocks database and HTTP connections.
AI checkpoints/engines, shared hosted financial tables/data and existing rental
records were not changed by this task.

Private ignored artifacts are in `backend/.payment-verification/jwt-20261112/`:
`targeted.xml`, `backend.xml`, `configuration-smoke.json` and `summary.json`.
The complete suite's default output is also at `.payment-verification/backend.xml`.
They contain test results, not the private signing key or actual access tokens.

Restart local backend/ingress processes to load the changed code and key because
settings are cached per process. Users holding tokens signed with the former key
must sign in again. No running service was restarted automatically. Public
deployment still needs the private environment to be provisioned independently;
the earlier dependency-security findings are outside this configuration change
and are not waived by these passing tests.
