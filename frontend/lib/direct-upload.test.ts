import assert from "node:assert/strict";
import { File } from "node:buffer";
import test from "node:test";
import { uploadPdf } from "./api";
import { getUploadValidationError, MAX_UPLOAD_BYTES, SMALLER_FILE_MESSAGE } from "./uploadValidation";

const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

test("size boundaries allow 10 MB and exactly 15 MB, and reject larger files", () => {
  for (const size of [10_000_000, MAX_UPLOAD_BYTES]) {
    assert.equal(getUploadValidationError({ name: "report.pdf", type: "application/pdf", size }), null);
  }
  assert.equal(getUploadValidationError({ name: "report.pdf", type: "application/pdf", size: MAX_UPLOAD_BYTES + 1 }), SMALLER_FILE_MESSAGE);
});

test("an oversized file never starts a network request", async (context) => {
  const fetch = context.mock.method(globalThis, "fetch");
  const file = new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], "report.pdf", { type: "application/pdf" });
  await assert.rejects(uploadPdf(file as unknown as globalThis.File), /Please select a smaller file/);
  assert.equal(fetch.mock.calls.length, 0);
});

test("file bytes go directly to storage; Next.js receives only authorization and completion", async (context) => {
  const file = new File([new Uint8Array(10_000_000)], "report.pdf", { type: "application/pdf" });
  const calls: { url: string; init?: RequestInit }[] = [];
  context.mock.method(globalThis, "fetch", async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (calls.length === 1) return response({ upload_id: "upload-id", signed_url: "https://storage.test/signed", content_type: "application/pdf" });
    if (calls.length === 2) return response({});
    return response({ document_id: "upload-id", status: "success", lifecycle_status: "ready", chunk_count: 1, stored_count: 1 });
  });
  const result = await uploadPdf(file as unknown as globalThis.File);
  assert.equal(result.document_id, "upload-id");
  assert.equal(calls[0].url, "/api/upload");
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { filename: "report.pdf", size: 10_000_000 });
  assert.equal(calls[1].url, "https://storage.test/signed");
  assert.equal(calls[1].init?.method, "PUT");
  assert.equal(calls[1].init?.body, file);
  assert.equal(calls[2].url, "/api/upload/upload-id/complete");
  assert.equal(calls[2].init?.body, undefined);
});

test("account allowance rejection never uploads file bytes", async (context) => {
  const fetch = context.mock.method(globalThis, "fetch", async () => response({ detail: "You have reached the demo allowance of 3 documents per account." }, 429));
  await assert.rejects(uploadPdf(new File(["PDF"], "a.pdf") as unknown as globalThis.File), /3 documents/);
  assert.equal(fetch.mock.calls.length, 1);
});

test("storage rejection stops processing and displays a friendly size error", async (context) => {
  let calls = 0;
  context.mock.method(globalThis, "fetch", async () => ++calls === 1
    ? response({ upload_id: "upload-id", signed_url: "https://storage.test/signed", content_type: "application/pdf" })
    : response({}, 413));
  await assert.rejects(uploadPdf(new File(["PDF"], "a.pdf") as unknown as globalThis.File), /Please select a smaller file/);
  assert.equal(calls, 2);
});
