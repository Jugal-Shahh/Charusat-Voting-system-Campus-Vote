# Restyle prompt: match CampusVote's visual identity to CHARUSAT e-Governance portal

## Scope — read this first

This is a **visual-only restyle**. Do not change routes, database schema, ID-parsing logic,
OAuth flow, eligibility checks, or any backend behavior built in Phases 1–3. Only touch
template markup and CSS. If achieving the look requires a structural HTML change (e.g. adding
a sidebar wrapper), keep all existing `{{ }}` template variables and form field names exactly
as they are — the backend must not need to change at all.

Four reference screenshots of the actual CHARUSAT e-governance portal, and the official
CHARUSAT logo file, are provided alongside this prompt — use them as the visual ground truth
alongside the tokens below.

---

## 1. Design tokens (extracted from the reference screenshots)

```css
:root {
  /* Core brand */
  --navy: #163A6B;          /* top navbar, sidebar background */
  --navy-dark: #0F2A4E;     /* sidebar hover/active state, slightly darker */
  --table-blue: #2472C8;    /* table header bars */
  --btn-blue: #1E6FE0;      /* primary buttons (Login etc.) */
  --accent-orange: #F0871E; /* institute-strip / decorative accent, used sparingly */
  --link-purple: #6A4FC4;   /* "Recover Password"-style links */
  --danger-red: #E14B4B;    /* Close / destructive buttons */

  /* Surfaces */
  --page-bg: #F2F3F5;       /* body background behind cards */
  --card-bg: #FFFFFF;
  --input-bg: #EDF0FA;      /* pale lavender input fields */
  --footer-bg: #000000;     /* black footer bar */
  --row-alt: #F7F8FA;       /* alternating table row */

  /* Text */
  --text-dark: #1B1B1B;
  --text-muted: #6B7280;
  --text-on-navy: #FFFFFF;

  --radius: 4px;            /* boxy, not rounded — this portal uses small radii throughout */
  --font: 'Segoe UI', Arial, sans-serif;  /* standard enterprise sans, not a display serif */
}
```

Buttons, inputs, and cards in this portal all use small border-radius (~4px) and flat colors —
no shadows-as-decoration, no gradients except the thin orange institute strip. Keep it plain
and administrative-looking, matching the reference exactly rather than adding modern flourishes.

---

## 2. Layout patterns to replicate

### Top navbar (appears on every page after login)
- Solid `--navy` background, full width, ~56–64px tall.
- Left side: hamburger/menu icon, then the CHARUSAT logo (small square mark + wordmark),
  then the current page title in white (e.g. "Dashboard", "e-Governance Module").
- Right side: "Welcome, [Name]" in white, a small circular profile photo/avatar, an expand
  icon, and a power/logout icon.
- For CampusVote, swap "Welcome JUGAL SHAH" for the signed-in voter/admin's name, and swap
  the page title for the current page (e.g. "Cast Your Vote", "Results", "Admin Dashboard").

