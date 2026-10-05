# Portfolio demo limits

Apply `migrations/202610050001_demo_limits.sql` in the Supabase SQL editor **before deploying either application**. The migration is transactional and requires the existing `public.documents` table. It creates the server-only rate functions, durable allowance receipts, and a private `askmydoc-uploads` bucket capped at 15,000,000 bytes. Existing documents count toward the upload allowance. Do not run this migration twice.

The Supabase project's global Storage file-size limit must be at least 15 MB. Keep the service-role key on the servers. No browser database privileges or public bucket permissions are needed. The restrictive Storage policy keeps this bucket private even if older permissive policies cover other buckets.

The browser first requests upload permission from Next.js. It sends file bytes directly to the signed Storage URL, then asks Next.js to tell FastAPI to process the server-selected object. FastAPI checks actual bytes, ownership, and processing state. Finishing an already completed upload returns its original receipt.

## Allowances

- 20 successfully persisted questions per account across all documents, including insufficient-context answers. Exceptions refund the reservation.
- 3 successfully processed documents per account. Deleting a document does not refund an upload.
- 5 question attempts per minute per account, 5 password-login attempts per minute per IP, and 3 signup attempts per hour per IP. Failed attempts still count toward these short cooldowns.
- 2,000 characters per question. Files may contain up to 15,000,000 bytes, including exactly that size. Larger files show "Please select a smaller file."
- One suggestion-generation attempt per document, with the result reused. Suggestions are optional; a failed attempt stores an empty result rather than allowing refreshes to repeat paid work.

Signed upload URLs last two hours. Unfinished uploads and failed signed uploads reserve a slot for two hours plus five minutes, so valid upload permissions cannot accumulate outside the allowance. The UI reports that slots are reserved rather than claiming successful uploads used them. Failed legacy uploads, which do not issue signed permissions, refund immediately.

Vercel's overwritten `x-forwarded-for` header supplies the authentication IP key when `VERCEL=1`. IP addresses are HMAC-hashed before persistence. Other frontend hosts use one shared fallback key until their trusted proxy is explicitly supported. Do not set `VERCEL=1` on a host that accepts client-controlled forwarding headers. The upload completion route requests a 300-second function duration; enable Vercel Fluid compute or verify the chosen plan supports that duration. A lost HTTP response can leave a successfully uploaded document visible in the library.

## Maintenance and recovery

Expired unfinished files need periodic cleanup. Schedule this on the backend, for example hourly:

```bash
python -m backend.scripts.cleanup_demo_uploads --apply
```

Omit `--apply` for a read-only count. Each run handles at most 100 expired unfinished uploads or orphaned files for subsequently deleted documents. It never removes an existing completed document or running work. Cleanup of a deleted document also handles a file recreated using its still-valid upload permission; that permission cannot overwrite an existing file and expires after two hours. Run additional batches if needed. Storage deletion happens through the Storage API, never by deleting `storage.objects` rows.

Reservations intentionally fail closed during database outages. A process crash or a failed receipt write can leave an operation in `running`; this prevents another request from exceeding the allowance or repeating paid processing. Inspect these receipts alongside persisted documents/messages before manually marking them completed or failed. Do not automatically expire running work while a server may still be processing it.

Old expired rate-window rows and demo receipts have no automatic retention job. They are small, but need a retention policy if this moves beyond a portfolio demo. Keep completed upload receipts while the account exists so deleting documents cannot reset its allowance. Per-IP signup limits do not prevent someone with multiple IP addresses from creating multiple accounts; the application's existing global AI budget remains a separate safeguard.

## Verification

```bash
python -m unittest discover -s backend/tests -p 'test_*.py'
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

The database tests start a disposable local PostgreSQL instance and apply the production migration against isolated fixture tables. They do not call Supabase. PostgreSQL binaries must be installed and the tests must run as a non-root user. Set `ASKMYDOC_REQUIRE_POSTGRES=1` to fail rather than skip when they are unavailable; CI does this.

After applying the migration, perform one deployment smoke test with a disposable account: upload an 8–10 MB PDF, ask a question, refresh the document, and check that its suggestions are reused. Try a file larger than 15 MB and confirm the smaller-file message appears. Automated tests cover the limits and concurrency, but do not verify the live Supabase/Vercel/Railway configuration.
