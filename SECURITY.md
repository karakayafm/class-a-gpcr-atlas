# Security policy

## Reporting

**Security issues, or data-integrity problems that should not be public:**
email **edu.mfatih@gmail.com**. Please do not open a public issue for these.

**Scientific data corrections, software bugs and everything else:**
[GitHub Issues](https://github.com/karakayafm/class-a-gpcr-atlas/issues) is the right place, and
corrections are welcome.

Include what you can: affected page or PDB identifier, browser and OS, and how to reproduce.

## Scope

This is a **static site with no server, no accounts and no data collection**. There is no
database, no authentication, no form submission, no analytics, no telemetry and no third-party
script. It makes **no network request to any external host** — the NGL viewer is vendored, and
every payload is local. Outbound links are links a user may choose to click.

That removes most of what a security policy usually covers. What remains, and what is worth
reporting:

- Any content that executes in the page (the application assigns text, never HTML)
- Anything that would cause the viewer to leak or exhaust local resources
- **Data-integrity problems** — a value that does not match its source deposition, a hash that
  does not verify, a licence statement that is wrong

The last one matters as much as the first two here.

## Known, accepted, low-severity

Recorded openly rather than left to be discovered:

1. **CSV export has no formula-injection guard.** Values are RFC 4180-escaped but a cell
   beginning `=`, `+`, `-` or `@` would be interpreted as a formula by a spreadsheet application.
   No shipped value currently triggers this — 0 of 287,485 string values — but the data is
   upstream-controlled, so the safe state is presently accidental rather than enforced.
2. **No Content-Security-Policy.** A static release has no server to send headers, and no meta
   CSP is set. Given there are no external requests and no HTML assignment, the practical
   exposure is small; it remains defence in depth that has not been added.
3. **The vendored NGL bundle will not receive security updates automatically.** It is
   hash-verified against the published distribution, but someone has to notice a new release.

Both (1) and (2) are planned fixes, not disputes.

## Privacy

No personal data of users is collected, because there is no mechanism that could collect it. The
only names in the corpus are published bibliographic author names relayed from RCSB structure
citation metadata. The theme and language preferences are stored locally in the browser and are
never transmitted — nothing is transmitted.

## Response

This project has a single maintainer. Reports will be read and acknowledged, but no response-time
guarantee is made, and it would be dishonest to publish one.
