# Security model and limits

The protected boundary is the authenticated rental participant, not a claimed filename,
role or user ID. Default authorization is fail-closed. Explicit local tokens map to
server-owned subject/rental-role fixtures and are hashed for in-memory comparison with
`hmac.compare_digest`. Local grants are not production identity, have no token issuance,
expiry or dynamic revocation, and must only be used in a loopback development service.
Production identity integration is deferred and documented in integration-contract.md.

Before-evidence requires the lender grant; after-evidence requires the borrower grant.
Both rental participants may read that rental's evidence and inspections. A participant
of a different rental is denied, including content downloads and cross-rental inspection
selections. Unauthenticated requests reveal no evidence. UUIDs reduce guessing but are
not authorization. Distinct 403/404 behavior for authenticated callers is documented;
resource IDs themselves must still be treated as sensitive references.

Only decoded JPEG/PNG is accepted. The API bounds whole bodies before parsing, including
chunked transfer. The decoder checks byte, pixel and dimension limits before full decode,
rejects animation, verifies containers and loads pixels, and converts EXIF orientation
into separate metadata-stripped PNGs. Decompression-bomb warnings are fatal. No client
filename becomes a storage path. Original evidence may contain EXIF/GPS or appended data;
image validation is not a malware scanner. Original downloads are authenticated,
`attachment`, `no-store` and `nosniff`. Do not render originals as active content in a
future frontend. Consider sandboxed decoding and malware scanning before public ingestion.

Private files live under dedicated `ep/.runtime/evidence` by default, never under the
backend static mount. API responses filter storage keys and uploader subjects. Original
and derivative SHA-256 values are verified at recovery, duplicate handling and inspection
creation; originals are also checked on download. Hashing detects changes relative to
trusted metadata; it is not a signature, proof of capture time, or protection against a
host attacker able to edit both bytes and SQLite. Storage-key helpers reject traversal
and symlinked file targets. Storage/database constructors reject symlinked roots/files
and resolved paths outside EP before opening them. The regression tests simulate symlink
metadata; native Windows symlink/ACL behavior has not been independently integration-tested.
Host-level modification is outside the remote-client threat
model; trusted operators must protect the whole data directory.

POSIX files use 0600 and directories request 0700. Windows uses inherited ACLs; Python
mode flags do not establish Windows access isolation. The operator must restrict NTFS
ACLs for the local grants, database and evidence directory. There is no at-rest encryption
or automated retention/deletion policy in this phase. Define consent, retention duration,
backups, deletion/dispute holds and audit access before production use.

The service does not load root dotenv files, log bodies/tokens/sensitive metadata, expose
raw exception details, or contact cloud/AI services. Error and validation responses are
sanitized and correlated with server-generated request IDs. CORS permits no origins by
default and does not permit credential cookies. CORS is a browser policy, not access control.

Remaining operational controls: TLS/reverse proxy, request read timeouts, rate limits,
user/storage quotas, process-wide decode concurrency, account revocation, private volume
ACL verification, durable backups, worker leasing, and load testing. SQLite/local recovery
is single-service-process development infrastructure, not a production deployment claim.
No statement of complete security, reliability or model accuracy is made.
