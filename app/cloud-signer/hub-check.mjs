// Unwritten Craft — hub store check. Zero dependencies:
//   node app/cloud-signer/hub-check.mjs
// Drives the real worker.js against a real SQLite database (node:sqlite)
// seeded with every migration (0001_sessions.sql through
// 0005_parts.sql), through the real HTTP routes. Fails non-zero on
// the first mismatch.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const dir = dirname(fileURLToPath(import.meta.url));
const { default: worker } = await import("./worker.js");

const db = new DatabaseSync(":memory:");
db.exec(readFileSync(join(dir, "migrations", "0001_sessions.sql"), "utf8"));
db.exec(readFileSync(join(dir, "migrations", "0002_fetch_jobs.sql"), "utf8"));
db.exec(readFileSync(join(dir, "migrations", "0003_ignored.sql"), "utf8"));
db.exec(readFileSync(join(dir, "migrations", "0004_duration.sql"), "utf8"));
db.exec(readFileSync(join(dir, "migrations", "0005_parts.sql"), "utf8"));

// D1-compatible stub over the real database: prepare/bind/first/all/run
// (bind is optional on real D1 when the query takes no parameters).
function d1(database = db) {
  return {
    prepare(sql) {
      const stmt = database.prepare(sql);
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
// Only / mints videos and proxies status/delete: any other path must
// 404 instead of falling into the create/status/delete trio.
{
  const p = await call(authed, "POST", "/hub/sessions", { title: "x" }, TOKEN);
  check(p.status === 404, "unknown POST path 404s instead of minting a video");
  const g = await call(authed, "GET", "/nope?videoId=x", undefined, TOKEN);
  check(g.status === 404, "unknown GET path 404s instead of proxying status");
  const d = await call(authed, "DELETE", "/nope?videoId=x", undefined, TOKEN);
  check(d.status === 404, "unknown DELETE path 404s instead of deleting");
}
// A malformed id answers 400, never an uncaught 500.
{
  const f = await call(authed, "POST", "/fetch/jobs/%/done", {}, TOKEN);
  check(f.status === 400, "malformed fetch job id is a 400");
  const h = await call(authed, "GET", "/hub/sessions/%", undefined, TOKEN);
  check(h.status === 400, "malformed hub video id is a 400");
}
// No token pool configured fails LOUD, never open: unset
// SIGNER_TOKENS must not silently serve the library to the world.
{
  const r = await call(open, "GET", "/hub/sessions", undefined, TOKEN);
  check(r.status === 500, "empty token pool fails closed");
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
// CORS allowlist: a listed origin is reflected, anything else gets the
// canonical first entry (never the requester's), "*" still opens up.
{
  const listed = { ...authed, CORS_ORIGIN: "https://app.example, http://localhost:8765" };
  const ask = (origin) => new Request(URL + "/hub/sessions",
    { headers: { "X-Signer-Token": TOKEN, ...(origin ? { Origin: origin } : {}) } });
  const echo = await worker.fetch(ask("http://localhost:8765"), listed);
  check(echo.headers.get("Access-Control-Allow-Origin") === "http://localhost:8765",
    "cors reflects a listed origin");
  const evil = await worker.fetch(ask("https://evil.example"), listed);
  const fell = evil.headers.get("Access-Control-Allow-Origin");
  check(fell === "https://app.example" && fell !== "https://evil.example",
    "cors answers an unlisted origin with the canonical entry");
  const star = await worker.fetch(ask("https://evil.example"),
    { ...authed, CORS_ORIGIN: "*" });
  check(star.headers.get("Access-Control-Allow-Origin") === "*",
    "cors keeps the first-test wildcard");
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
// Ignored videos: the operator's set-asides live here; the hub never
// shows them, and the recorders badge them on the Record screen.
{
  const req = await call(authed, "POST", "/hub/ignored", { title: "x" }, TOKEN);
  check(req.status === 400, "ignore requires videoId");
  const p = await call(authed, "POST", "/hub/ignored",
    { videoId: "junk-1", title: "Test clip", reason: "not a lesson" }, TOKEN);
  check(p.status === 200 && p.data.ignored === "junk-1", "ignore upserts");
  const l = await call(authed, "GET", "/hub/ignored", undefined, TOKEN);
  check(l.status === 200 && l.data.length === 1 && l.data[0].title === "Test clip" &&
    l.data[0].reason === "not a lesson", "ignored list carries title and reason");
  const p2 = await call(authed, "POST", "/hub/ignored",
    { videoId: "junk-1", title: "Test clip", reason: "changed mind" }, TOKEN);
  const l2 = await call(authed, "GET", "/hub/ignored", undefined, TOKEN);
  check(p2.status === 200 && l2.data.length === 1 && l2.data[0].reason === "changed mind",
    "re-ignore updates the marker");
}
// A published session that gets ignored vanishes from the hub (list
// and detail); un-ignoring brings it back.
{
  await call(authed, "POST", "/hub/publish",
    { videoId: "soon-junk", title: "Oops", writeupMd: "# Oops" }, TOKEN);
  const before = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(before.data.some((s) => s.videoId === "soon-junk"), "session listed before ignore");
  await call(authed, "POST", "/hub/ignored", { videoId: "soon-junk", reason: "oops" }, TOKEN);
  const after = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(!after.data.some((s) => s.videoId === "soon-junk"), "ignored session leaves the list");
  const det = await call(authed, "GET", "/hub/sessions/soon-junk", undefined, TOKEN);
  check(det.status === 404, "ignored session detail 404s");
  const del = await call(authed, "DELETE", "/hub/ignored/soon-junk", undefined, TOKEN);
  check(del.status === 200 && del.data.deleted === true, "un-ignore deletes the marker");
  const back = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(back.data.some((s) => s.videoId === "soon-junk"), "un-ignored session returns");
  await call(authed, "DELETE", "/hub/sessions/soon-junk", undefined, TOKEN);
}
// Ignored routes share the hub's guards.
{
  const r = await call(noDb, "GET", "/hub/ignored", undefined, TOKEN);
  check(r.status === 503, "ignored answers 503 with no store");
  const m = await call(authed, "PUT", "/hub/ignored/junk-1", {}, TOKEN);
  check(m.status === 405, "unknown ignored method rejected");
  const b = await call(authed, "DELETE", "/hub/ignored/%", undefined, TOKEN);
  check(b.status === 400, "malformed ignored video id is a 400");
  const t = await call(authed, "GET", "/hub/ignored/", undefined, TOKEN);
  check(t.status === 200 && Array.isArray(t.data), "ignored list tolerates a trailing slash");
  await call(authed, "DELETE", "/hub/ignored/junk-1", undefined, TOKEN);
}
// A database missing a migration (deployed worker, store migrated
// only up to 0001) answers a JSON 503 naming the migration to apply,
// never an uncaught exception or a bare "no such table" 500.
{
  const old = new DatabaseSync(":memory:");
  old.exec(readFileSync(join(dir, "migrations", "0001_sessions.sql"), "utf8"));
  const env = { ...authed, DB: d1(old) };
  const s = await call(env, "GET", "/hub/sessions", undefined, TOKEN);
  check(s.status === 503 && /0003_ignored\.sql/.test(s.data.error) && /--remote/.test(s.data.error),
    "hub list names the missing migration");
  const i = await call(env, "GET", "/hub/ignored", undefined, TOKEN);
  check(i.status === 503 && /0003_ignored\.sql/.test(i.data.error), "ignored list names the missing migration");
  const f = await call(env, "GET", "/fetch/jobs", undefined, TOKEN);
  check(f.status === 503 && /0002_fetch_jobs\.sql/.test(f.data.error), "fetch list names the missing migration");
}
// Without the vendor key the listing proxy fails loud naming the
// secret, instead of forwarding an empty AccessKey whose 401 reads
// like a bad signer token.
{
  const realFetch = globalThis.fetch;
  let called = false;
  globalThis.fetch = async () => { called = true; return new Response("{}", { status: 401 }); };
  try {
    const r = await call({ SIGNER_TOKENS: TOKEN, CLOUD_LIBRARY_ID: "L", DB: d1() },
      "GET", "/pipeline/videos?page=1", undefined, TOKEN);
    check(r.status === 500 && /CLOUD_API_KEY/.test(r.data.error) && !called,
      "pipeline proxy names a missing vendor key");
  } finally {
    globalThis.fetch = realFetch;
  }
}
// --retry-failed claims rotate: the least recently tried failed job
// comes first (after any pending work), so one job that keeps
// failing cannot starve every other failed job of its retry.
{
  const rdb = new DatabaseSync(":memory:");
  rdb.exec(readFileSync(join(dir, "migrations", "0002_fetch_jobs.sql"), "utf8"));
  rdb.exec(`INSERT INTO fetch_jobs (id, url, status, attempts, created_at, updated_at) VALUES
    ('job_a', 'https://x/a.mp4', 'failed', 3, 100, 500),
    ('job_b', 'https://x/b.mp4', 'failed', 1, 200, 300),
    ('job_p', 'https://x/p.mp4', 'pending', 0, 900, 900)`);
  const env = { ...authed, DB: d1(rdb) };
  const claim = "/fetch/jobs?claim=1&by=pipe&includeFailed=1";
  const c1 = await call(env, "GET", claim, undefined, TOKEN);
  check(c1.data.job && c1.data.job.id === "job_p", "pending work goes ahead of retries");
  const c2 = await call(env, "GET", claim, undefined, TOKEN);
  check(c2.data.job && c2.data.job.id === "job_b", "a retry takes the least recently tried failed job");
  const c3 = await call(env, "GET", claim, undefined, TOKEN);
  check(c3.data.job && c3.data.job.id === "job_a", "the next retry takes the next one");
}
// Status and delete splice the videoId into the vendor path encoded:
// a malformed id from a client bug must stay one path segment, never
// walk to another vendor endpoint ("x/.." resolves upward).
{
  const realFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url) => {
    seen.push(String(url));
    return new Response(JSON.stringify({ status: 4 }), { status: 200 });
  };
  try {
    await call(authed, "GET", "/?videoId=" + encodeURIComponent("x/../.."), undefined, TOKEN);
    await call(authed, "DELETE", "/?videoId=" + encodeURIComponent("x/../.."), undefined, TOKEN);
    check(seen.length === 2 && seen.every((u) => u.endsWith("/library/L/videos/x%2F..%2F..")),
      "vendor status/delete paths carry the videoId encoded");
  } finally {
    globalThis.fetch = realFetch;
  }
}
// A non-string videoId publishes under its string form instead of
// crashing the handler.
{
  const r = await call(authed, "POST", "/hub/publish", { videoId: 42, title: "Num" }, TOKEN);
  check(r.status === 200 && r.data.published === "42", "a numeric videoId publishes as a string");
  await call(authed, "DELETE", "/hub/sessions/42", undefined, TOKEN);
}
// Parts: several videos tied together read as one overall session.
// A part is any Stream video id — published or not yet — so a take
// can be tied the moment its upload has an id; the hub shows only
// published parts and counts the rest as still processing.
{
  const pub = (videoId, title, extra) => call(authed, "POST", "/hub/publish",
    Object.assign({ videoId, title, lessonDate: "Nov 3, 2026" }, extra || {}), TOKEN);
  await pub("pa", "Croissants", {
    durationSeconds: 60, writeupMd: "Laminate.", mp4Url: "https://cdn/pa.mp4",
    corrections: [{ start: "0:10", quote: "colder", correcting: "butter" }],
    chapters: [{ start: "0:00", label: "Dough" }],
  });
  await pub("pb", "Croissants shaping", {
    durationSeconds: 90, writeupMd: "Roll tight.", mp4Url: "https://cdn/pb.mp4",
    corrections: [{ start: "0:20", quote: "tighter", correcting: "roll" }],
    chapters: [{ start: "0:00", label: "Shaping" }],
  });
  await pub("pc", "Croissants bake", { durationSeconds: 30, writeupMd: "Bake." });

  const bad = await call(authed, "POST", "/hub/parts", { videoIds: ["pa"] }, TOKEN);
  check(bad.status === 400, "tying needs at least two videos");
  const bad2 = await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "pa"] }, TOKEN);
  check(bad2.status === 400, "tying a video to itself is refused");

  const t = await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "pb"] }, TOKEN);
  check(t.status === 200 && typeof t.data.groupId === "string" && t.data.groupId &&
    JSON.stringify(t.data.parts) === JSON.stringify(["pa", "pb"]), "tie returns the group in order");

  let list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  let rows = list.data.filter((r) => ["pa", "pb", "pc"].includes(r.videoId));
  const grp = rows.find((r) => r.videoId === "pa");
  check(rows.length === 2 && grp && !rows.some((r) => r.videoId === "pb"),
    "a tied session lists once, under its first part");
  check(grp.partCount === 2 && grp.durationSeconds === 150 && grp.title === "Croissants" &&
    grp.groupId === t.data.groupId && grp.pendingParts === 0,
    "the listed session carries part count, total length, and group");
  const solo = rows.find((r) => r.videoId === "pc");
  check(solo.partCount === 1 && solo.groupId === "" && solo.pendingParts === 0,
    "an untied session lists as one part");

  const dB = await call(authed, "GET", "/hub/sessions/pb", undefined, TOKEN);
  check(dB.status === 200 && dB.data.videoId === "pa" && dB.data.parts.length === 2 &&
    dB.data.parts[0].videoId === "pa" && dB.data.parts[1].videoId === "pb" &&
    dB.data.parts[1].mp4Url === "https://cdn/pb.mp4" && dB.data.parts[1].durationSeconds === 90,
    "any part opens the whole session, parts in order with their streams");
  check(dB.data.durationSeconds === 150 && dB.data.title === "Croissants",
    "the whole session's length is the sum of its parts");
  check(/\*\*Part 1 — Croissants\*\*/.test(dB.data.writeupMd) &&
    /\*\*Part 2 — Croissants shaping\*\*/.test(dB.data.writeupMd) &&
    dB.data.writeupMd.indexOf("Laminate.") < dB.data.writeupMd.indexOf("Roll tight."),
    "the write-up reads as one, each part under its heading");
  check(dB.data.corrections.length === 2 && dB.data.corrections[0].part === 1 &&
    dB.data.corrections[1].part === 2 && dB.data.corrections[1].start === "0:20" &&
    dB.data.chapters[1].part === 2 && dB.data.chapters[1].label === "Shaping",
    "corrections and chapters carry the part they come from");

  // Tie another (published) and a not-yet-published take onto the end.
  const t2 = await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "pc", "pending-1"] }, TOKEN);
  check(t2.status === 200 && JSON.stringify(t2.data.parts) === JSON.stringify(["pa", "pb", "pc", "pending-1"]),
    "tying more onto a session appends them in order");
  list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  const g3 = list.data.find((r) => r.videoId === "pa");
  check(g3.partCount === 3 && g3.pendingParts === 1 && !list.data.some((r) => r.videoId === "pc"),
    "an unpublished part counts as still processing, not as a row");
  await pub("pending-1", "Croissants tasting", { durationSeconds: 5 });
  list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  const g4 = list.data.find((r) => r.videoId === "pa");
  check(g4.partCount === 4 && g4.pendingParts === 0 && !list.data.some((r) => r.videoId === "pending-1"),
    "a pending part joins the session once the pipeline publishes it");

  // Two groups tie into one, the second group's order kept.
  await pub("qa", "Sourdough", {}); await pub("qb", "Sourdough 2", {});
  await call(authed, "POST", "/hub/parts", { videoIds: ["qa", "qb"] }, TOKEN);
  const m = await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "qa"] }, TOKEN);
  check(JSON.stringify(m.data.parts) === JSON.stringify(["pa", "pb", "pc", "pending-1", "qa", "qb"]),
    "tying two sessions merges them, each keeping its order");

  // Untie: the part stands alone again; a group left with one member dissolves.
  const u = await call(authed, "DELETE", "/hub/parts/qb", undefined, TOKEN);
  check(u.status === 200 && u.data.untied === true, "untie answers untied");
  list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  check(list.data.some((r) => r.videoId === "qb" && r.partCount === 1),
    "an untied part lists as its own session again");
  const u0 = await call(authed, "DELETE", "/hub/parts/never-tied", undefined, TOKEN);
  check(u0.status === 200 && u0.data.untied === false, "untying an untied video is a no-op");
  for (const v of ["pb", "pc", "pending-1", "qa"]) await call(authed, "DELETE", `/hub/parts/${v}`, undefined, TOKEN);
  const solo2 = await call(authed, "GET", "/hub/sessions/pa", undefined, TOKEN);
  check(solo2.data.parts.length === 1 && solo2.data.groupId === "" && solo2.data.writeupMd === "Laminate." &&
    solo2.data.corrections[0].part === 1,
    "the last part left alone dissolves its group and reads as before");

  // Deleting a hub session unties it too.
  await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "pb"] }, TOKEN);
  await call(authed, "DELETE", "/hub/sessions/pb", undefined, TOKEN);
  const afterDel = await call(authed, "GET", "/hub/sessions/pa", undefined, TOKEN);
  check(afterDel.data.parts.length === 1 && afterDel.data.groupId === "",
    "deleting a part from the hub unties it");

  // An ignored part never shows, in the list or the detail.
  await pub("pb", "Croissants shaping", { durationSeconds: 90 });
  await call(authed, "POST", "/hub/parts", { videoIds: ["pa", "pb"] }, TOKEN);
  await call(authed, "POST", "/hub/ignored", { videoId: "pb" }, TOKEN);
  const ig = await call(authed, "GET", "/hub/sessions/pa", undefined, TOKEN);
  list = await call(authed, "GET", "/hub/sessions", undefined, TOKEN);
  const gi = list.data.find((r) => r.videoId === "pa");
  check(ig.data.parts.length === 1 && gi.partCount === 1 && gi.pendingParts === 0,
    "an ignored part is left out, not counted as processing");
  await call(authed, "DELETE", "/hub/ignored/pb", undefined, TOKEN);

  const m405 = await call(authed, "GET", "/hub/parts", undefined, TOKEN);
  check(m405.status === 405, "unknown parts method rejected");
  const nodb = await call(noDb, "POST", "/hub/parts", { videoIds: ["a", "b"] }, TOKEN);
  check(nodb.status === 503, "parts answer 503 with no store");
  for (const v of ["pa", "pb", "pc", "pending-1", "qa", "qb"]) {
    await call(authed, "DELETE", `/hub/parts/${v}`, undefined, TOKEN);
    await call(authed, "DELETE", `/hub/sessions/${v}`, undefined, TOKEN);
  }
}
// A fetched link can continue a session: the job carries joinTo, and
// when the pipeline reports the job done with its new Stream video
// id, the worker ties it onto that session.
{
  await call(authed, "POST", "/hub/publish", { videoId: "fa", title: "Pasta" }, TOKEN);
  const s = await call(authed, "POST", "/fetch/jobs",
    { url: "https://www.youtube.com/watch?v=part2", joinTo: "fa" }, TOKEN);
  check(s.status === 200, "a fetch job can name the session it continues");
  const c = await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  check(c.data.job && c.data.job.id === s.data.id && c.data.job.joinTo === "fa",
    "the claim hands the pipeline the session to continue");
  const d = await call(authed, "POST", `/fetch/jobs/${s.data.id}/done`, { session: "w/2", videoId: "fb" }, TOKEN);
  check(d.status === 200 && d.data.ok === true && d.data.tied === true, "done with a video id ties it on");
  await call(authed, "POST", "/hub/publish", { videoId: "fb", title: "Pasta 2" }, TOKEN);
  const g = await call(authed, "GET", "/hub/sessions/fb", undefined, TOKEN);
  check(g.data.parts.length === 2 && g.data.parts[0].videoId === "fa" && g.data.parts[1].videoId === "fb",
    "the fetched video is the next part of the session");
  const list = await call(authed, "GET", "/fetch/jobs", undefined, TOKEN);
  check(list.data.find((j) => j.id === s.data.id).joinTo === "fa", "the job list shows what it continues");
  const plain = await call(authed, "POST", "/fetch/jobs", { url: "https://x/plain.mp4" }, TOKEN);
  await call(authed, "GET", "/fetch/jobs?claim=1&by=pipe1", undefined, TOKEN);
  const pd = await call(authed, "POST", `/fetch/jobs/${plain.data.id}/done`, { session: "w/3", videoId: "fc" }, TOKEN);
  check(pd.data.ok === true && pd.data.tied === false, "a job without joinTo ties nothing");
  const re = await call(authed, "POST", "/fetch/jobs", { url: "https://x/again.mp4" }, TOKEN);
  const re2 = await call(authed, "POST", "/fetch/jobs", { url: "https://x/again.mp4", joinTo: "fa" }, TOKEN);
  const rl = await call(authed, "GET", "/fetch/jobs", undefined, TOKEN);
  check(re2.data.id === re.data.id && rl.data.find((j) => j.id === re.data.id).joinTo === "fa",
    "resubmitting a queued link with joinTo updates what it continues");
  for (const v of ["fa", "fb"]) {
    await call(authed, "DELETE", `/hub/parts/${v}`, undefined, TOKEN);
    await call(authed, "DELETE", `/hub/sessions/${v}`, undefined, TOKEN);
  }
}
// A store without 0005 names it, on the parts route and on the list.
{
  const old = new DatabaseSync(":memory:");
  for (const f of ["0001_sessions.sql", "0002_fetch_jobs.sql", "0003_ignored.sql", "0004_duration.sql"])
    old.exec(readFileSync(join(dir, "migrations", f), "utf8"));
  const env = { ...authed, DB: d1(old) };
  const p = await call(env, "POST", "/hub/parts", { videoIds: ["a", "b"] }, TOKEN);
  check(p.status === 503 && /0005_parts\.sql/.test(p.data.error), "parts name the missing migration");
  const s = await call(env, "GET", "/hub/sessions", undefined, TOKEN);
  check(s.status === 503 && /0005_parts\.sql/.test(s.data.error), "hub list names 0005 when it is missing");
  const f = await call(env, "POST", "/fetch/jobs", { url: "https://x/y.mp4", joinTo: "a" }, TOKEN);
  check(f.status === 503 && /0005_parts\.sql/.test(f.data.error), "fetch joinTo names 0005 when it is missing");
}
console.log(`ALL HUB CHECKS PASSED (${n})`);
