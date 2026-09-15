import assert from "node:assert/strict";
import test from "node:test";

import { forwardToBackend } from "./backend-proxy";

test("returns an authentication response without contacting the backend", async () => {
  let fetchCalled = false;
  let bodyPrepared = false;

  const response = await forwardToBackend(
    {
      path: "/documents",
      method: "POST",
      prepareBody: () => {
        bodyPrepared = true;
        return "should not be prepared";
      }
    },
    {
      getSession: async () => null,
      fetch: async () => {
        fetchCalled = true;
        return new Response();
      }
    }
  );

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { detail: "Authentication required." });
  assert.equal(fetchCalled, false);
  assert.equal(bodyPrepared, false);
});

test("adds signed identity and forwards the request and backend response", async () => {
  let receivedInput: RequestInfo | URL | undefined;
  let receivedInit: RequestInit | undefined;

  const response = await forwardToBackend(
    {
      path: "/chat",
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: "doc-a" }),
      cache: "no-store"
    },
    {
      getSession: async () => ({ user: { id: "user-a" } }),
      createAuthHeaders: (userId) => ({
        "x-test-user": userId,
        "x-test-signature": "signed"
      }),
      fetch: async (input, init) => {
        receivedInput = input;
        receivedInit = init;
        return new Response('{"answer":"ok"}', {
          status: 207,
          headers: { "content-type": "application/json" }
        });
      }
    }
  );

  assert.equal(receivedInput, "http://localhost:8000/chat");
  assert.equal(receivedInit?.method, "POST");
  assert.equal(receivedInit?.body, JSON.stringify({ document_id: "doc-a" }));
  assert.equal(receivedInit?.cache, "no-store");

  const headers = new Headers(receivedInit?.headers);
  assert.equal(headers.get("content-type"), "application/json");
  assert.equal(headers.get("x-test-user"), "user-a");
  assert.equal(headers.get("x-test-signature"), "signed");

  assert.equal(response.status, 207);
  assert.equal(response.headers.get("content-type"), "application/json");
  assert.equal(await response.text(), '{"answer":"ok"}');
});

test("uses a JSON content type when the backend does not provide one", async () => {
  const response = await forwardToBackend(
    { path: "/documents", method: "GET" },
    {
      getSession: async () => ({ user: { id: "user-a" } }),
      createAuthHeaders: () => ({}),
      fetch: async () => new Response(null, { status: 200 })
    }
  );

  assert.equal(response.headers.get("content-type"), "application/json");
  assert.equal(await response.text(), "");
});
