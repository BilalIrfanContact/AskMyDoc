-- `import_ai_usage` took an exclusive lock on `ai_usage`, which needs UPDATE, DELETE or TRUNCATE on the table,
-- but the backend's service role may only SELECT and INSERT there. A transaction-scoped advisory lock serializes
-- imports just as well without widening that role's privileges. `create or replace` keeps the existing grants.

begin;

-- Insert every row of `p_rows` into an empty ledger and return how many there were.
create or replace function public.import_ai_usage(p_rows jsonb) returns integer
language plpgsql
set search_path = ''
as $$
declare
  imported integer;
begin
  -- Concurrent imports take turns, so the emptiness check below holds until this one commits.
  perform pg_advisory_xact_lock(hashtext('import_ai_usage'));
  if exists (select 1 from public.ai_usage) then
    raise exception 'ai_usage already has rows';
  end if;
  insert into public.ai_usage (created_at, provider, model, task, input_tokens, output_tokens, cost_usd)
  select
    (row ->> 'created_at')::timestamptz,
    row ->> 'provider',
    row ->> 'model',
    row ->> 'task',
    (row ->> 'input_tokens')::bigint,
    (row ->> 'output_tokens')::bigint,
    (row ->> 'cost_usd')::double precision
  from jsonb_array_elements(p_rows) as row;
  get diagnostics imported = row_count;
  return imported;
end;
$$;

commit;
