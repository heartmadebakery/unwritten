/* Unwritten Craft — Cloud signer (Cloudflare Worker).
 *
 * Holds the Stream library API key as a Worker secret so no app
 * client ever ships it. Endpoints, all JSON:
 *
 *   POST /            {title, videoId?} -> {videoId, libraryId, signature,
 *                                          expire, embedUrl}
 *                     Creates the video object (or re-signs videoId so an
 *                     interrupted TUS upload can resume) and returns
 *                     presigned TUS credentials:
 *                     signature = SHA256(libraryId + apiKey + expire + videoId)
 *
 *   GET  /?videoId=X  -> the Stream video object (status polling)
 *
 *   DELETE /?videoId=X -> {deleted: true} (removes the cloud copy)
 *
 *   GET  /pipeline/videos?page=N -> the library listing, passed
 *        through (lets the local pipeline list videos without holding
 *        the vendor key; needs the same token as every other route)
 *
 * Env: CLOUD_LIBRARY_ID (var), CLOUD_API_KEY (secret).
 * Optional: SIGNER_TOKENS (secret) — comma-separated token pool; a
 * caller is authorized when its X-Signer-Token header matches ANY
 * entry, so each distributed build can carry its own token and a leak
 * revokes one build instead of all of them. The older single
 * SIGNER_TOKEN secret is still honored as a fallback.
 * CORS_ORIGIN (var) — default "*"; set to your app origin before
 * real use. The vendor's docs warn that an open create route lets
 * anyone fill your library; the token + origin are the minimum.
 *
 * Trust boundary: one token authorizes the whole library — re-sign,
 * status, delete, and the listing proxy take any videoId with no
 * ownership check. That is deliberate (tokens go only to our own
 * builds and the pipeline machine), but treat a token as
 * library-admin: a leaked one revokes that build (rotate it out of
 * SIGNER_TOKENS), and per-token issuance tracking would be the next
 * step if tokens ever go to third parties.
 *
 * Hub store (D1, SQLite): the published lessons behind the in-app hub.
 *
 *   POST /hub/publish  {videoId, libraryId?, title?, lessonDate?,
 *                       hlsUrl?, mp4Url?, writeupMd?, corrections?,
 *                       chapters?, glossary?} -> {published: videoId}
 *                     Upserts the session row. pipeline/publish.py pushes
 *                     finished runs here; videoId is required, everything
 *                     else defaults to empty.
 *
 *   GET  /hub/sessions -> [{videoId, libraryId, title, lessonDate,
 *                           publishedAt}]  (newest first)
 *
 *   GET  /hub/sessions/<videoId> -> the full session row
 *
 *   DELETE /hub/sessions/<videoId> -> {deleted: true}
 *
 * Env: DB (d1_databases binding, see wrangler.toml + migrations/).
 * Without it the /hub/* routes answer 503 — uploads keep working.
 *
 * URL fetch queue (D1 table fetch_jobs): the apps queue video URLs
 * the browser cannot download itself (YouTube/watch pages); the
 * pipeline machine claims them one at a time, downloads each
 * (yt-dlp or direct), and runs it like any session.
 *
 *   POST /fetch/jobs  {url} -> {id, status} (resubmitting a queued
 *                       URL returns the existing job)
 *   GET  /fetch/jobs   -> the 50 most recent jobs, newest first
 *   GET  /fetch/jobs?claim=1&by=<worker>[&includeFailed=1]
 *                     -> {job: {id, url, attempts, session} | null}
 *                     (oldest pending first; failed stays failed
 *                     unless includeFailed=1, like --retry-failed;
 *                     claims older than two hours count as abandoned
 *                     and come back)
 *   POST /fetch/jobs/<id>/done   {session?} -> {ok: true}
 *   POST /fetch/jobs/<id>/failed {error?}   -> {ok: true}
 */

const CLOUD_API = "https://video.bunnycdn.com";

