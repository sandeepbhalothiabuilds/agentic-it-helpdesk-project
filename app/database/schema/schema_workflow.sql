CREATE TABLE IF NOT EXISTS case4.workflow_sessions (
    request_id text PRIMARY KEY,
    employee_id text NOT NULL,
    message text NOT NULL,
    intent text,
    current_node text NOT NULL DEFAULT 'start',
    status text NOT NULL DEFAULT 'in_progress',
    needs_confirmation boolean NOT NULL DEFAULT false,
    ticket_id text,
    response_payload jsonb,
    final_state jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS case4.retrieval_logs (
    id bigserial PRIMARY KEY,
    request_id text NOT NULL,
    employee_id text NOT NULL,
    query_text text NOT NULL,
    document_name text,
    chunk_id text,
    score numeric,
    retrieved_metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_employee_id
    ON case4.workflow_sessions (employee_id);

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_status
    ON case4.workflow_sessions (status);

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_updated_at
    ON case4.workflow_sessions (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_sessions_intent_status
    ON case4.workflow_sessions (intent, status);

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_request_id
    ON case4.retrieval_logs (request_id);

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_employee_id
    ON case4.retrieval_logs (employee_id);

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_created_at
    ON case4.retrieval_logs (created_at DESC);

DO $$
BEGIN
    CREATE TRIGGER trg_workflow_sessions_updated_at
    BEFORE UPDATE ON case4.workflow_sessions
    FOR EACH ROW EXECUTE FUNCTION case4.set_updated_at();
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
