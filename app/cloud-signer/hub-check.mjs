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
db.exec(readFileSync(join(dir, "migrations", "0002_fetch_jobs.sql"), "utf8"));

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
// Pipeline proxy needs the token like every other route: an open
// proxy would leak the library listing to anyone.
{
  const r = await call(authed, "GET", "/pipeline/videos?page=1", undefined, "nope");
  check(r.status === 401, "pipeline proxy rejects a bad token");
  const r2 = await call(authed, "GET", "/pipeline/videos?page=1");
  check(r2.status === 401, "pipeline proxy rejects a missing token");
}
// A signer URL pasted with a trailing slash (or a doubled one)
// must route the same as the clean URL.
{
  const r = await call(authed, "GET", "/hub/sessions/", undefined, TOKEN);
  check(r.status === 200 && Array.isArray(r.data), "hub list tolerates a trailing slash");
  await call(authed, "POST", "/hub/publish", { videoId: "slash1", title: "Slash" }, TOKEN);
  const r2 = await call(authed, "GET", "//hub/sessions/slash1/", undefined, TOKEN);
  check(r2.status === 200 && r2.data.videoId === "slash1", "hub detail tolerates doubled slashes");
}
// A corrupt JSON column (hand-edited D1, old writer) must not 500
// the whole hub: the row serves with empty lists instead.
{
  authed.DB.prepare(
    `INSERT INTO sessions (video_id, title, corrections_json, chapters_json, glossary_json, published_at)
     VALUES ('corrupt1', 'Corrupt', 'nope{', 'nope{', 'nope{', 1)`
  ).run();
  const r = await call(authed, "GET", "/hub/sessions/corrupt1", undefined, TOKEN);
  check(r.status === 200 && Array.isArray(r.data.corrections) && r.data.corrections.length === 0
    && Array.isArray(r.data.chapters) && JSON.stringify(r.data.glossary) === "{}",
    "hub detail survives a corrupt row");
  const l = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  const row = l.data.find((s) => s.videoId === "corrupt1");
  check(l.status === 200 && row && row.title === "Corrupt", "hub list survives a corrupt row");
}
// Authenticated proxy passes the vendor listing through untouched,
// with the caller's page and the CORS headers.
{
  const realFetch = globalThis.fetch;
  let seenUrl = "", seenKey = "";
  globalThis.fetch = async (url, opts) => {
    seenUrl = String(url);
    seenKey = (opts && opts.headers && opts.headers.AccessKey) || "";
    return new Response(JSON.stringify({ items: [{ guid: "g1" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const req = new Request(URL + "/pipeline/videos?page=2", {
      method: "GET",
      headers: { "X-Signer-Token": TOKEN },
    });
    const resp = await worker.fetch(req, authed);
    const data = await resp.json();
    check(resp.status === 200 && data.items.length === 1 && data.items[0].guid === "g1",
      "pipeline proxy passes the listing through");
    check(seenUrl.includes("/library/L/videos") && seenUrl.includes("page=2"),
      "pipeline proxy forwards the page");
    check(seenKey === "K", "pipeline proxy authenticates to the vendor");
    check(resp.headers.get("Access-Control-Allow-Origin") !== null,
      "pipeline proxy answers with CORS headers");
  } finally {
    globalThis.fetch = realFetch;
  }
}
// Fetch queue: same token gate as every other route.
{
  const r = await call(authed, "POST", "/fetch/jobs", { url: "https://x/y.mp4" }, "nope");
  check(r.status === 401, "fetch submit rejects a bad token");
  const r2 = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe");
  check(r2.status === 401, "fetch claim rejects a missing token");
}
// 503 without the D1 binding.
{
  const r = await call(noDb, "POST", "/fetch/jobs", { url: "https://x/y.mp4" }, TOKEN);
  check(r.status === 503, "fetch answers 503 with no store");
}
// URL required, and it must be an http(s) URL.
{
  const r = await call(authed, "POST", "/fetch/jobs", {}, TOKEN);
  check(r.status === 400, "fetch submit requires a url");
  const r2 = await call(authed, "POST", "/fetch/jobs", { url: "notaurl" }, TOKEN);
  const r3 = await call(authed, "POST", "/fetch/jobs", { url: "ftp://x/y.mp4" }, TOKEN);
  check(r2.status === 400 && r3.status === 400, "fetch submit rejects non-http urls");
}
// Submit, then claim exactly once; a second claim finds nothing.
{
  const s = await call(authed, "POST", "/fetch/jobs",
    { url: "https://www.youtube.com/watch?v=abc123" }, TOKEN);
  check(s.status === 200 && s.data.status === "pending" && typeof s.data.id === "string",
    "fetch submit queues a job");
  const again = await call(authed, "POST", "/fetch/jobs",
    { url: "https://www.youtube.com/watch?v=abc123" }, TOKEN);
  check(again.data.id === s.data.id, "resubmitting a queued url returns the same job");
  const nob = await call(authed, "GET", "/fetch/jobs?claim=1", undefined, TOKEN);
  check(nob.status === 400, "fetch claim requires a worker name");
  const c = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  check(c.status === 200 && c.data.job && c.data.job.id === s.data.id, "fetch claim hands out the job");
  const c2 = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  check(c2.status === 200 && c2.data.job === null, "a claimed job is not handed out twice");
  const d = await call(authed, "POST", `/fetch/jobs/${s.data.id}/done`, { session: "w/1" }, TOKEN);
  check(d.status === 200 && d.data.ok === true, "fetch done closes the job");
  const list = await call(authed, "GET", "/fetch/jobs", undefined, TOKEN);
  const row = list.data.find((j) => j.id === s.data.id);
  check(list.status === 200 && row && row.status === "done" && row.session === "w/1",
    "fetch list shows the finished job");
}
// Failed jobs stay failed until explicitly reclaimed, like --retry-failed.
{
  const s = await call(authed, "POST", "/fetch/jobs", { url: "https://x/broken.mp4" }, TOKEN);
  await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  const f = await call(authed, "POST", `/fetch/jobs/${s.data.id}/failed`, { error: "boom" }, TOKEN);
  check(f.status === 200 && f.data.ok === true, "fetch failed records the error");
  const c = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  check(c.status === 200 && c.data.job === null, "a failed job is not reclaimed by default");
  const r = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1&includeFailed=1", undefined, TOKEN);
  check(r.status === 200 && r.data.job && r.data.job.id === s.data.id, "includeFailed reclaims it");
  const unk = await call(authed, "POST", "/fetch/jobs/nope/done", {}, TOKEN);
  check(unk.status === 404, "fetch done on an unknown job 404s");
}
// Trailing slashes route the same.
{
  const r = await call(authed, "GET", "/fetch/jobs/", undefined, TOKEN);
  check(r.status === 200 && Array.isArray(r.data), "fetch list tolerates a trailing slash");
}
// A claim older than two hours is a crashed worker: the job comes
// back instead of sticking in claimed forever.
{
  const s = await call(authed, "POST", "/fetch/jobs", { url: "https://x/stuck.mp4" }, TOKEN);
  await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  authed.DB.prepare(`UPDATE fetch_jobs SET updated_at = ? WHERE id = ?`)
    .bind(Math.floor(Date.now() / 1000) - 7201, s.data.id).run();
  const r = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe2", undefined, TOKEN);
  check(r.status === 200 && r.data.job && r.data.job.id === s.data.id,
    "an abandoned claim is handed out again");
}
console.log(`ALL HUB CHECKS PASSED (${n})`);
