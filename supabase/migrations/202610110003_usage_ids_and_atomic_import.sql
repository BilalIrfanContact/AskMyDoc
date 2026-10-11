-- Make recording AI spend safe to retry, and importing old spend history all-or-nothing.
--
-- `usage_id` is chosen by the backend before it records a call, so retrying a write whose reply was lost
-- can't count the call twice. `import_ai_usage` imports a whole history in one transaction, so an
-- interrupted import leaves nothing behind and can simply be run again.

begin;

alter table public.ai_usage add column usage_id uuid not null default gen_random_uuid();
alter table public.ai_usage add constraint ai_usage_usage_id_key unique (usage_id);

-- Insert every row of `p_rows` into an empty ledger and return how many there were.
create function public.import_ai_usage(p_rows jsonb) returns integer
language plpgsql
set search_path = ''
as $$
declare
  imported integer;
begin
  lock table public.ai_usage in exclusive mode;
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

revoke all on function public.import_ai_usage(jsonb) from public, anon, authenticated;
grant execute on function public.import_ai_usage(jsonb) to service_role;

commit;
