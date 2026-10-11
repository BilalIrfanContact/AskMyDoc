"""Exercise the chunk store's and spend ledger's production SQL with a disposable local PostgreSQL server and
pgvector, never Supabase."""
import glob
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4


MIGRATIONS = [
    Path(__file__).resolve().parents[2] / "supabase/migrations" / name
    for name in ("202610110001_document_chunks.sql", "202610110002_ai_usage.sql", "202610110003_usage_ids_and_atomic_import.sql")
]


class SupabaseFunctionsDatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binaries = sorted(glob.glob("/usr/lib/postgresql/*/bin/pg_ctl"))
        if not binaries or os.getuid() == 0:
            cls.unavailable("Local PostgreSQL binaries and a non-root user are required")
        cls.bin = Path(binaries[-1]).parent
        cls.temp = tempfile.TemporaryDirectory(prefix="askmydoc-functions-")
        cls.data = Path(cls.temp.name) / "data"
        subprocess.run([str(cls.bin / "initdb"), "-D", str(cls.data), "-A", "trust", "--no-locale", "-E", "UTF8"], check=True, capture_output=True)
        subprocess.run([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-l", str(Path(cls.temp.name) / "server.log"),
            "-o", f"-k {cls.temp.name} -h '' -p 55484", "-w", "start"], check=True, capture_output=True)
        cls.addClassCleanup(cls.stop_database)
        if not cls.sql("select count(*) from pg_available_extensions where name = 'vector'") == "1":
            cls.unavailable("pgvector is required for the chunk store tests")
        # Like Supabase: the service role bypasses row-level security, and every API role can use `extensions`.
        cls.sql("create role anon; create role authenticated; create role service_role bypassrls; "
            "create schema extensions; grant usage on schema extensions to anon, authenticated, service_role;")
        for migration in MIGRATIONS:
            cls.sql(migration.read_text())

    @classmethod
    def unavailable(cls, reason):
        if os.getenv("ASKMYDOC_REQUIRE_POSTGRES") == "1":
            raise RuntimeError(reason)
        raise unittest.SkipTest(reason)

    @classmethod
    def stop_database(cls):
        subprocess.run([str(cls.bin / "pg_ctl"), "-D", str(cls.data), "-m", "immediate", "stop"], capture_output=True)
        cls.temp.cleanup()

    @classmethod
    def sql(cls, query):
        result = subprocess.run([str(cls.bin / "psql"), "-h", cls.temp.name, "-p", "55484", "-d", "postgres",
            "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", query], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def insert_chunks(self, document_id, generation, vectors):
        values = ",".join(
            f"('{document_id}','{generation}',{index},'{document_id}:chunk:{index}','text {index}','{vector}')"
            for index, vector in enumerate(vectors)
        )
        self.sql("set role service_role; insert into public.document_chunks "
            f"(document_id, generation, chunk_index, chunk_id, content, embedding) values {values};")

    def commit(self, document_id, generation, expected):
        return self.sql("set role service_role; select public.commit_document_index("
            f"'{document_id}','{generation}','voyage-4-lite','plain',{expected});")

    def test_commit_switches_generations_and_refuses_an_incomplete_one(self):
        document_id, old, new = str(uuid4()), uuid4(), uuid4()
        self.insert_chunks(document_id, old, ["[1,0]"])
        self.assertEqual(self.commit(document_id, old, 1), "1")
        self.insert_chunks(document_id, new, ["[0,1]", "[1,1]"])

        with self.assertRaisesRegex(AssertionError, "stored 2 of 3 chunks"):
            self.commit(document_id, new, 3)
        self.assertEqual(self.sql(f"select generation from document_indexes where document_id = '{document_id}'"), str(old))

        self.assertEqual(self.commit(document_id, new, 2), "2")
        self.assertEqual(
            self.sql(f"select generation, chunk_count from document_indexes where document_id = '{document_id}'"), f"{new}|2"
        )
        self.assertEqual(self.sql(f"select count(*) from document_chunks where document_id = '{document_id}' and generation = '{old}'"), "0")

    def test_match_returns_one_generations_nearest_chunks_first(self):
        document_id, current, other = str(uuid4()), uuid4(), uuid4()
        self.insert_chunks(document_id, current, ["[1,0]", "[0,1]", "[0.7,0.7]"])
        self.insert_chunks(document_id, other, ["[0,1]"])

        found = self.sql("set role service_role; select string_agg(chunk_id, ',') from public.match_document_chunks("
            f"'{document_id}','{current}','[0,1]',2);")

        self.assertEqual(found, f"{document_id}:chunk:1,{document_id}:chunk:2")

    def test_browser_roles_cannot_read_chunks(self):
        with self.assertRaisesRegex(AssertionError, "permission denied"):
            self.sql("set role anon; select count(*) from public.document_chunks;")

    def test_usage_totals_split_tokens_at_the_month_start_and_sum_only_that_months_cost(self):
        self.sql("set role service_role; insert into public.ai_usage (created_at, provider, model, task, input_tokens, output_tokens, cost_usd) values "
            "('2026-09-30 18:59:59+00','voyage','voyage-4-lite','embed',100,0,0.002),"
            "('2026-09-30 19:00:00+00','voyage','voyage-4-lite','embed',40,0,0.0008),"
            "('2026-10-05 00:00:00+00','groq','openai/gpt-oss-120b','answer',1000,200,0.27),"
            "('2026-11-01 00:00:00+00','groq','openai/gpt-oss-120b','answer',5,5,0.01);")

        totals = self.sql("set role service_role; select string_agg(concat_ws('|', provider, tokens_before, tokens_in_month, cost_in_month), ',' order by provider) "
            "from public.ai_usage_totals('2026-10-01 00:00:00+05', '2026-11-01 00:00:00+05');")

        # October in Pakistan time starts at 2026-09-30 19:00 UTC; the November row falls after the month.
        self.assertEqual(totals, "groq|0|1200|0.27,voyage|100|40|0.0008")

    def test_recording_the_same_usage_id_twice_keeps_one_row(self):
        usage_id = uuid4()
        self.addCleanup(self.sql, f"delete from public.ai_usage where usage_id = '{usage_id}'")
        insert = ("set role service_role; insert into public.ai_usage (usage_id, provider, model, task, input_tokens, cost_usd) "
            f"values ('{usage_id}','groq','openai/gpt-oss-20b','retry-test',1,0.1) on conflict (usage_id) do nothing;")
        self.sql(insert)
        self.sql(insert)

        self.assertEqual(self.sql(f"select count(*) from ai_usage where usage_id = '{usage_id}'"), "1")

    def test_history_import_is_all_or_nothing(self):
        self.sql("create schema scratch; create table scratch.ai_usage (like public.ai_usage including all);")
        # Run the import against an empty copy of the ledger so the other usage tests' rows don't matter.
        function = Path(MIGRATIONS[2]).read_text().split("create function", 1)[1].split("$$;", 1)[0]
        self.sql("create function" + function.replace("public.ai_usage", "scratch.ai_usage").replace("public.import_ai_usage", "scratch.import_ai_usage") + "$$;")
        good = '{"created_at":"2026-10-01T00:00:00+00:00","provider":"groq","model":"m","task":"t","input_tokens":1,"output_tokens":0,"cost_usd":0.1}'

        with self.assertRaises(AssertionError):
            self.sql(f"""select scratch.import_ai_usage('[{good}, {{"provider":"groq"}}]');""")
        self.assertEqual(self.sql("select count(*) from scratch.ai_usage"), "0")

        self.assertEqual(self.sql(f"select scratch.import_ai_usage('[{good}, {good}]');"), "2")
        with self.assertRaisesRegex(AssertionError, "already has rows"):
            self.sql(f"select scratch.import_ai_usage('[{good}]');")
        self.assertEqual(self.sql("select count(*) from scratch.ai_usage"), "2")

    def test_browser_roles_cannot_read_usage(self):
        with self.assertRaisesRegex(AssertionError, "permission denied"):
            self.sql("set role authenticated; select count(*) from public.ai_usage;")


if __name__ == "__main__":
    unittest.main()
