"""Exercise the production SQL with a disposable local PostgreSQL server, never Supabase."""
import concurrent.futures
import glob
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4


class DemoLimitsDatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binaries = sorted(glob.glob('/usr/lib/postgresql/*/bin/pg_ctl'))
        if not binaries or os.getuid() == 0:
            if os.getenv('ASKMYDOC_REQUIRE_POSTGRES') == '1':
                raise RuntimeError('PostgreSQL is required for the database limit tests')
            raise unittest.SkipTest('Local PostgreSQL binaries and a non-root user are required')
        cls.bin = Path(binaries[-1]).parent
        cls.temp = tempfile.TemporaryDirectory(prefix='askmydoc-limits-')
        cls.data = Path(cls.temp.name) / 'data'
        cls.socket = Path(cls.temp.name)
        subprocess.run([str(cls.bin / 'initdb'), '-D', str(cls.data), '-A', 'trust', '--no-locale', '-E', 'UTF8'], check=True, capture_output=True)
        subprocess.run([str(cls.bin / 'pg_ctl'), '-D', str(cls.data), '-l', str(cls.socket / 'server.log'),
            '-o', f"-k {cls.socket} -h '' -p 55483", '-w', 'start'], check=True, capture_output=True)
        cls.addClassCleanup(cls.stop_database)
        cls.legacy_user = str(uuid4())
        cls.sql("create role anon; create role authenticated; create role service_role; create schema storage; "
            "create table storage.buckets(id text primary key, name text, public boolean, file_size_limit bigint, allowed_mime_types text[]); "
            "create table public.documents(id uuid, user_id uuid); "
            "create table public.conversations(id uuid primary key, user_id uuid, document_id uuid); "
            "create table public.messages(id uuid primary key, conversation_id uuid references conversations(id), role text, content text, created_at timestamptz default now()); create table storage.objects(bucket_id text); alter table storage.objects enable row level security;")
        cls.sql(f"insert into documents select gen_random_uuid(),'{cls.legacy_user}' from generate_series(1,3);")
        migrations = Path(__file__).resolve().parents[2] / 'supabase/migrations'
        for migration in sorted(migrations.glob('*.sql')):
            cls.sql(migration.read_text())

    @classmethod
    def stop_database(cls):
        subprocess.run([str(cls.bin / 'pg_ctl'), '-D', str(cls.data), '-m', 'immediate', 'stop'], capture_output=True)
        cls.temp.cleanup()

    @classmethod
    def sql(cls, query):
        result = subprocess.run([str(cls.bin / 'psql'), '-h', str(cls.socket), '-p', '55483', '-d', 'postgres',
            '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-c', query], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def operation(self, action, user, kind, operation_id=None):
        identifier = f"'{operation_id}'" if operation_id else 'null'
        return json.loads(self.sql(f"""set role service_role; select public.demo_operation('{action}','{user}','{kind}',{identifier},'{{"signed_upload":true}}');"""))

    def test_concurrent_uploads_cannot_reserve_more_than_three(self):
        user = uuid4()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: self.operation('reserve', user, 'upload'), range(12)))
        self.assertEqual(sum('id' in result for result in results), 3)
        self.assertEqual(sum(result.get('error') == 'reserved' for result in results), 9)

    def test_questions_stop_at_twenty_and_failures_refund(self):
        user = uuid4()
        first = self.operation('reserve', user, 'question')
        self.operation('fail', user, 'question', first['id'])
        for _ in range(20):
            self.sql(f"delete from demo_rate_windows where key = 'question:{user}';")
            question = self.operation('reserve', user, 'question')
            self.operation('complete', user, 'question', question['id'])
        self.assertEqual(self.operation('reserve', user, 'question')['error'], 'quota')

    def test_question_burst_is_shared_and_does_not_reserve_rejected_attempts(self):
        user = uuid4()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.operation('reserve', user, 'question'), range(10)))
        self.assertEqual(sum('id' in result for result in results), 5)
        self.assertEqual(sum(result.get('error') == 'rate' for result in results), 5)
        self.assertTrue(all(1 <= result['retry_after'] <= 60 for result in results if 'error' in result))

    def test_upload_claim_is_owner_scoped_and_cannot_process_twice(self):
        user = uuid4()
        upload = self.operation('reserve', user, 'upload')
        self.assertEqual(self.operation('claim', uuid4(), 'upload', upload['id'])['error'], 'not_found')
        self.assertEqual(self.operation('claim', user, 'upload', upload['id'])['state'], 'running')
        self.assertEqual(self.operation('claim', user, 'upload', upload['id'])['error'], 'busy')
        self.operation('complete', user, 'upload', upload['id'])
        self.assertEqual(self.operation('claim', user, 'upload', upload['id'])['state'], 'completed')

    def test_abandoned_and_failed_signed_uploads_hold_slots_until_token_expiry(self):
        user = uuid4()
        uploads = [self.operation('reserve', user, 'upload') for _ in range(3)]
        self.operation('fail', user, 'upload', uploads[0]['id'])
        self.assertEqual(self.operation('reserve', user, 'upload')['error'], 'reserved')
        self.sql(f"update demo_operations set expires_at = now() - interval '1 second' where user_id = '{user}';")
        self.assertIn('id', self.operation('reserve', user, 'upload'))
        self.assertEqual(self.operation('claim', user, 'upload', uploads[1]['id'])['error'], 'expired')

    def test_suggestions_are_claimed_once_even_when_pending(self):
        user, document = uuid4(), uuid4()
        query = f"set role service_role; select demo_suggestions('{user}','{document}');"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: json.loads(self.sql(query)), range(8)))
        self.assertEqual(sum(result['generate'] for result in results), 1)
        self.assertTrue(all(result['pending'] for result in results if not result['generate']))
        first = next(result for result in results if result['generate'])
        self.sql(f"select demo_operation('complete','{user}','suggestions','{first['id']}','[\"Question?\"]');")
        cached = json.loads(self.sql(query))
        self.assertEqual(cached['suggestions'], ['Question?'])
        self.assertFalse(cached['pending'])

    def test_expired_suggestions_stop_waiting_without_another_generation(self):
        user, document = uuid4(), uuid4()
        query = f"set role service_role; select demo_suggestions('{user}','{document}');"
        first = json.loads(self.sql(query))
        self.sql(f"update demo_operations set expires_at = now() - interval '1 second' where id = '{first['id']}';")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: json.loads(self.sql(query)), range(4)))
        for result in results:
            self.assertFalse(result['generate'])
            self.assertFalse(result['pending'])
            self.assertEqual(result['suggestions'], [])
        self.assertEqual(self.sql(f"select count(*) from demo_operations where user_id = '{user}';"), '1')
        # A slow original worker can still save its result; expiry never starts a second AI call.
        self.sql(f"select demo_operation('complete','{user}','suggestions','{first['id']}','[\"Question?\"]');")
        self.assertEqual(json.loads(self.sql(query))['suggestions'], ['Question?'])

    def test_public_roles_cannot_bypass_limits_and_bucket_enforces_size(self):
        for role in ('anon', 'authenticated'):
            with self.assertRaisesRegex(AssertionError, 'permission denied'):
                self.sql(f"set role {role}; select demo_operation('reserve','{uuid4()}','upload');")
            with self.assertRaisesRegex(AssertionError, 'permission denied'):
                self.sql(f"set role {role}; select demo_suggestions('{uuid4()}','{uuid4()}');")
            with self.assertRaisesRegex(AssertionError, 'permission denied'):
                self.sql(f"set role {role}; select * from demo_operations;")
        self.assertEqual(self.sql("select public || ':' || file_size_limit from storage.buckets where id='askmydoc-uploads';"), 'false:15000000')

    def test_auth_windows_limit_attempts_and_reset_only_after_cooldown(self):
        for scope, limit, seconds in [('login', 5, 60), ('signup', 3, 3600)]:
            key = f'{scope}:{uuid4()}'
            query = f"set role service_role; select demo_rate_limit('{key}',{limit},{seconds});"
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(lambda _: int(self.sql(query)), range(10)))
            self.assertEqual(results.count(0), limit)
            self.assertTrue(all(1 <= result <= seconds for result in results if result))
            self.sql(f"update demo_rate_windows set started_at = now() - interval '{seconds + 1} seconds' where key = '{key}';")
            self.assertEqual(self.sql(query), '0')

    def test_failed_legacy_upload_refunds_without_waiting_for_unused_token(self):
        user = uuid4()
        query = f"select demo_operation('reserve','{user}','upload');"
        for _ in range(5):
            op = json.loads(self.sql(query))
            self.operation('fail', user, 'upload', op['id'])
        self.assertIn('id', json.loads(self.sql(query)))

    def test_preexisting_documents_and_deleted_documents_do_not_get_free_uploads(self):
        user = self.legacy_user
        self.assertEqual(self.sql(f"select count(*) from demo_operations where user_id = '{user}' and kind = 'upload' and state = 'completed';"), '3')
        self.sql(f"delete from documents where user_id = '{user}';")
        self.assertEqual(self.operation('reserve', user, 'upload')['error'], 'quota')


    def test_concurrent_requests_cannot_spend_the_last_question_twice(self):
        user = uuid4()
        self.sql(f"insert into demo_operations(user_id,kind,state) select '{user}','question','completed' from generate_series(1,19);")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.operation('reserve', user, 'question'), range(10)))
        self.assertEqual(sum('id' in result for result in results), 1)
        self.assertEqual(sum(result.get('error') == 'quota' for result in results), 9)

    def test_bucket_policy_blocks_broad_client_storage_permissions(self):
        self.sql("grant usage on schema storage to anon,authenticated; grant select,insert on storage.objects to anon,authenticated; "
            "create policy fixture_permissive on storage.objects for all to anon,authenticated using(true) with check(true); "
            "insert into storage.objects values ('askmydoc-uploads'),('another-bucket');")
        for role in ('anon','authenticated'):
            self.assertEqual(self.sql(f"set role {role}; select bucket_id from storage.objects;"), 'another-bucket')
            with self.assertRaisesRegex(AssertionError, 'row-level security'):
                self.sql(f"set role {role}; insert into storage.objects values ('askmydoc-uploads');")

    def test_cleanup_excludes_running_and_live_documents_and_preserves_receipts(self):
        user = uuid4()
        pending, failed, running = [self.operation('reserve', user, 'upload') for _ in range(3)]
        # Use a second account for a live completed document.
        completed_user = uuid4()
        completed = self.operation('reserve', completed_user, 'upload')
        self.operation('fail', user, 'upload', failed['id'])
        self.operation('claim', user, 'upload', running['id'])
        self.operation('claim', completed_user, 'upload', completed['id'])
        self.operation('complete', completed_user, 'upload', completed['id'])
        self.sql(f"insert into documents values ('{completed['id']}','{completed_user}'); "
            f"update demo_operations set expires_at=now()-interval '1 second' where user_id in ('{user}','{completed_user}');")
        candidates = json.loads(self.sql("select coalesce(jsonb_agg(id),'[]') from demo_expired_uploads();"))
        self.assertIn(pending['id'], candidates)
        self.assertIn(failed['id'], candidates)
        self.assertNotIn(running['id'], candidates)
        self.assertNotIn(completed['id'], candidates)
        self.sql(f"delete from documents where id = '{completed['id']}';")
        candidates = json.loads(self.sql("select coalesce(jsonb_agg(id),'[]') from demo_expired_uploads();"))
        self.assertIn(completed['id'], candidates)
        self.assertEqual(self.operation('get', completed_user, 'upload', completed['id'])['state'], 'completed')

    def new_turn(self):
        user, conversation, request = map(str, (uuid4(), uuid4(), uuid4()))
        self.sql(f"insert into conversations values ('{conversation}','{user}',gen_random_uuid());")
        return user, conversation, request

    def turn(self, action, user, conversation, request, question="Refund window?", result=None):
        payload = "null" if result is None else "'" + json.dumps(result).replace("'", "''") + "'::jsonb"
        escaped = question.replace("'", "''")
        return json.loads(self.sql(f"set role service_role; select chat_turn('{action}','{user}','{conversation}','{request}','{escaped}',{payload});"))

    def answer_receipt(self):
        return dict(answer="30 days", intent="qa", retrieval_mode="semantic", answer_status="answered",
                    citations=[dict(chunk_id="chunk-1", excerpt="Refunds within 30 days.")])

    def test_concurrent_turn_retries_claim_once_and_replay_at_quota(self):
        user, conversation, request = self.new_turn()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: self.turn('claim', user, conversation, request), range(8)))
        self.assertEqual(sum(r.get('state') == 'generating' for r in claims), 1)
        self.assertEqual(sum(r.get('error') == 'busy' for r in claims), 7)
        self.assertEqual(self.sql(f"select count(*) from messages where conversation_id='{conversation}';"), '1')
        receipt = self.answer_receipt()
        self.turn('save', user, conversation, request, result=receipt)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            completions = list(pool.map(lambda _: self.turn('complete', user, conversation, request), range(8)))
        self.assertTrue(all(r['result'] == receipt for r in completions))
        self.assertEqual(self.sql(f"select count(*) from messages where conversation_id='{conversation}';"), '2')
        self.sql(f"insert into demo_operations(user_id,kind,state) select '{user}','question','completed' from generate_series(1,19);")
        self.assertEqual(self.turn('claim', user, conversation, request)['result'], receipt)
        self.assertEqual(self.turn('claim', user, conversation, str(uuid4()))['error'], 'quota')

    def test_failed_generation_reuses_user_message_and_refunds_reservation(self):
        user, conversation, request = self.new_turn()
        first = self.turn('claim', user, conversation, request)
        self.turn('fail', user, conversation, request)
        self.assertEqual(self.operation('get', user, 'question', first['operation_id'])['state'], 'failed')
        second = self.turn('claim', user, conversation, request)
        self.assertNotEqual(second['operation_id'], first['operation_id'])
        self.assertEqual(self.sql(f"select count(*) from messages where conversation_id='{conversation}';"), '1')
        self.turn('save', user, conversation, request, result=self.answer_receipt())
        self.turn('complete', user, conversation, request)
        self.assertEqual(self.sql(f"select count(*) from demo_operations where user_id='{user}' and state='completed';"), '1')

    def test_failed_message_commit_keeps_answer_for_retry_and_rolls_back_quota(self):
        user, conversation, request = self.new_turn()
        self.turn('claim', user, conversation, request)
        self.turn('save', user, conversation, request, result=self.answer_receipt())
        # A temporary failure after the assistant insert must roll back the whole completion.
        self.sql(f"create function reject_turn_completion() returns trigger language plpgsql as $$ begin "
                 f"if new.request_id = '{request}' and new.state='completed' then raise exception 'receipt unavailable'; end if; return new; end $$; "
                 "create trigger reject_completion before update on chat_turns for each row execute function reject_turn_completion();")
        try:
            with self.assertRaisesRegex(AssertionError, 'receipt unavailable'):
                self.turn('complete', user, conversation, request)
            claim = self.turn('claim', user, conversation, request)
            self.assertEqual(claim['state'], 'generated')
            self.assertEqual(claim['result'], self.answer_receipt())
            self.assertEqual(self.sql(f"select count(*) from messages where conversation_id='{conversation}';"), '1')
            self.assertEqual(self.operation('get', user, 'question', claim['operation_id'])['state'], 'running')
        finally:
            self.sql('drop trigger reject_completion on chat_turns; drop function reject_turn_completion();')
        self.assertEqual(self.turn('complete', user, conversation, request)['state'], 'completed')

    def test_turn_keys_are_bound_to_owner_conversation_and_question(self):
        user, conversation, request = self.new_turn()
        self.turn('claim', user, conversation, request)
        self.assertEqual(self.turn('claim', user, conversation, request, question='Different?')['error'], 'conflict')
        self.assertEqual(self.turn('claim', str(uuid4()), conversation, request)['error'], 'not_found')
        other = str(uuid4())
        self.sql(f"insert into conversations values ('{other}','{user}',gen_random_uuid());")
        self.assertEqual(self.turn('claim', user, other, request)['error'], 'conflict')
        for role in ('anon', 'authenticated'):
            with self.assertRaisesRegex(AssertionError, 'permission denied'):
                self.sql(f"set role {role}; select chat_turn('claim','{user}','{conversation}','{request}','Refund window?');")
            with self.assertRaisesRegex(AssertionError, 'permission denied'):
                self.sql(f"set role {role}; select * from chat_turns;")
        self.sql(f"delete from messages where conversation_id='{conversation}'; delete from conversations where id='{conversation}';")
        self.assertEqual(self.sql(f"select count(*) from chat_turns where request_id='{request}';"), '0')
        self.assertEqual(self.turn('claim', user, conversation, request)['error'], 'not_found')
