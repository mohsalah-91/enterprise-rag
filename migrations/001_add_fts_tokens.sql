ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS fts_tokens tsvector;

UPDATE document_chunks SET fts_tokens = to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''));

CREATE INDEX IF NOT EXISTS idx_fts_tokens ON document_chunks USING gin(fts_tokens);

CREATE OR REPLACE FUNCTION update_fts_tokens() RETURNS trigger AS $$
begin
  new.fts_tokens := to_tsvector('english', coalesce(new.title, '') || ' ' || coalesce(new.content, ''));
  return new;
end
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_fts_tokens ON document_chunks;
CREATE TRIGGER trg_update_fts_tokens
BEFORE INSERT OR UPDATE ON document_chunks
FOR EACH ROW EXECUTE FUNCTION update_fts_tokens();
