-- Apply after the demo-limit migrations, before deploying retry-aware chat.
begin;
alter table public.messages add column request_id uuid;
create table public.chat_turns (
  user_id uuid not null,
  request_id uuid not null,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  question text not null,
  state text not null check (state in ('generating','failed','generated','completed')),
  operation_id uuid not null references public.demo_operations(id),
  result jsonb,
  primary key (user_id, request_id)
);
create index chat_turns_conversation on public.chat_turns(conversation_id);
alter table public.chat_turns enable row level security;
revoke all on public.chat_turns from public, anon, authenticated;
grant all on public.chat_turns to service_role;

-- The account lock also serializes quota reservations. Every message/receipt
-- transition is transactional; generation happens outside this function.
create function public.chat_turn(p_action text, p_user_id uuid, p_conversation_id uuid,
  p_request_id uuid, p_question text, p_result jsonb default null)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare turn chat_turns; reservation jsonb;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 1));
  -- Lock the conversation against deletion while committing messages.
  perform 1 from conversations where id = p_conversation_id and user_id = p_user_id for key share;
  if not found then return jsonb_build_object('error','not_found'); end if;
  select * into turn from chat_turns where user_id = p_user_id and request_id = p_request_id;
  if found and (turn.conversation_id <> p_conversation_id or turn.question <> p_question) then
    return jsonb_build_object('error','conflict');
  end if;
  if p_action = 'claim' then
    if turn.state in ('generated','completed') then return to_jsonb(turn); end if;
    if turn.state = 'generating' then return jsonb_build_object('error','busy'); end if;
    reservation := demo_operation('reserve',p_user_id,'question');
    if reservation ? 'error' then return reservation; end if;
    if turn.request_id is null then
      insert into chat_turns(user_id,request_id,conversation_id,question,state,operation_id)
      values (p_user_id,p_request_id,p_conversation_id,p_question,'generating',(reservation->>'id')::uuid)
      returning * into turn;
      insert into messages(id,conversation_id,role,content,request_id)
      values (gen_random_uuid(),p_conversation_id,'user',p_question,p_request_id);
    else
      update chat_turns set state='generating',operation_id=(reservation->>'id')::uuid
      where user_id=p_user_id and request_id=p_request_id returning * into turn;
    end if;
    return to_jsonb(turn);
  end if;
  if turn.request_id is null then return jsonb_build_object('error','not_found'); end if;
  if p_action = 'save' then
    if turn.state = 'generating' then
      if p_result is null or not (p_result ?& array['answer','answer_status','citations','intent','retrieval_mode'])
        or jsonb_typeof(p_result->'answer') is distinct from 'string'
        or (p_result->>'answer_status' in ('answered','insufficient_context')) is not true
        or (p_result->>'intent' in ('qa','summary')) is not true
        or (p_result->>'retrieval_mode' in ('head','semantic')) is not true
        or jsonb_typeof(p_result->'citations') is distinct from 'array' then
        raise exception 'Invalid answer receipt';
      end if;
      update chat_turns set state='generated',result=p_result
      where user_id=p_user_id and request_id=p_request_id returning * into turn;
    elsif turn.state not in ('generated','completed') then return jsonb_build_object('error','busy');
    end if;
  elsif p_action = 'complete' then
    if turn.state = 'generated' then
      insert into messages(id,conversation_id,role,content,request_id)
      values (gen_random_uuid(),p_conversation_id,'assistant',
        'askmydoc:answer:v1:' || jsonb_build_object('content',turn.result->>'answer',
          'answer_status',turn.result->>'answer_status','citations',turn.result->'citations')::text,p_request_id);
      reservation := demo_operation('complete',p_user_id,'question',turn.operation_id,turn.result);
      if reservation ? 'error' then raise exception 'Question reservation cannot complete'; end if;
      update chat_turns set state='completed' where user_id=p_user_id and request_id=p_request_id returning * into turn;
    elsif turn.state <> 'completed' then return jsonb_build_object('error','busy'); end if;
  elsif p_action = 'fail' then
    if turn.state = 'generating' then
      perform demo_operation('fail',p_user_id,'question',turn.operation_id);
      update chat_turns set state='failed' where user_id=p_user_id and request_id=p_request_id returning * into turn;
    end if;
  else raise exception 'Invalid turn action'; end if;
  return to_jsonb(turn);
end $$;
revoke all on function public.chat_turn(text,uuid,uuid,uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.chat_turn(text,uuid,uuid,uuid,text,jsonb) to service_role;
commit;
