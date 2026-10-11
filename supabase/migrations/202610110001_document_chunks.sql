-- Searchable document chunks, moved here from the backend's local Chroma folder so indexes survive
-- restarts and redeploys on hosts with no persistent disk.
--
-- Each indexed document has one `document_indexes` row naming its current generation and the embedding
-- model that produced its vectors. Its chunks live in `document_chunks` under that generation. A write
-- inserts a new generation's chunks, then `commit_document_index` switches to it and deletes every other
-- generation in one transaction, so a failed or interrupted re-index leaves the previous chunks searchable.
-- Only the backend's service role reads or writes these tables.

begin;

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table public.document_indexes (
  document_id text primary key,
  generation uuid not null,
  embedding_model text not null,
  embedding_input text not null,
  chunk_count integer not null,
  updated_at timestamptz not null default now()
);

-- Vectors have no fixed dimension, so changing embedding models needs no migration. Search scans one
-- document's chunks exactly, which stays fast at a few thousand chunks and needs no vector index.
create table public.document_chunks (
  document_id text not null,
  generation uuid not null,
  chunk_index integer not null,
  chunk_id text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector not null,
  primary key (document_id, generation, chunk_index)
);

alter table public.document_indexes enable row level security;
alter table public.document_chunks enable row level security;
revoke all on public.document_indexes, public.document_chunks from anon, authenticated;
grant select, insert, update, delete on public.document_indexes, public.document_chunks to service_role;

-- Make `p_generation` the document's current chunks once all `p_expected_count` of them are stored, and
-- delete every other generation. Raises, changing nothing, if the count is wrong.
create function public.commit_document_index(
  p_document_id text,
  p_generation uuid,
  p_embedding_model text,
  p_embedding_input text,
  p_expected_count integer
) returns integer
language plpgsql
set search_path = ''
as $$
declare
  stored integer;
begin
  perform pg_advisory_xact_lock(hashtext('document_index:' || p_document_id));
  select count(*) into stored
  from public.document_chunks
  where document_id = p_document_id and generation = p_generation;
  if stored <> p_expected_count then
    raise exception 'stored % of % chunks', stored, p_expected_count;
  end if;

  insert into public.document_indexes (document_id, generation, embedding_model, embedding_input, chunk_count)
  values (p_document_id, p_generation, p_embedding_model, p_embedding_input, stored)
  on conflict (document_id) do update
    set generation = excluded.generation,
        embedding_model = excluded.embedding_model,
        embedding_input = excluded.embedding_input,
        chunk_count = excluded.chunk_count,
        updated_at = now();

  delete from public.document_chunks
  where document_id = p_document_id and generation <> p_generation;
  return stored;
end;
$$;

-- The `p_count` chunks of one generation closest to `p_query` by cosine distance, nearest first.
create function public.match_document_chunks(
  p_document_id text,
  p_generation uuid,
  p_query extensions.vector,
  p_count integer
) returns table (chunk_id text, chunk_index integer, content text, metadata jsonb)
language sql
stable
set search_path = ''
as $$
  select c.chunk_id, c.chunk_index, c.content, c.metadata
  from public.document_chunks c
  where c.document_id = p_document_id and c.generation = p_generation
  order by c.embedding operator(extensions.<=>) p_query, c.chunk_index
  limit p_count;
$$;

revoke all on function public.commit_document_index(text, uuid, text, text, integer) from public, anon, authenticated;
revoke all on function public.match_document_chunks(text, uuid, extensions.vector, integer) from public, anon, authenticated;
grant execute on function public.commit_document_index(text, uuid, text, text, integer) to service_role;
grant execute on function public.match_document_chunks(text, uuid, extensions.vector, integer) to service_role;

commit;
