# Graceful error handling for ineligible sign-ins, and voters.txt's new role

## Part 1: no sign-in failure should ever crash the site

Once Google OAuth is (or becomes) the identity check, there are several distinct ways a
sign-in attempt can be "not allowed" — every single one of them must end with the person
seeing a clear, plain message and landing back on a normal page, never a stack trace, blank
error screen, or unhandled exception. Go through each of these explicitly and confirm (don't
assume) that each one is actually handled:

1. **Wrong email domain** — someone signs in with a personal Gmail account, not
   `@charusat.edu.in` or `@charusat.ac.in`. → Message: something like "Please sign in with
   your official CHARUSAT email." Return to the sign-in page.
2. **Right domain, but the ID doesn't match any known institute/department pattern** — e.g.
   a malformed or unusual email local-part that the ID parser can't make sense of. →
   Message: something like "We couldn't verify your student ID from this account. Please
   contact the election admin if you believe this is an error." Return to sign-in, don't
   crash.
3. **Valid ID, valid institute/department — but not eligible for *this specific* election**
   — e.g. a DEPSTAR student trying to vote in a CSPIT-only departmental election, reached via
   a code/link. → Message: something like "This election isn't open to your
   institute/department." Return to a normal page (their voter dashboard, not a dead end).
4. **A parsing exception itself** — if the ID parser throws an error rather than cleanly
   returning "no match" for some unexpected input shape, that must be caught and treated the
   same as case 2, not allowed to propagate into a 500 error page.

For all four cases: wrap the actual OAuth callback / eligibility-check route in proper
try/except handling so nothing here can produce an unhandled exception, and confirm this by
deliberately testing bad inputs (a non-CHARUSAT Google account, and if possible a
deliberately malformed test case) rather than only testing the happy path.

## Part 2: voters.txt / the voters table's role is changing — reflect this in the code and comments

Once OAuth is the live identity check, eligibility is determined directly from the signed-in
person's verified email (via the ID parser), not by looking them up in the `voters` table.
The `voters` table (populated from `voters.txt` via `import_voters.py`) should be treated as
**reference/backup data going forward, not the live source of truth for eligibility** —
specifically:

- Do not gate sign-in or voting eligibility on whether someone exists in the `voters` table.
  Base eligibility purely on parsing their verified OAuth email.
- When someone signs in via OAuth for the first time, capture their real display name from
  the Google profile data returned in the OAuth response, and store it — don't assume the
  `voters` table already has their name, since that's only populated for CSPIT/DEPSTAR
  students right now and won't cover the other 7 institutes at all.
- Leave `import_voters.py` and the `voters` table as-is otherwise — they're still useful as a
  cross-reference/backup, just no longer part of the live eligibility decision.
- Add a short code comment wherever the old lookup-based eligibility logic previously lived,
  noting that it's been superseded by OAuth-based parsing, so a future reader (or a future
  antigravity pass) doesn't accidentally reintroduce a dependency on the static roster.

## Verification steps

1. Attempt sign-in with a non-CHARUSAT Google test account — confirm a clean rejection
   message, not a crash.
2. Attempt to join a departmental election using an account from a different, ineligible
   department — confirm a clean rejection message, not a crash, and confirm they land
   somewhere sensible (their dashboard), not a dead page.
3. Sign in with a valid CHARUSAT test account whose ID is NOT in the `voters` table at all
   (e.g. simulate someone from an institute never imported) — confirm they can still sign in
   and are correctly identified by institute/department from the parsed email alone, proving
   eligibility no longer depends on the static roster.
4. Confirm the signed-in person's real name is captured and displayed correctly (e.g. "Welcome,
   [Name]") even for an account not present in the `voters` table.
