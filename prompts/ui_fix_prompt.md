# UI-only fix pass — CampusVote

## Scope

This pass is visual/CSS/template fixes only. Do not touch routes, database logic, auth,
or anything backend-related — including the identity verification method, which is being
handled separately later. If a fix seems to require a backend change, stop and flag it
instead of making it.

Two specific bugs survived a previous fix attempt aimed at them, so **diagnose before
changing anything** — don't reapply the same fix that already failed.

---

## 1. Diagnose first, then fix: navbar logo/title overlap

Before writing any code, do the following and show the results:
1. Find the actual template file(s) that render the top navbar — the bar containing the
   CHARUSAT logo/wordmark and the page title (e.g. "Dashboard").
2. Print out the current HTML structure and CSS rules that position those two elements —
   specifically look for `position: absolute`, `position: fixed`, negative margins, or
   elements without a shared flex/grid parent, since any of these would explain why a
   previous "make it a flex row" instruction didn't visibly change anything.
3. Only after identifying the actual cause, fix it: the logo and title must be two children
   inside a single flex container (`display: flex; align-items: center;`), the logo with a
   fixed `height` (e.g. 32–40px) and `width: auto`, the title with `margin-left` for spacing.
   Neither element should be positioned independently of the other.
4. **Check every page that uses this shared navbar component** (dashboard, ballot, results,
   admin dashboard, audit log, admin login) — this is one shared component, so if it's fixed
   in one place it must be fixed everywhere it's used. Confirm this by finding all templates
   that include/extend the navbar, not just the one page it was reported on.

## 2. Diagnose first, then fix: missing logo on home/login page

1. Find the `<img>` tag (or CSS `background-image`) responsible for the CHARUSAT logo on
   the home/login page.
2. Check whether its `src` (or `url_for('static', filename=...)` path) actually resolves —
   confirm the logo file still exists at that exact path in the `static/` folder. A previous
   restyle/bug-fix pass likely moved, renamed, or removed the file, or changed the folder
   structure without updating this reference — that's the most likely cause of a logo that
   was working before and isn't now.
3. Fix the path so it points at the real, current location of the logo file. If the logo
   file is genuinely missing from the project entirely, say so explicitly rather than
   silently leaving a broken image tag or swapping in a placeholder — the user needs to know
   they must re-supply that file.

## 3. Full visual audit — every page, not just the two known bugs

Go through every page in the app (home/login, admin signup if present, admin login, voter
dashboard, ballot/voting page, results, admin dashboard, audit log, thank-you/confirmation)
and check for:
- Overlapping or clipped text or images
- Elements breaking out of their containers on a normal desktop browser width (~1280–1920px)
- Inconsistent spacing, fonts, or colors between pages (they should all share the same
  design tokens/CSS variables set up during the restyle — check nothing accidentally
  reverted to default browser styling on any one page)
- Broken image paths anywhere else in the app, not just the logo already mentioned
- Buttons, links, or form fields that are unreadable (bad contrast) or misaligned

Fix anything found, even if not explicitly listed above.

---

## 4. Verification requirement — do not report a fix as done without this

For each fix, actually load the corresponding page and visually confirm the fix took
effect, the same way a person testing it in a browser would — do not consider something
fixed just because the code change looks correct on paper. If you cannot render/view pages
yourself, clearly list every page you changed and exactly what to look for when the user
reloads it, so they can confirm quickly rather than having to guess what changed.
