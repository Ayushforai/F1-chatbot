-- Optional. Requires the pgvector extension (compose uses pgvector/pgvector:pg16).
-- Skip on hosts that only offer vanilla Postgres; FAISS remains the RAG runtime.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE rag.regulation_chunks
    ADD COLUMN IF NOT EXISTS embedding vector(768);

ALTER TABLE rag.historical_documents
    ADD COLUMN IF NOT EXISTS embedding vector(768);
