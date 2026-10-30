// Unwritten Craft — hub store check. Zero dependencies:
//   node app/cloud-signer/hub-check.mjs
// Drives the real worker.js against a real SQLite database (node:sqlite)
// seeded with migrations/0001_sessions.sql, through the real HTTP
// routes. Fails non-zero on the first mismatch.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const dir = dirname(fileURLToPath(import.meta.url));
const { default: worker } = await import("./worker.js");

const db = new DatabaseSync(":memory:");
db.exec(readFileSync(join(dir, "migrations", "0001_sessions.sql"), "utf8"));

// D1-compatible stub over the real database: prepare/bind/first/all/run
// (bind is optional on real D1 when the query takes no parameters).
function d1() {
  return {
    prepare(sql) {
      const stmt = db.prepare(sql);
      const bound = (...params) => ({
        first: () => stmt.get(...params) ?? null,
        all: () => ({ results: stmt.all(...params) }),
        run: () => (stmt.run(...params), { success: true }),
      });
      return Object.assign(bound(), { bind: (...params) => bound(...params) });
    },
  };
}

const URL = "https://signer.test";
const TOKEN = "t1";
const authed = { SIGNER_TOKENS: TOKEN, CLOUD_LIBRARY_ID: "L", CLOUD_API_KEY: "K", DB: d1() };
const noDb = { SIGNER_TOKENS: TOKEN, CLOUD_LIBRARY_ID: "L", CLOUD_API_KEY: "K" };
const open = { CLOUD_LIBRARY_ID: "L", CLOUD_API_KEY: "K", DB: d1() };

let n = 0;
function check(cond, label) {
  n++;
  if (!cond) {
    console.error(`FAIL: ${label}`);
    process.exit(1);
  }
  console.log(`ok - ${label}`);
}
async function call(env, method, path, body, token) {
  const headers = {};
  if (token) headers["X-Signer-Token"] = token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const req = new Request(URL + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const resp = await worker.fetch(req, env);
  let data = null;
  try { data = await resp.json(); } catch { /* empty */ }
  return { status: resp.status, data };
}

const VID = "vid-123";

// Unauthorized when the pool is set.
{
  const r = await call(authed, "GET", "/hub/sessions", undefined, "nope");
  check(r.status === 401, "hub rejects a bad token");
}
// 503 without the D1 binding; uploads keep working.
{
  const r = await call(noDb, "GET", "/hub/sessions", undefined, TOKEN);
  check(r.status === 503, "hub answers 503 with no store");
}
// videoId required.
{
  const r = await call(authed, "POST", "/hub/publish", { title: "x" }, TOKEN);
  check(r.status === 400, "publish requires videoId");
}
// Publish, then read back list + full record.
{
  const payload = {
    videoId: VID, libraryId: "L", title: "Bread", lessonDate: "Oct 29, 2026",
    hlsUrl: "https://cdn/x/playlist.m3u8", mp4Url: "https://cdn/x/play_720p.mp4",
    writeupMd: "# Bread\n\nBody.\n",
    corrections: [{ start: "0:42", quote: "q", correcting: "c", segment: "s" }],
    chapters: [{ start: "0:00", label: "Intro" }],
    glossary: { Bread: "staple" },
  };
  const r = await call(authed, "POST", "/hub/publish", payload, TOKEN);
  check(r.status === 200 && r.data.published === VID, "publish upserts");
  const list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(list.status === 200 && list.data.length === 1 && list.data[0].title === "Bread",
    "list shows the published session");
  const get = await call(authed, "GET", `/hub/sessions/${VID}`, undefined, TOKEN);
  check(get.status === 200 && get.data.writeupMd.includes("# Bread"), "get returns the writeup");
  check(get.data.corrections.length === 1 && get.data.corrections[0].quote === "q", "get parses corrections");
  check(get.data.chapters[0].label === "Intro", "get parses chapters");
  check(get.data.glossary.Bread === "staple", "get parses glossary");
  check(get.data.hlsUrl.includes("playlist.m3u8") && get.data.mp4Url.includes("play_720p"), "get returns playback urls");
}
// Republish updates in place, no duplicate row.
{
  const r = await call(authed, "POST", "/hub/publish", { videoId: VID, title: "Bread v2" }, TOKEN);
  const get = await call(authed, "GET", `/hub/sessions/${VID}`, undefined, TOKEN);
  const list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(r.data.published === VID && get.data.title === "Bread v2" && list.data.length === 1,
    "republish upserts instead of duplicating");
}
// Delete removes the record.
{
  const del = await call(authed, "DELETE", `/hub/sessions/${VID}`, undefined, TOKEN);
  const get = await call(authed, "GET", `/hub/sessions/${VID}`, undefined, TOKEN);
  check(del.data.deleted === true && get.status === 404, "delete removes the record");
}
// Unknown hub method is rejected, not routed to the signer.
{
  const r = await call(authed, "PUT", `/hub/sessions/${VID}`, {}, TOKEN);
  check(r.status === 405, "unknown hub method rejected");
}
console.log(`ALL HUB CHECKS PASSED (${n})`);
