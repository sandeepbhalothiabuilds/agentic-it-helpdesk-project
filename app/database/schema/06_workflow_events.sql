CREATE TABLE IF NOT EXISTS case4.workflow_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    outcome TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_workflow_events_request_id
    ON case4.workflow_events (request_id);

CREATE INDEX IF NOT EXISTS ix_workflow_events_employee_id
    ON case4.workflow_events (employee_id);

CREATE INDEX IF NOT EXISTS ix_workflow_events_node_name
    ON case4.workflow_events (node_name);

CREATE INDEX IF NOT EXISTS ix_workflow_events_created_at
    ON case4.workflow_events (created_at DESC);

CREATE INDEX IF NOT EXISTS ix_workflow_events_stage_outcome
    ON case4.workflow_events (stage, outcome);

DO $$
BEGIN
    CREATE TRIGGER trg_workflow_events_updated_at
    BEFORE UPDATE ON case4.workflow_events
    FOR EACH ROW EXECUTE FUNCTION case4.set_updated_at();
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
