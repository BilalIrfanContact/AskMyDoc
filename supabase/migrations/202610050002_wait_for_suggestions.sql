-- Apply after 202610050001_demo_limits.sql, including on installations already using that migration.
begin;
create or replace function public.demo_suggestions(p_user_id uuid, p_document_id uuid)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare op demo_operations;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 1));
  -- Upload and suggestion IDs are separate; the document ID lives in the payload.
  select * into op from demo_operations where user_id = p_user_id and kind = 'suggestions' and payload->>'document_id' = p_document_id::text;
  if found then return jsonb_build_object('generate', false, 'pending', op.state = 'running',
    'suggestions', coalesce(op.result,'[]'::jsonb)); end if;
  insert into demo_operations(user_id,kind,state,payload) values
    (p_user_id,'suggestions','running',jsonb_build_object('document_id',p_document_id)) returning * into op;
  return jsonb_build_object('generate',true,'id',op.id);
end $$;

commit;
