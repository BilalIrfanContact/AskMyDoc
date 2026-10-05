-- Run with the Supabase SQL editor before deploying either application.
begin;
create table public.demo_operations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  kind text not null check (kind in ('question', 'upload', 'suggestions')),
  state text not null default 'pending' check (state in ('pending','running','completed','failed')),
  expires_at timestamptz not null default now() + interval '2 hours 5 minutes',
  payload jsonb not null default '{}',
  result jsonb,
  storage_cleaned boolean not null default false,
  created_at timestamptz not null default now()
);
create index demo_operations_account on public.demo_operations(user_id, kind);
create table public.demo_rate_windows (
  key text primary key,
  started_at timestamptz not null,
  attempts integer not null
);
alter table public.demo_operations enable row level security;
alter table public.demo_rate_windows enable row level security;
revoke all on public.demo_operations, public.demo_rate_windows from public, anon, authenticated;
grant all on public.demo_operations, public.demo_rate_windows to service_role;

-- Fixed windows start on the first attempt, rather than on a clock boundary.
create function public.demo_rate_limit(p_key text, p_limit integer, p_seconds integer)
returns integer language plpgsql security definer set search_path = public, pg_temp as $$
declare current_window demo_rate_windows; remaining integer; checked_at timestamptz;
begin
  if p_limit < 1 or p_seconds < 1 then raise exception 'Invalid rate window'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_key, 0));
  -- Transaction-start time can precede another caller that acquired the lock first.
  checked_at := clock_timestamp();
  select * into current_window from demo_rate_windows where key = p_key;
  if not found or current_window.started_at + make_interval(secs => p_seconds) <= checked_at then
    insert into demo_rate_windows values (p_key, checked_at, 1)
      on conflict (key) do update set started_at = checked_at, attempts = 1;
    return 0;
  end if;
  if current_window.attempts >= p_limit then
    remaining := ceil(extract(epoch from current_window.started_at + make_interval(secs => p_seconds) - checked_at));
    return greatest(1, remaining);
  end if;
  update demo_rate_windows set attempts = attempts + 1 where key = p_key;
  return 0;
end $$;

-- All account reservations serialize on the same lock, including across app instances.
create function public.demo_operation(p_action text, p_user_id uuid, p_kind text,
  p_id uuid default null, p_payload jsonb default '{}')
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare op demo_operations; allowance integer; used integer; retry integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 1));
  if p_action = 'reserve' then
    if p_kind not in ('question','upload') then raise exception 'Invalid operation kind'; end if;
    allowance := case when p_kind = 'question' then 20 else 3 end;
    select count(*) into used from demo_operations where user_id = p_user_id and kind = p_kind
      and (state in ('running','completed') or (state = 'pending' and expires_at > now())
        or (kind = 'upload' and state = 'failed' and payload->>'signed_upload' = 'true' and expires_at > now()));
    if used >= allowance then
      if p_kind = 'upload' and (select count(*) from demo_operations
          where user_id = p_user_id and kind = 'upload' and state = 'completed') < allowance then
        return jsonb_build_object('error','reserved');
      end if;
      return jsonb_build_object('error','quota');
    end if;
    if p_kind = 'question' then
      retry := demo_rate_limit('question:' || p_user_id, 5, 60);
      if retry > 0 then return jsonb_build_object('error','rate','retry_after',retry); end if;
    end if;
    insert into demo_operations(user_id,kind,state,payload)
      values (p_user_id,p_kind,case when p_kind = 'question' then 'running' else 'pending' end,p_payload)
      returning * into op;
    return to_jsonb(op);
  end if;
  select * into op from demo_operations where id = p_id and user_id = p_user_id and kind = p_kind;
  if not found then return jsonb_build_object('error','not_found'); end if;
  if p_action = 'claim' then
    if op.state = 'completed' then return to_jsonb(op); end if;
    if op.state = 'running' then return jsonb_build_object('error','busy'); end if;
    if op.state <> 'pending' or op.expires_at <= now() then return jsonb_build_object('error','expired'); end if;
    update demo_operations set state = 'running' where id = op.id returning * into op;
  elsif p_action = 'complete' then
    if op.state <> 'running' then return jsonb_build_object('error','busy'); end if;
    update demo_operations set state = 'completed', result = p_payload where id = op.id returning * into op;
  elsif p_action = 'fail' then
    if op.state not in ('pending','running') then return to_jsonb(op); end if;
    update demo_operations set state = 'failed' where id = op.id returning * into op;
  elsif p_action <> 'get' then raise exception 'Invalid operation action';
  end if;
  return to_jsonb(op);
end $$;

-- One suggestion attempt per document. A timeout does not allow another model call.
create function public.demo_suggestions(p_user_id uuid, p_document_id uuid)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare op demo_operations;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 1));
  -- Upload and suggestion IDs are separate; the document ID lives in the payload.
  select * into op from demo_operations where user_id = p_user_id and kind = 'suggestions' and payload->>'document_id' = p_document_id::text;
  if found then return jsonb_build_object('generate', false, 'suggestions', coalesce(op.result,'[]'::jsonb)); end if;
  insert into demo_operations(user_id,kind,state,payload) values
    (p_user_id,'suggestions','running',jsonb_build_object('document_id',p_document_id)) returning * into op;
  return jsonb_build_object('generate',true,'id',op.id);
end $$;

-- Once signed permissions expire, remove abandoned objects and any recreated
-- objects whose completed document was subsequently deleted. Keep quota receipts.
create function public.demo_expired_uploads()
returns setof public.demo_operations language sql security definer
set search_path = public, pg_temp as $$
  select op.* from demo_operations op
  where op.kind = 'upload' and op.payload->>'signed_upload' = 'true'
    and not op.storage_cleaned and op.expires_at <= now()
    and (op.state in ('pending','failed') or (op.state = 'completed' and not exists (
      select 1 from documents d where d.id::text = op.id::text and d.user_id::text = op.user_id::text)))
  order by op.created_at limit 100;
$$;

revoke all on function public.demo_rate_limit(text,integer,integer),
  public.demo_operation(text,uuid,text,uuid,jsonb), public.demo_suggestions(uuid,uuid), public.demo_expired_uploads() from public, anon, authenticated;
grant execute on function public.demo_rate_limit(text,integer,integer),
  public.demo_operation(text,uuid,text,uuid,jsonb), public.demo_suggestions(uuid,uuid), public.demo_expired_uploads() to service_role;

-- Existing documents count toward the upload allowance. Deletion never deletes these receipts.
insert into public.demo_operations (user_id,kind,state,payload)
select user_id::uuid,'upload','completed',jsonb_build_object('document_id',id) from public.documents;

-- Even broad existing storage policies cannot expose this private bucket.
create policy askmydoc_uploads_private on storage.objects as restrictive
for all to anon, authenticated
using (bucket_id <> 'askmydoc-uploads') with check (bucket_id <> 'askmydoc-uploads');

-- A dedicated private bucket enforces size before the backend downloads or parses a file.
insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values ('askmydoc-uploads','askmydoc-uploads',false,15000000,array['application/pdf','text/markdown'])
on conflict (id) do update set public=false,file_size_limit=15000000,allowed_mime_types=excluded.allowed_mime_types;
commit;
