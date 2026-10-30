/* Unwritten Craft — Cloud signer (Cloudflare Worker).
 *
 * Holds the Stream library API key as a Worker secret so neither
 * recorder client ever ships it. Three endpoints, all JSON:
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
 * Env: CLOUD_LIBRARY_ID (var), CLOUD_API_KEY (secret).
 * Optional: SIGNER_TOKENS (secret) — comma-separated token pool; a
 * caller is authorized when its X-Signer-Token header matches ANY
 * entry, so each distributed build can carry its own token and a leak
 * revokes one build instead of all of them. The older single
 * SIGNER_TOKEN secret is still honored as a fallback.
 * CORS_ORIGIN (var) — default "*"; set to your recorder origin before
 * real use. The vendor's docs warn that an open create route lets
 * anyone fill your library; the token + origin are the minimum.
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
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const pool = (env.SIGNER_TOKENS || "").split(",").map((t) => t.trim()).filter(Boolean);
    if (env.SIGNER_TOKEN) pool.push(env.SIGNER_TOKEN);
    if (pool.length && !pool.includes(request.headers.get("X-Signer-Token") || "")) {
      return json({ error: "unauthorized" }, 401);
    }
    if (!env.CLOUD_LIBRARY_ID || !env.CLOUD_API_KEY) {
      return json({ error: "signer not configured (CLOUD_LIBRARY_ID / CLOUD_API_KEY)" }, 500);
    }
    const url = new URL(request.url);
    try {
      if (url.pathname === "/hub/publish" && request.method === "POST") {
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
      if (url.pathname === "/hub/sessions" && request.method === "GET") {
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
        const m = url.pathname.match(/^\/hub\/sessions\/([^/]+)$/);
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
              corrections: JSON.parse(row.corrections_json || "[]"),
              chapters: JSON.parse(row.chapters_json || "[]"),
              glossary: JSON.parse(row.glossary_json || "{}"),
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