### Login page
- Two-panel layout: left side has decorative branding space (institute badge/graphic — can
  be simplified to just the CHARUSAT logo large, doesn't need the exact "25 Years" graphic),
  right side is the actual login card.
- Login card: white background, CHARUSAT logo at top, thin horizontal-rule divider with
  centered caption text below it ("Gateway to e-Governance" → change to something like
  "CampusVote — Official Election Portal"), then form fields.
- Input fields: pale lavender background (`--input-bg`), left-aligned icon prefix (person
  icon for ID/username, lock icon for password), no visible border — just the background
  color change signals the field.
- Primary button: solid `--btn-blue`, full width, white text, small lock/login icon, `--radius`
  corners — matches the "🔒 Login" button style exactly.
- Keep CampusVote's existing Google OAuth sign-in as the actual auth mechanism — this page
  should visually resemble the e-governance login card, but the button action stays
  "Sign in with Google," not a username/password form, for the voter-facing login. The
  admin username/password login (already built) can keep the literal username/password
  fields styled this way, since that one is a real password form.

### Dashboard / content pages (results, ballot, admin dashboard, audit log)
- Page background: flat `--page-bg` gray.
- Content organized into **white card widgets**, each with a light gray header bar
  containing a small icon + title (e.g. "🗓 Time Table" → adapt to "🗳 Cast Your Ballot",
  "📊 Live Results", "🧾 Candidates").
- Any tabular data (results table, candidate list, audit log, admin candidate table) uses
  a `--table-blue` header row with white text, and alternating white/`--row-alt` body rows.
- Small square icon-buttons (edit/action icons) appear at the right edge of table rows in
  the reference — replicate that pattern for row-level actions like "Remove candidate."

### Sidebar (optional, only if it doesn't conflict with existing nav)
- Dark `--navy` vertical sidebar, top item "Profile," collapsible sections with a chevron
  icon, indented sub-items. If adding a sidebar changes the page structure meaningfully,
  keep it as a togglable/collapsible element (the hamburger already implies this in the
  reference) rather than force it into every page if it complicates layout.

### Footer
- Solid black bar, centered white text: `© [year] CampusVote — CHARUSAT. All Rights Reserved.`
  (adapt the reference's copyright line rather than copying it verbatim).

### Modals (e.g. detailed results breakdown, confirmation dialogs)
- White modal, plain header text (no colored bar), close button in top-right (×) plus a
  labeled `--danger-red` "Close" button at the bottom-right of the modal footer, matching
  the reference's attendance-detail modal pattern.

---

## 3. Page-by-page mapping

| CampusVote page | Reference pattern to follow |
|---|---|
| Voter sign-in / Join voting | Login page (two-panel, card, lavender inputs) |
| Admin login | Login page, but literal username/password fields |
| Ballot / vote casting | Dashboard content page, ballot as a white card widget |
| Results (voter-facing) | Dashboard content page, results as a card with a `--table-blue` table |
| Admin dashboard | Dashboard content page, multiple card widgets (candidates table, turnout stats, voting-open toggle) |
| Audit log | Dashboard content page, single wide card with `--table-blue` table |
| Thank-you / confirmation | Simple centered card, can keep the existing seal/stamp element or drop it in favor of a plain confirmation message matching this portal's plainer administrative tone — your call, but state which you picked |

---

## 4. Logo usage

Use the official CHARUSAT logo file (provided separately) in:
- The login page (large, left panel or above the login card)
- The top navbar (small mark, left side, next to the wordmark)

Do not stretch or recolor the logo — use it at its native aspect ratio, matching how it
appears in the reference screenshots (blue swoosh mark + "CHARUSAT" wordmark + small
"CHAROTAR UNIVERSITY OF SCIENCE AND TECHNOLOGY" subtitle).

---

## 5. What NOT to copy from the reference

- The specific 10 institute logos in the login-page side strip — not relevant to CampusVote,
  skip this element entirely.
- The "25 Years of Excellence" anniversary graphic — decorative and time-bound, skip it.
- Any actual e-governance functionality (fees, attendance, exam hall ticket, etc.) — those
  are irrelevant menu items from the reference portal, not things CampusVote needs.
- The captcha — CampusVote's voter identity is already handled by Google OAuth restricted to
  the university domain, which is stronger than a captcha; don't add one.

---

## 6. Acceptance check before calling this done

After the restyle, every one of these should still work exactly as before, just look
different:
- Creating a voting system (all three scopes)
- Google sign-in restricted to the CHARUSAT domain
- Casting a ballot and being blocked from voting twice
- Viewing results after voting closes
- Admin dashboard candidate management and voting open/close toggle
- Auditor turnout log (still showing no vote content)

If any of these breaks during the restyle, that's a regression — stop and fix it before
moving on, since Phases 1–3 were already verified working.
