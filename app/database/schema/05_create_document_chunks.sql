CREATE TABLE IF NOT EXISTS case4.document_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_document TEXT NOT NULL,
    workflow TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_json JSONB NOT NULL,
    chunk_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_document_chunks_workflow
    ON case4.document_chunks (workflow);

CREATE INDEX IF NOT EXISTS ix_document_chunks_source_document
    ON case4.document_chunks (source_document);

CREATE INDEX IF NOT EXISTS ix_document_chunks_is_active
    ON case4.document_chunks (is_active);

CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id
    ON case4.document_chunks ((chunk_metadata->>'document_id'));

CREATE INDEX IF NOT EXISTS ix_document_chunks_source_active
    ON case4.document_chunks (source_document, is_active);

DO $$
BEGIN
    CREATE TRIGGER trg_document_chunks_updated_at
    BEFORE UPDATE ON case4.document_chunks
    FOR EACH ROW EXECUTE FUNCTION case4.set_updated_at();
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
