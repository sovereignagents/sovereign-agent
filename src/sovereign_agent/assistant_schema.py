"""Migration 19: learner-owned turns, schedules, approvals and remote effects."""

SCHEMA = """
CREATE TABLE assistant_control (
    id INTEGER PRIMARY KEY CHECK(id = 1), epoch TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0
);
INSERT INTO assistant_control(id,epoch) VALUES (1, lower(hex(randomblob(16))));
CREATE TABLE assistant_work (
    id TEXT PRIMARY KEY, origin TEXT NOT NULL UNIQUE, session TEXT NOT NULL,
    prompt TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'READY',
    generation INTEGER NOT NULL DEFAULT 0, owner TEXT, expires REAL,
    created REAL NOT NULL, result TEXT, channel TEXT NOT NULL DEFAULT 'local',
    recipient TEXT NOT NULL DEFAULT '', delivery TEXT NOT NULL DEFAULT 'PENDING'
);
CREATE INDEX assistant_work_ready ON assistant_work(status, created);
CREATE TABLE assistant_transcript (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, work_id TEXT NOT NULL REFERENCES assistant_work(id),
    generation INTEGER NOT NULL, message TEXT NOT NULL
);
CREATE TABLE assistant_jobs (
    id TEXT PRIMARY KEY, session TEXT NOT NULL, prompt TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL CHECK(interval_seconds > 0),
    next_due REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    channel TEXT NOT NULL DEFAULT 'local', recipient TEXT NOT NULL DEFAULT ''
);
CREATE TABLE assistant_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL,
    name TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL,
    created REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX assistant_preference_current
ON assistant_preferences(session, name) WHERE active = 1;
CREATE TABLE assistant_skills (
    name TEXT NOT NULL, version TEXT NOT NULL, content TEXT NOT NULL,
    source TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(name, version)
);
CREATE UNIQUE INDEX assistant_skill_current ON assistant_skills(name) WHERE active = 1;
CREATE TABLE assistant_orders (
    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES assistant_work(id),
    proposal TEXT NOT NULL, digest TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount > 0),
    status TEXT NOT NULL DEFAULT 'DRAFT', approved_by TEXT, approved_until REAL,
    revoked INTEGER NOT NULL DEFAULT 0, receipt TEXT, created REAL NOT NULL
);
CREATE TABLE assistant_spending (
    id INTEGER PRIMARY KEY CHECK(id = 1), limit_pence INTEGER NOT NULL,
    reserved_pence INTEGER NOT NULL DEFAULT 0, spent_pence INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE assistant_channel_cursor (channel TEXT PRIMARY KEY, offset INTEGER NOT NULL);
"""
