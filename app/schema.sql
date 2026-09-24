-- jobbot's store. One source of truth for what was found, what was built, and
-- what he applied to. GitHub Actions writes here through the Worker's API;
-- the app reads and writes it directly. Resume PDFs stay in the repo.

CREATE TABLE IF NOT EXISTS jobs (
  uid         TEXT PRIMARY KEY,
  company     TEXT NOT NULL,
  title       TEXT NOT NULL,
  tier        INTEGER,
  term        TEXT,                 -- "Summer 2027" as a person would say it
  location    TEXT,
  source      TEXT,                 -- greenhouse | lever | ashby | workday | amazon
  org         TEXT,
  raw_id      TEXT,
  url         TEXT,
  apply_url   TEXT,
  posted_at   TEXT,
  deadline    TEXT,
  state       TEXT NOT NULL,        -- found|building|ready|applying|needs|applied|skipped|failed
  note        TEXT,                 -- plain-language status line
  knockout    INTEGER DEFAULT 0,
  folder      TEXT,                 -- resumes/<Company>/<Role>
  pdf         TEXT,
  preview     TEXT,
  issue       INTEGER,              -- GitHub issue, while that path still exists
  seen_at     TEXT NOT NULL,        -- when jobbot first saw it
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state, tier, posted_at DESC);
CREATE INDEX IF NOT EXISTS jobs_seen ON jobs(seen_at DESC);

-- Everything he has applied to: jobbot's applications and his own history.
CREATE TABLE IF NOT EXISTS applications (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  uid         TEXT,                 -- null for rows that predate jobbot
  company     TEXT NOT NULL,
  title       TEXT NOT NULL,
  applied_at  TEXT NOT NULL,
  outcome     TEXT NOT NULL DEFAULT 'no response',   -- no response|screening|interview|offer|rejected|withdrawn
  outcome_at  TEXT,
  referral    TEXT,
  notes       TEXT,
  apply_url   TEXT,
  pdf         TEXT,
  how         TEXT NOT NULL,        -- jobbot | by hand | tracker
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS applications_when ON applications(applied_at DESC);
CREATE INDEX IF NOT EXISTS applications_outcome ON applications(outcome);

-- Why anything is the way it is.
CREATE TABLE IF NOT EXISTS events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  uid    TEXT,
  at     TEXT NOT NULL,
  kind   TEXT NOT NULL,             -- found|built|applied|needs|skipped|error|note
  detail TEXT
);
CREATE INDEX IF NOT EXISTS events_uid ON events(uid, at DESC);

-- Web push, once notifications move into the app.
CREATE TABLE IF NOT EXISTS push_subs (
  endpoint TEXT PRIMARY KEY,
  keys     TEXT NOT NULL,
  added_at TEXT NOT NULL
);

-- Actions he takes in the app. jobbot pulls the unhandled ones on its next run
-- and applies them to its own files, so the app can drive the system even for
-- jobs that have no issue.
ALTER TABLE events ADD COLUMN handled INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS events_open ON events (handled, id);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs (state);
CREATE INDEX IF NOT EXISTS apps_date ON applications (applied_at DESC);

-- Answers he edited in the app. The prepared answers live in the repo next to
-- the resume; these win over them, and jobbot writes them back on its next run.
CREATE TABLE IF NOT EXISTS answers (
  folder     TEXT NOT NULL,
  label      TEXT NOT NULL,
  text       TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (folder, label)
);

-- What he wants said differently on a resume, in his own words. It rides along
-- with the request to write it and ends up in the JD the writer reads.
ALTER TABLE jobs ADD COLUMN hint TEXT;

-- The posting itself, so he can read it without leaving the app, and one row
-- of housekeeping so the app can say when jobbot last checked the boards.
ALTER TABLE jobs ADD COLUMN jd TEXT;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT, at TEXT);

-- Mute a company, snooze a job until later, keep the screenshots an apply run
-- took, remember a deleted application long enough to undo it, and keep the
-- draft an edited answer replaced so it can be put back.
ALTER TABLE jobs ADD COLUMN shots TEXT;
ALTER TABLE jobs ADD COLUMN snoozed_until TEXT;
ALTER TABLE applications ADD COLUMN deleted_at TEXT;
ALTER TABLE answers ADD COLUMN was TEXT;
CREATE TABLE IF NOT EXISTS muted (company TEXT PRIMARY KEY, at TEXT NOT NULL);

-- The companies he follows. Seeded once from jobbot/targets.txt; after that
-- the app is where he changes it, and jobbot writes his changes back.
CREATE TABLE IF NOT EXISTS following (key TEXT PRIMARY KEY, name TEXT NOT NULL, at TEXT NOT NULL);

-- What jobbot's rules turned away in the last week, and why, so a rule that is
-- wrong shows up as a line here rather than as a job he never hears about.
-- `data` is the whole posting, handed back to jobbot if he brings it back.
CREATE TABLE IF NOT EXISTS filtered (uid TEXT PRIMARY KEY, company TEXT NOT NULL, title TEXT,
  location TEXT, url TEXT, apply_url TEXT, posted_at TEXT, reason TEXT, data TEXT, seen_at TEXT NOT NULL);

-- His Settings. `base` is the default jobbot reads from its files (criteria,
-- answers, profile, resume rules); `value` is what he saved, with `value_base`
-- the default he was looking at when he saved it, so a field he never touched
-- keeps following the file. `was` is the previous save, for Undo.
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, base TEXT, value TEXT, value_base TEXT,
  was TEXT, was_base TEXT, updated_at TEXT);

-- Why he archived a job, so patterns can be offered back to him as a Settings
-- change; the suggestions he waved away; and which parts of the app he uses,
-- counted per day.
CREATE TABLE IF NOT EXISTS feedback (uid TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT,
  reason TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dismissed (id TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage (day TEXT NOT NULL, name TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, name));

-- What each subscribed device has already been told about, so a job that sits
-- ready for a week is announced once.
-- What Claude wants to say about a job it just wrote for: a choice it made, or
-- a question. He answers in the same box he uses for notes.
ALTER TABLE jobs ADD COLUMN says TEXT;

CREATE TABLE IF NOT EXISTS push_sent (uid TEXT NOT NULL, state TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (uid, state));
