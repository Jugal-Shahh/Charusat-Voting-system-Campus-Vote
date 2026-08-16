-- ============================================================
-- CampusVote Database Schema (Phase 2+3: Multi-Tenant)
-- ============================================================
-- Design principle: the "voters" / "turnout_log" tables track
-- WHO has voted. The "votes" table tracks WHAT was voted for.
-- These are deliberately NOT linked by a voter_id foreign key,
-- so nobody -- not even an admin with full DB access -- can look
-- up how a specific student voted. That separation is the single
-- most important property of a real election system.
--
-- Phase 2+3 additions:
--   - institute_id_patterns: data-driven ID parsing
--   - voting_systems: multi-tenant election instances
--   - admins redesigned: Google-verified + username/password
--   - candidates, votes, turnout_log scoped by voting_system_id
-- ============================================================

-- ============================================================
-- Institute ID pattern definitions (data, not code).
-- Adding a new institute = INSERT a new row here, no code change.
-- ============================================================
CREATE TABLE IF NOT EXISTS institute_id_patterns (
    institute_code          TEXT PRIMARY KEY,
    regex_pattern           TEXT NOT NULL,
    department_codes        TEXT NOT NULL,      -- JSON array
    diploma_marker_position TEXT NOT NULL       -- 'before_year'|'after_year'|'none'
);

INSERT OR REPLACE INTO institute_id_patterns
    (institute_code, regex_pattern, department_codes, diploma_marker_position)
VALUES (
    'CSPIT',
    '^(D)?(\d{2})(CS|CE|IT|EC|ME|EE|CL|AIML)(\d{3})$',
    '["CS","CE","IT","EC","ME","EE","CL","AIML"]',
    'before_year'
);

INSERT OR REPLACE INTO institute_id_patterns
    (institute_code, regex_pattern, department_codes, diploma_marker_position)
VALUES (
    'DEPSTAR',
    '^(D)?(\d{2})(D)(CE|CS|IT)(\d{3})$',
    '["CE","CS","IT"]',
    'after_year'
);

-- ============================================================
-- Voters
-- Structured columns populated at import time (parse-on-import).
-- ============================================================
CREATE TABLE IF NOT EXISTS voters (
    voter_id        TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    has_voted       INTEGER NOT NULL DEFAULT 0,
    voted_at        TIMESTAMP,
    institute       TEXT,
    department      TEXT,
    admission_year  INTEGER,
    is_diploma      INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- Admins
-- Google sign-in proves accountability (google_email).
-- Username/password is a convenience login for returning admins.
-- ============================================================
CREATE TABLE IF NOT EXISTS admins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    google_email    TEXT UNIQUE,
    username        TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'admin',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Voting Systems (multi-tenant election instances)
-- scope_type determines who is eligible:
--   'university'  -> all voters with non-NULL institute
--   'institute'   -> voters WHERE institute = scope_institute
--   'department'  -> voters WHERE institute = scope_institute
--                            AND department = scope_department
-- ============================================================
CREATE TABLE IF NOT EXISTS voting_systems (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    scope_type       TEXT NOT NULL,       -- 'university'|'institute'|'department'
    scope_institute  TEXT,                -- NULL for university-wide
    scope_department TEXT,                -- NULL for university/institute
    code             TEXT UNIQUE NOT NULL, -- 6-char shareable code
    admin_id         INTEGER NOT NULL,
    is_open          INTEGER NOT NULL DEFAULT 0,
    max_choices      INTEGER NOT NULL DEFAULT 1,
    allow_live_results INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins(id)
);

-- ============================================================
-- Candidates (scoped per voting system)
-- ============================================================
CREATE TABLE IF NOT EXISTS candidates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    voting_system_id  INTEGER NOT NULL,
    name              TEXT NOT NULL,
    party_or_role     TEXT,
    photo_filename    TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (voting_system_id) REFERENCES voting_systems(id)
);

-- ============================================================
-- Votes (scoped per voting system, NO voter_id -- anonymous)
-- ============================================================
CREATE TABLE IF NOT EXISTS votes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    voting_system_id  INTEGER NOT NULL,
    candidate_id      INTEGER,
    is_nota           INTEGER NOT NULL DEFAULT 0,
    cast_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (voting_system_id) REFERENCES voting_systems(id),
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

-- ============================================================
-- Turnout log (scoped per voting system)
-- Proves who voted and when, without revealing what they chose.
-- ============================================================
CREATE TABLE IF NOT EXISTS turnout_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    voting_system_id  INTEGER NOT NULL,
    voter_id          TEXT NOT NULL,
    voted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (voting_system_id) REFERENCES voting_systems(id)
);

-- ============================================================
-- Settings (global key/value store)
-- ============================================================
CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('voting_open', '0');
INSERT OR IGNORE INTO settings (key, value) VALUES ('election_title', 'CharusatVote');
