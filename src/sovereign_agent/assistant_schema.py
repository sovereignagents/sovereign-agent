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


SCHEMA_20 = """
CREATE TABLE assistant_daily (
    session TEXT NOT NULL, day INTEGER NOT NULL,
    controls INTEGER NOT NULL DEFAULT 0,
    admitted INTEGER NOT NULL DEFAULT 0, model_calls INTEGER NOT NULL DEFAULT 0,
    estimated_cost_pence INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(session,day)
);
CREATE TABLE assistant_channel_leases (
    channel TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL
);
ALTER TABLE assistant_orders ADD COLUMN target TEXT NOT NULL DEFAULT 'lucy-local';
ALTER TABLE assistant_work ADD COLUMN estimated_cost_pence INTEGER NOT NULL DEFAULT 0;
ALTER TABLE assistant_work ADD COLUMN available_after REAL NOT NULL DEFAULT 0;
ALTER TABLE assistant_work ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE assistant_work ADD COLUMN control INTEGER NOT NULL DEFAULT 0;
CREATE TRIGGER assistant_order_identity_immutable
BEFORE UPDATE OF id,work_id,proposal,digest,amount,target ON assistant_orders
BEGIN SELECT RAISE(ABORT, 'order identity is immutable'); END;
"""


SCHEMA_21 = """
ALTER TABLE assistant_work ADD COLUMN subject TEXT NOT NULL DEFAULT '';
CREATE TRIGGER assistant_work_subject_immutable BEFORE UPDATE OF subject ON assistant_work
BEGIN SELECT RAISE(ABORT, 'work subject is immutable'); END;
CREATE TABLE assistant_stock_conditions (
    id TEXT PRIMARY KEY, session TEXT NOT NULL, subject TEXT NOT NULL REFERENCES products(sku),
    armed INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1, channel TEXT NOT NULL DEFAULT 'local',
    recipient TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX assistant_stock_condition_active_subject
ON assistant_stock_conditions(subject) WHERE enabled=1;
CREATE TABLE assistant_deliveries (
    order_id TEXT PRIMARY KEY REFERENCES assistant_orders(id), reference TEXT NOT NULL,
    received_by TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
    received_at REAL NOT NULL
);
"""


SCHEMA_22 = """
ALTER TABLE assistant_work ADD COLUMN role TEXT NOT NULL DEFAULT 'shop';
ALTER TABLE assistant_work ADD COLUMN billing_session TEXT NOT NULL DEFAULT '';
CREATE TRIGGER assistant_work_role_immutable BEFORE UPDATE OF role,billing_session
ON assistant_work BEGIN SELECT RAISE(ABORT, 'work role and billing are immutable'); END;
CREATE TRIGGER assistant_work_intake_immutable BEFORE UPDATE OF origin,session,prompt
ON assistant_work BEGIN SELECT RAISE(ABORT, 'work intake is immutable'); END;
CREATE TABLE assistant_delegations (
    work_id TEXT PRIMARY KEY REFERENCES assistant_work(id),
    parent_id TEXT NOT NULL UNIQUE REFERENCES assistant_work(id),
    deadline REAL NOT NULL, model_calls_limit INTEGER NOT NULL,
    estimated_call_pence INTEGER NOT NULL, budget_pence INTEGER NOT NULL,
    model_calls INTEGER NOT NULL DEFAULT 0
);
CREATE TRIGGER assistant_delegation_immutable
BEFORE UPDATE OF work_id,parent_id,deadline,model_calls_limit,estimated_call_pence,budget_pence
ON assistant_delegations BEGIN SELECT RAISE(ABORT, 'assignment contract is immutable'); END;
"""


SCHEMA_23 = """
ALTER TABLE assistant_daily ADD COLUMN call_limit INTEGER NOT NULL DEFAULT 100;
ALTER TABLE assistant_daily ADD COLUMN cost_limit INTEGER NOT NULL DEFAULT 1000;
ALTER TABLE assistant_daily ADD COLUMN history_complete INTEGER NOT NULL DEFAULT 1;
CREATE TABLE assistant_supplier_bindings (
    target TEXT PRIMARY KEY, account TEXT NOT NULL, epoch INTEGER NOT NULL
);
CREATE TABLE assistant_recovery_runs (
    epoch TEXT PRIMARY KEY, plan_digest TEXT NOT NULL, account TEXT NOT NULL,
    provider_epoch INTEGER NOT NULL, completed_at REAL NOT NULL
);
"""
