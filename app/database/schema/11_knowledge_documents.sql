CREATE TABLE IF NOT EXISTS case4.knowledge_documents (
    document_id text PRIMARY KEY,
    source_document text NOT NULL,
    original_filename text NOT NULL,
    workflow text NOT NULL,
    revision_number integer NOT NULL,
    file_hash text NOT NULL,
    storage_type text NOT NULL DEFAULT 'local',
    storage_path text NOT NULL,
    mime_type text,
    uploaded_by text NOT NULL DEFAULT 'system',
    is_active boolean NOT NULL DEFAULT true,
    is_latest boolean NOT NULL DEFAULT true,
    created_by text NOT NULL DEFAULT 'system',
    updated_by text NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_knowledge_documents_source_revision UNIQUE (source_document, revision_number)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_source_document
    ON case4.knowledge_documents (source_document);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_source_revision
    ON case4.knowledge_documents (source_document, revision_number DESC);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_source_active
    ON case4.knowledge_documents (source_document, is_active, is_latest);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_file_hash
    ON case4.knowledge_documents (file_hash);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_is_active
    ON case4.knowledge_documents (is_active);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_is_latest
    ON case4.knowledge_documents (is_latest);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_workflow
    ON case4.knowledge_documents (workflow);

DO $$
BEGIN
    CREATE TRIGGER trg_knowledge_documents_updated_at
    BEFORE UPDATE ON case4.knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION case4.set_updated_at();
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
