-- The AI spend ledger, moved here from the backend's local `usage/ledger.jsonl` so the monthly budget stop
-- and free-allowance history survive restarts and redeploys on hosts with no persistent disk.
--
-- Each AI call adds one row with the tokens the provider reported and its list-price cost. Before a call,
-- the backend reads `ai_usage_totals` and works out this month's billed spend after free allowances.
-- Only the backend's service role reads or writes the ledger.

begin;

create table public.ai_usage (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  provider text not null,
  model text not null,
  task text not null,
  input_tokens bigint not null,
  output_tokens bigint not null default 0,
  cost_usd double precision not null
);

create index ai_usage_created_at on public.ai_usage (created_at);

alter table public.ai_usage enable row level security;
revoke all on public.ai_usage from anon, authenticated;
grant select, insert on public.ai_usage to service_role;
grant usage on sequence public.ai_usage_id_seq to service_role;

-- Per model: tokens used before `p_month_start`, and tokens and list-price cost from then until `p_month_end`.
create function public.ai_usage_totals(p_month_start timestamptz, p_month_end timestamptz)
returns table (provider text, model text, tokens_before bigint, tokens_in_month bigint, cost_in_month double precision)
language sql
stable
set search_path = ''
as $$
  select
    u.provider,
    u.model,
    coalesce(sum(u.input_tokens + u.output_tokens) filter (where u.created_at < p_month_start), 0)::bigint,
    coalesce(sum(u.input_tokens + u.output_tokens) filter (where u.created_at >= p_month_start and u.created_at < p_month_end), 0)::bigint,
    coalesce(sum(u.cost_usd) filter (where u.created_at >= p_month_start and u.created_at < p_month_end), 0)
  from public.ai_usage u
  group by u.provider, u.model;
$$;

revoke all on function public.ai_usage_totals(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.ai_usage_totals(timestamptz, timestamptz) to service_role;

commit;