export default {
  async fetch(request, env) {
    const origin = env.CORS_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Signer-Token",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    };
    const json = (obj, status) =>
      new Response(JSON.stringify(obj), {
        status: status || 200,
        headers: Object.assign({ "Content-Type": "application/json" }, cors),
      });
    // A corrupt JSON column (hand-edited D1, old writer) serves as
    // empty instead of 500ing the whole hub.
    const parseList = (text) => {
      try {
        const v = JSON.parse(text || "[]");
        return Array.isArray(v) ? v : [];
      } catch { return []; }
    };
    const parseObj = (text) => {
      try {
        const v = JSON.parse(text || "{}");
        return v && typeof v === "object" && !Array.isArray(v) ? v : {};
      } catch { return {}; }
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const pool = (env.SIGNER_TOKENS || "").split(",").map((t) => t.trim()).filter(Boolean);
    if (env.SIGNER_TOKEN) pool.push(env.SIGNER_TOKEN);
    if (pool.length && !pool.includes(request.headers.get("X-Signer-Token") || "")) {
      return json({ error: "unauthorized" }, 401);
    }
    // Clients paste signer URLs with or without a trailing slash;
    // normalize so every form routes the same.
    const normPath = new URL(request.url).pathname.replace(/\/+/g, "/").replace(/\/+$/, "") || "/";
    // Pipeline proxy: lets the local pipeline list videos without
    // holding the vendor API key (it sends X-Signer-Token). Behind
    // the token check like every other route — an open proxy would
    // leak the library listing to anyone.
    {
      const pUrl = new URL(request.url);
      if (normPath === "/pipeline/videos") {
        const page = pUrl.searchParams.get("page") || "1";
        const br = await fetch(CLOUD_API + "/library/" + env.CLOUD_LIBRARY_ID + "/videos?page=" + page + "&itemsPerPage=100&orderBy=date", {
          headers: { AccessKey: env.CLOUD_API_KEY, Accept: "application/json" }
        });
        return new Response(await br.text(), { status: br.status, headers: Object.assign({ "Content-Type": "application/json" }, cors) });
      }
    }
    // URL fetch queue: needs only the token gate above plus D1 — no
    // cloud credentials — so it lives ahead of the CLOUD check below
    // and keeps queueing while cloud creds rotate.
    if (normPath === "/fetch/jobs") {
      const store = hubStore(env);
      if (!store) return json({ error: "fetch store not configured" }, 503);
      if (request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const url = String(body.url || "").trim();
        if (!url) return json({ error: "url required" }, 400);
        if (url.length > 2000 || !/^https?:\/\/.+\..+/.test(url))
          return json({ error: "url must be an http(s) URL" }, 400);
        const now = Math.floor(Date.now() / 1000);
        const dup = await store
          .prepare("SELECT id, status FROM fetch_jobs WHERE url = ? AND status IN ('pending','claimed')")
          .bind(url).first();
        if (dup) return json({ id: dup.id, status: dup.status });
        const id = "job_" + crypto.randomUUID().replace(/-/g, "");
        await store
          .prepare(`INSERT INTO fetch_jobs (id, url, status, attempts, created_at, updated_at)
                    VALUES (?, ?, 'pending', 0, ?, ?)`)
          .bind(id, url, now, now).run();
        return json({ id, status: "pending" });
      }
      if (request.method === "GET") {
        const qs = new URL(request.url).searchParams;
        if (qs.get("claim") === "1") {
          const by = (qs.get("by") || "").trim();
          if (!by) return json({ error: "by (worker name) required" }, 400);
          const states = qs.get("includeFailed") === "1" ? "('pending','failed')" : "('pending')";
          const now = Math.floor(Date.now() / 1000);
          // A claim older than two hours is a crashed worker, not a
          // running one: hand the job out again instead of sticking it
          // in claimed forever. One pipeline machine claims (cron
          // flock); no fencing beyond that.
          const job = await store
            .prepare(`SELECT * FROM fetch_jobs WHERE status IN ${states} OR (status='claimed' AND updated_at < ?) ORDER BY created_at ASC, id ASC LIMIT 1`)
            .bind(now - 7200).first();
          if (!job) return json({ job: null });
          await store
            .prepare(`UPDATE fetch_jobs SET status='claimed', claimed_by=?, updated_at=? WHERE id=?`)
            .bind(by, now, job.id).run();
          return json({ job: { id: job.id, url: job.url, attempts: job.attempts || 0, session: job.session || "" } });
        }
        const rows = await store
          .prepare(`SELECT * FROM fetch_jobs ORDER BY created_at DESC, id ASC LIMIT 50`).all();
        return json((rows.results || []).map((r) => ({
          id: r.id, url: r.url, status: r.status, attempts: r.attempts,
          claimedBy: r.claimed_by, error: r.error, session: r.session,
          createdAt: r.created_at, updatedAt: r.updated_at,
        })));
      }
      return json({ error: "method not allowed" }, 405);
    }
    {
      const m = normPath.match(/^\/fetch\/jobs\/([^/]+)\/(done|failed)$/);
      if (m) {
        const store = hubStore(env);
        if (!store) return json({ error: "fetch store not configured" }, 503);
        if (request.method !== "POST") return json({ error: "method not allowed" }, 405);
        const id = decodeURIComponent(m[1]), verb = m[2];
        const job = await store.prepare(`SELECT * FROM fetch_jobs WHERE id = ?`).bind(id).first();
        if (!job) return json({ error: "not found" }, 404);
        if (job.status !== "claimed")
          return json({ error: "job is " + job.status + ", only a claimed job can finish" }, 409);
        const now = Math.floor(Date.now() / 1000);
        const body = await request.json().catch(() => ({}));
        if (verb === "done") {
          await store.prepare(`UPDATE fetch_jobs SET status='done', session=?, updated_at=? WHERE id=?`)
            .bind(String(body.session || "").slice(0, 500), now, id).run();
        } else {
          await store.prepare(`UPDATE fetch_jobs SET status='failed', attempts=attempts+1, error=?, updated_at=? WHERE id=?`)
            .bind(String(body.error || "").slice(0, 500), now, id).run();
        }
        return json({ ok: true });
      }
    }
    if (!env.CLOUD_LIBRARY_ID || !env.CLOUD_API_KEY) {
      return json({ error: "signer not configured (CLOUD_LIBRARY_ID / CLOUD_API_KEY)" }, 500);
    }
    const url = new URL(request.url);
    try {
      if (normPath === "/hub/publish" && request.method === "POST") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        const body = await request.json().catch(() => ({}));
        const videoId = (body.videoId || "").trim();
        if (!videoId) return json({ error: "videoId required" }, 400);
        const now = Math.floor(Date.now() / 1000);
        await store
          .prepare(
            `INSERT INTO sessions
               (video_id, library_id, title, lesson_date, hls_url, mp4_url,
                writeup_md, corrections_json, chapters_json, glossary_json,
                published_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(video_id) DO UPDATE SET
               library_id=excluded.library_id, title=excluded.title,
               lesson_date=excluded.lesson_date, hls_url=excluded.hls_url,
               mp4_url=excluded.mp4_url, writeup_md=excluded.writeup_md,
               corrections_json=excluded.corrections_json,
               chapters_json=excluded.chapters_json,
               glossary_json=excluded.glossary_json,
               published_at=excluded.published_at`
          )
          .bind(
            videoId,
            String(body.libraryId || env.CLOUD_LIBRARY_ID || ""),
            String(body.title || ""),
            String(body.lessonDate || ""),
            String(body.hlsUrl || ""),
            String(body.mp4Url || ""),
            String(body.writeupMd || ""),
            JSON.stringify(body.corrections || []),
            JSON.stringify(body.chapters || []),
            JSON.stringify(body.glossary || {}),
            now
          )
          .run();
        return json({ published: videoId });
      }
      if (normPath === "/hub/sessions" && request.method === "GET") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        const rows = await store
          .prepare(
            `SELECT video_id, library_id, title, lesson_date, published_at
             FROM sessions ORDER BY published_at DESC, video_id ASC`
          )
          .all();
        return json(
          (rows.results || []).map((r) => ({
            videoId: r.video_id,
            libraryId: r.library_id,
            title: r.title,
            lessonDate: r.lesson_date,
            publishedAt: r.published_at,
          }))
        );
      }
      {
        const m = normPath.match(/^\/hub\/sessions\/([^/]+)$/);
        if (m) {
          const store = hubStore(env);
          if (!store) return json({ error: "hub store not configured" }, 503);
          const videoId = decodeURIComponent(m[1]);
          if (request.method === "GET") {
            const row = await store
              .prepare(`SELECT * FROM sessions WHERE video_id = ?`)
              .bind(videoId)
              .first();
            if (!row) return json({ error: "not found" }, 404);
            return json({
              videoId: row.video_id,
              libraryId: row.library_id,
              title: row.title,
              lessonDate: row.lesson_date,
              hlsUrl: row.hls_url,
              mp4Url: row.mp4_url,
              writeupMd: row.writeup_md,
              corrections: parseList(row.corrections_json),
              chapters: parseList(row.chapters_json),
              glossary: parseObj(row.glossary_json),
              publishedAt: row.published_at,
            });
          }
          if (request.method === "DELETE") {
            await store
              .prepare(`DELETE FROM sessions WHERE video_id = ?`)
              .bind(videoId)
              .run();
            return json({ deleted: true });
          }
          return json({ error: "method not allowed" }, 405);
        }
      }
      if (request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        let videoId = body.videoId || null;
        if (!videoId) {
          const create = await fetch(`${CLOUD_API}/library/${env.CLOUD_LIBRARY_ID}/videos`, {
            method: "POST",
            headers: {
              "AccessKey": env.CLOUD_API_KEY,
              "Accept": "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ title: body.title || "Untitled lesson" }),
          });
          if (!create.ok) return json({ error: "cloud create failed", status: create.status }, 502);
          const video = await create.json();
          videoId = video.guid || video.videoId || video.id;
          if (!videoId) return json({ error: "cloud create returned no id" }, 502);
        }
        const expire = Math.floor(Date.now() / 1000) + 86400;
        const signature = await sha256Hex(`${env.CLOUD_LIBRARY_ID}${env.CLOUD_API_KEY}${expire}${videoId}`);
        return json({
          videoId,
          libraryId: env.CLOUD_LIBRARY_ID,
          signature,
          expire,
          embedUrl: `https://player.mediadelivery.net/embed/${env.CLOUD_LIBRARY_ID}/${videoId}`,
        });
      }
      if (request.method === "GET") {
        const videoId = url.searchParams.get("videoId");
        if (!videoId) return json({ error: "videoId required" }, 400);
        const r = await fetch(`${CLOUD_API}/library/${env.CLOUD_LIBRARY_ID}/videos/${videoId}`, {
          headers: { "AccessKey": env.CLOUD_API_KEY, "Accept": "application/json" },
        });
        let body;
        try { body = await r.json(); } catch (_) { body = { status: r.status, error: r.status === 404 ? "not found" : "empty response" }; }
        return json(body, r.status);
      }
      if (request.method === "DELETE") {
        const videoId = url.searchParams.get("videoId");
        if (!videoId) return json({ error: "videoId required" }, 400);
        const r = await fetch(`${CLOUD_API}/library/${env.CLOUD_LIBRARY_ID}/videos/${videoId}`, {
          method: "DELETE",
          headers: { "AccessKey": env.CLOUD_API_KEY, "Accept": "application/json" },
        });
        if (!r.ok && r.status !== 404) return json({ error: "cloud delete failed", status: r.status }, 502);
        return json({ deleted: true });
      }
      return json({ error: "method not allowed" }, 405);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};

function hubStore(env) {
  return (env && env.DB) || null;
}

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => ("0" + b.toString(16)).slice(-2)).join("");
}
