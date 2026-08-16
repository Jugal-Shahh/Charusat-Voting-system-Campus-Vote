# Bug fix & completeness pass — CampusVote

## Ground rules — read before touching anything

- **This is a fix-and-complete pass, not a rewrite.** Most of the system already works
  (Phases 1–3 were verified working end-to-end before the restyle). Read the existing code
  first, identify what's actually broken or missing against the checklist below, and make
  the smallest change that fixes each item. Do not refactor or restructure files that are
  already working correctly.
- **Do not touch the identity-verification mechanism itself** (whatever is currently wired
  up for login/signup) beyond what's needed to make the rest of the app work correctly with
  it. The auth approach is being decided separately with the user's faculty/seniors — your
  job here is to make sure everything downstream of "we know who this person is" (their
  voter_id, institute, department) works correctly, not to change how that identity is
  established.
- **After every fix, re-run the full checklist below, not just the item you just fixed** —
  this is a shared codebase where a change in one template or route can silently break
  another page. Treat any checklist item that was passing before your change and fails after
  it as a regression to fix immediately, before moving to the next item.
- If you find a genuine design ambiguity (not just a bug) — two places in the code that
  disagree about how something should work — do not silently pick one. Flag it clearly in
  your response and state which behavior you implemented and why, so the user can correct it
  if you guessed wrong.

---

## 1. Functional checklist — verify each of these actually works, end to end

### Home page
- [ ] Two clear entry points: "Create a Voting System" and "Vote / Join a Voting System."

### Creating a voting system
- [ ] Clear branch between **"Log in"** (existing admin account) and **"Create account"**
      (new admin) — not just a login form with no signup path.
- [ ] After identity verification, new admin sets a username and password.
- [ ] Returning admin can log in with username + password and land on a dashboard listing
      **all voting systems they own** (not just one).
- [ ] Creating a new voting system: name it, then choose scope —
      **University-wide / Institutional / Departmental**.
- [ ] Institutional scope: all 9 institutes listed (IIIM, RPCP, CSPIT, DEPSTAR, PDPIAS,
      CMPICA, ARIP, MTIN, BDIAS); institutes with no usable data for determining eligibility
      are shown disabled/"not available," never silently selectable into a broken election.
- [ ] Departmental scope: institute → department, same availability rule.
- [ ] On creation, a unique code and shareable link are generated and shown to the admin.

### Admin dashboard (per voting system)
- [ ] Add candidate, remove candidate.
- [ ] Open voting / close voting toggle, and voters are correctly blocked from voting
      while closed.
- [ ] Live turnout count (X of Y eligible voters have voted).
- [ ] Viewing the turnout/audit log requires re-entering the account password, even within
      an active session.
- [ ] Turnout/audit log shows **who voted and when only** — never what they voted for.
      Confirm there is no code path anywhere (including this one) that can join vote content
      back to a voter identity.

### Voter flow
- [ ] Signed-in voter sees a personal dashboard listing every currently open voting system
      they're eligible for, based on their institute/department.
- [ ] "Join by code/link" also requires identity verification before showing a ballot —
      confirm this can't be bypassed by hitting the ballot URL directly without verifying.
- [ ] **Votes-per-ballot should be configurable per election, not hardcoded to a fixed
      number.** The original prototype fixed this at 2 votes per voter, which doesn't make
      sense generalized — a single-position election like "Sports Coordinator" should
      default to 1 selection, while a multi-seat election could allow more. Add this as a
      field the admin sets when creating the election (default: 1), and make sure the ballot
      page, vote-recording logic, and results tally all respect that number correctly rather
      than assuming 2.
- [ ] NOTA is available as an option for each selection slot on the ballot.
- [ ] A voter cannot vote twice in the same voting system (double-submission, back button,
      multiple tabs, or resubmitting the form after already voting must all be blocked).
- [ ] A voter whose institute/department doesn't match the election's scope cannot vote in
      it, even if they have the code/link.

### Results
- [ ] **Decide and implement one consistent rule, and state which you chose:** are results
      visible to voters only after the admin closes voting, or visible live while voting is
      open too? These have appeared inconsistently across earlier instructions. Recommended
      default if not otherwise specified: **results are hidden from voters until the admin
      closes voting**, but the admin can always see live turnout counts (not vote-content
      breakdowns) from their own dashboard while it's open. Implement this as the default,
      but make it a per-election toggle if that's not much extra work, and clearly state
      what you did either way.
- [ ] Once visible, results show correct per-candidate tallies and NOTA count, matching the
      configurable vote-count logic above (not assuming exactly 2 votes were cast per voter).

### Data integrity / anonymity (non-negotiable — re-verify explicitly)
- [ ] No database table, join, or query anywhere links a specific voter to their specific
      vote choice.
- [ ] All of the above (candidates, votes, turnout, has-voted state) are correctly scoped
      per voting-system-instance — actions in one election must never affect another.
- [ ] Vote recording + marking a voter as having voted happen atomically (already solved
      once in the original single-election build — confirm the same guarantee holds now
      that it's scoped per voting system).

### Visual / layout
- [ ] The top navbar logo and page title no longer overlap (this was a known bug — verify
      the fix by actually checking every page that renders the shared header component, not
      just the one page it was originally spotted on).
- [ ] General pass: check other pages for similar layout collisions introduced during the
      restyle (overlapping text, elements escaping their containers, unreadable contrast)
      and fix any found, even if not explicitly listed here.

---

## 2. Before you finish

Run through this exact sequence as a final smoke test, the same way it was verified after
Phase 3, and report the result of each step:

1. Create a new admin account from scratch (not an existing one).
2. Create a departmental-scope election with 1 vote per ballot and 3 candidates.
3. Sign in as an eligible voter, confirm the election appears on their dashboard, cast a
   ballot.
4. Confirm that same voter cannot vote again (all three angles: reload, back button, direct
   URL to the ballot).
5. Sign in as a voter who is NOT eligible for that election (wrong institute/department),
   confirm they cannot vote in it even with the code/link.
6. Close voting from the admin dashboard, confirm voters can now see results and they're
   correct.
7. Log out and log back in as the same admin, confirm the voting system (and its data) is
   still there and manageable.
8. Re-enter the admin password to view the audit log, confirm it shows turnout only, no
   vote content.

If any step fails, that's the priority fix before anything else in this pass is considered
done.
