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
 *                       chapters?, glossary?, durationSeconds?} -> {published: videoId}
 *                     Upserts the session row. pipeline/publish.py pushes
 *                     finished runs here; videoId is required, everything
 *                     else defaults to empty.
 *
 *   GET  /hub/sessions -> [{videoId, libraryId, title, lessonDate,
 *                           durationSeconds, publishedAt}]  (newest first)
 *
 *   GET  /hub/sessions/<videoId> -> the full session row
 *
 *   DELETE /hub/sessions/<videoId> -> {deleted: true} (also unties it)
 *
 *   Parts (D1 table session_parts): several videos tied together read
 *   as one overall session — a lesson filmed in several takes,
 *   uploaded in pieces, or fetched from more than one link. A part
 *   may be a video the pipeline has not published yet (the apps tie a
 *   take as soon as its upload has an id); the hub shows published
 *   parts only and counts the rest as pendingParts.
 *
 *   POST /hub/parts  {videoIds: [a, b, ...]} -> {groupId, parts: [...]}
 *                     Ties b, ... onto a's session in that order (a
 *                     video already in another session brings its
 *                     whole session along, order kept).
 *   DELETE /hub/parts/<videoId> -> {untied: bool} (the video stands
 *                     alone again; a session left with one part
 *                     dissolves)
 *
 *   With parts, GET /hub/sessions lists each tied session once, under
 *   its first published part, with partCount, groupId, pendingParts,
 *   and the summed durationSeconds (untied rows: partCount 1, groupId
 *   ""). GET /hub/sessions/<any part> answers the whole session: the
 *   first part's fields, the summed length, one write-up with a
 *   "**Part N — title**" heading per part, corrections and chapters
 *   tagged with their 1-based part, and parts: [{videoId, libraryId,
 *   title, lessonDate, durationSeconds, hlsUrl, mp4Url}] in order.
 *
 *   Ignored videos (D1 table ignored_videos): operator set-asides
 *   the hub never shows. The pipeline syncs them here; the
 *   recorders badge them on the Record screen instead.
 *
 *   POST /hub/ignored  {videoId, title?, reason?} -> {ignored: videoId}
 *                     Upserts the marker; videoId is required.
 *   GET  /hub/ignored -> [{videoId, title, reason, ignoredAt}]
 *                     (newest first)
 *   DELETE /hub/ignored/<videoId> -> {deleted: true} (un-ignores;
 *                     a published session becomes visible again)
 *
 * Env: DB (d1_databases binding, see wrangler.toml + migrations/).
 * Without it the /hub/* routes answer 503 — uploads keep working.
 * A store missing a migration answers 503 naming the file to apply.
 *
 * URL fetch queue (D1 table fetch_jobs): the apps queue video URLs
 * the browser cannot download itself (YouTube/watch pages); the
 * pipeline machine claims them one at a time, downloads each
 * (yt-dlp or direct), and runs it like any session.
 *
 *   POST /fetch/jobs  {url, joinTo?} -> {id, status} (resubmitting a
 *                       queued URL returns the existing job; joinTo, a
 *                       session's video id, makes the fetched video
 *                       its next part)
 *   GET  /fetch/jobs   -> the 50 most recent jobs, newest first
 *   GET  /fetch/jobs?claim=1&by=<worker>[&includeFailed=1]
 *                     -> {job: {id, url, attempts, session, joinTo} | null}
 *                     (oldest pending first; failed stays failed
 *                     unless includeFailed=1, like --retry-failed,
 *                     and those retries follow pending work, least
 *                     recently tried first; claims older than two
 *                     hours count as abandoned and come back)
 *   POST /fetch/jobs/<id>/done   {session?, videoId?} -> {ok: true, tied}
 *                     (videoId is the fetched lesson's Stream id: a
 *                     job with joinTo ties it onto that session)
 *   POST /fetch/jobs/<id>/failed {error?}   -> {ok: true}
 */

const CLOUD_API = "https://video.bunnycdn.com";
// Which migration creates each D1 table (see migrations/).
const MIGRATIONS = {
  sessions: "0001_sessions.sql",
  fetch_jobs: "0002_fetch_jobs.sql",
  ignored_videos: "0003_ignored.sql",
  duration_seconds: "0004_duration.sql",
  session_parts: "0005_parts.sql",
  join_to: "0005_parts.sql",
};

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
    // Every failure answers JSON with CORS (a thrown D1 or network
    // error would otherwise surface as the platform's HTML error
    // page), and a store migrated short of the schema — a deployed
    // worker whose D1 never got 0002/0003 — names the file to apply.
    const failed = (e) => {
      const msg = String((e && e.message) || e);
      let m = msg.match(/no such table: (\w+)/);
      let file = m && MIGRATIONS[m[1]];
      if (!file) {
        m = msg.match(/no such column: (\w+)/) || msg.match(/has no column named (\w+)/);
        file = m && MIGRATIONS[m[1]];
      }
      if (file) {
        const what = m ? (/no such table/.test(msg) ? `table ${m[1]}` : `column ${m[1]}`) : "store";
        return json({ error: `hub store is missing ${what} — apply migrations/${file}: ` +
          `npx wrangler d1 execute unwritten-hub --remote --file migrations/${file}` }, 503);
      }
      return json({ error: msg }, 500);
    };
    try {
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      const pool = (env.SIGNER_TOKENS || "").split(",").map((t) => t.trim()).filter(Boolean);
      if (env.SIGNER_TOKEN) pool.push(env.SIGNER_TOKEN);
      // No pool configured fails LOUD, never open: an unset
      // SIGNER_TOKENS must not silently serve the library to the world.
      if (!pool.length) return json({ error: "signer tokens not configured" }, 500);
      if (!pool.includes(request.headers.get("X-Signer-Token") || "")) {
        return json({ error: "unauthorized" }, 401);
      }
      // Clients paste signer URLs with or without a trailing slash;
      // normalize so every form routes the same.
      const normPath = new URL(request.url).pathname.replace(/\/+/g, "/").replace(/\/+$/, "") || "/";
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
          if (url.length > 2000 || !/^https?:\/\/.+/.test(url))
            return json({ error: "url must be an http(s) URL" }, 400);
          const joinTo = String(body.joinTo || "").trim().slice(0, 200);
          const now = Math.floor(Date.now() / 1000);
          const dup = await store
            .prepare("SELECT id, status FROM fetch_jobs WHERE url = ? AND status IN ('pending','claimed')")
            .bind(url).first();
          if (dup) {
            // The newest choice of session wins for a link still queued.
            if (joinTo)
              await store.prepare(`UPDATE fetch_jobs SET join_to=? WHERE id=?`).bind(joinTo, dup.id).run();
            return json({ id: dup.id, status: dup.status });
          }
          const id = "job_" + crypto.randomUUID().replace(/-/g, "");
          // join_to only when asked: a store without 0005 keeps
          // queueing plain links, and a continue names the migration.
          if (joinTo) {
            await store
              .prepare(`INSERT INTO fetch_jobs (id, url, status, attempts, created_at, updated_at, join_to)
                        VALUES (?, ?, 'pending', 0, ?, ?, ?)`)
              .bind(id, url, now, now, joinTo).run();
          } else {
            await store
              .prepare(`INSERT INTO fetch_jobs (id, url, status, attempts, created_at, updated_at)
                        VALUES (?, ?, 'pending', 0, ?, ?)`)
              .bind(id, url, now, now).run();
          }
          return json({ id, status: "pending" });
        }
        if (request.method === "GET") {
          const qs = new URL(request.url).searchParams;
          if (qs.get("claim") === "1") {
            const by = (qs.get("by") || "").trim();
            if (!by) return json({ error: "by (worker name) required" }, 400);
            const retry = qs.get("includeFailed") === "1";
            const states = retry ? "('pending','failed')" : "('pending')";
            // Retries go after pending work, least recently tried
            // first: oldest-created first would hand one job that
            // keeps failing back every time, and no other failed job
            // would ever get its retry.
            const order = retry
              ? "ORDER BY (status = 'failed') ASC, CASE WHEN status = 'failed' THEN updated_at ELSE created_at END ASC, id ASC"
              : "ORDER BY created_at ASC, id ASC";
            const now = Math.floor(Date.now() / 1000);
            // A claim older than two hours is a crashed worker, not a
            // running one: hand the job out again instead of sticking it
            // in claimed forever. One pipeline machine claims (cron
            // flock); no fencing beyond that.
            const job = await store
              .prepare(`SELECT * FROM fetch_jobs WHERE status IN ${states} OR (status='claimed' AND updated_at < ?) ${order} LIMIT 1`)
              .bind(now - 7200).first();
            if (!job) return json({ job: null });
            await store
              .prepare(`UPDATE fetch_jobs SET status='claimed', claimed_by=?, updated_at=? WHERE id=?`)
              .bind(by, now, job.id).run();
            return json({ job: { id: job.id, url: job.url, attempts: job.attempts || 0,
              session: job.session || "", joinTo: job.join_to || "" } });
          }
          const rows = await store
            .prepare(`SELECT * FROM fetch_jobs ORDER BY created_at DESC, id ASC LIMIT 50`).all();
          return json((rows.results || []).map((r) => ({
            id: r.id, url: r.url, status: r.status, attempts: r.attempts,
            claimedBy: r.claimed_by, error: r.error, session: r.session,
            joinTo: r.join_to || "",
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
          let id;
          try { id = decodeURIComponent(m[1]); } catch { return json({ error: "bad job id" }, 400); }
          const verb = m[2];
          const job = await store.prepare(`SELECT * FROM fetch_jobs WHERE id = ?`).bind(id).first();
          if (!job) return json({ error: "not found" }, 404);
          if (job.status !== "claimed")
            return json({ error: "job is " + job.status + ", only a claimed job can finish" }, 409);
          const now = Math.floor(Date.now() / 1000);
          const body = await request.json().catch(() => ({}));
          if (verb === "done") {
            await store.prepare(`UPDATE fetch_jobs SET status='done', session=?, updated_at=? WHERE id=?`)
              .bind(String(body.session || "").slice(0, 500), now, id).run();
            // A link that continues a session becomes its next part.
            const videoId = String(body.videoId || "").trim();
            const joinTo = String(job.join_to || "").trim();
            let tied = false;
            if (joinTo && videoId && joinTo !== videoId) {
              await tieParts(store, [joinTo, videoId], now);
              tied = true;
            }
            return json({ ok: true, tied });
          } else {
            await store.prepare(`UPDATE fetch_jobs SET status='failed', attempts=attempts+1, error=?, updated_at=? WHERE id=?`)
              .bind(String(body.error || "").slice(0, 500), now, id).run();
          }
          return json({ ok: true });
        }
      }
      // Parts: tie videos into one overall session, or untie one.
      // Like the fetch queue, needs only the token gate plus D1.
      if (normPath === "/hub/parts") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        if (request.method !== "POST") return json({ error: "method not allowed" }, 405);
        const body = await request.json().catch(() => ({}));
        const raw = Array.isArray(body.videoIds) ? body.videoIds : [];
        const ids = [];
        for (const v of raw) {
          const id = String(v == null ? "" : v).trim();
          if (id && id.length <= 200 && !ids.includes(id)) ids.push(id);
        }
        if (ids.length < 2) return json({ error: "videoIds needs at least two different videos" }, 400);
        if (ids.length > 50) return json({ error: "at most 50 parts in one session" }, 400);
        const tied = await tieParts(store, ids, Math.floor(Date.now() / 1000));
        return json(tied);
      }
      {
        const m = normPath.match(/^\/hub\/parts\/([^/]+)$/);
        if (m) {
          const store = hubStore(env);
          if (!store) return json({ error: "hub store not configured" }, 503);
          if (request.method !== "DELETE") return json({ error: "method not allowed" }, 405);
          let videoId;
          try { videoId = decodeURIComponent(m[1]); } catch { return json({ error: "bad video id" }, 400); }
          return json({ untied: await untiePart(store, videoId) });
        }
      }
      // Ignored videos: operator set-asides the hub never shows. Like
      // the fetch queue, needs only the token gate plus D1.
      if (normPath === "/hub/ignored") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        if (request.method === "POST") {
          const body = await request.json().catch(() => ({}));
          const videoId = String(body.videoId || "").trim();
          if (!videoId) return json({ error: "videoId required" }, 400);
          const now = Math.floor(Date.now() / 1000);
          await store
            .prepare(
              `INSERT INTO ignored_videos (video_id, title, reason, ignored_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title, reason=excluded.reason,
                 ignored_at=excluded.ignored_at`
            )
            .bind(videoId, String(body.title || ""),
              String(body.reason || ""), now).run();
          return json({ ignored: videoId });
        }
        if (request.method === "GET") {
          const rows = await store
            .prepare(
              `SELECT video_id, title, reason, ignored_at FROM ignored_videos
               ORDER BY ignored_at DESC, video_id ASC`
            )
            .all();
          return json(
            (rows.results || []).map((r) => ({
              videoId: r.video_id,
              title: r.title,
              reason: r.reason,
              ignoredAt: r.ignored_at,
            }))
          );
        }
        return json({ error: "method not allowed" }, 405);
      }
      {
        const m = normPath.match(/^\/hub\/ignored\/([^/]+)$/);
        if (m) {
          const store = hubStore(env);
          if (!store) return json({ error: "hub store not configured" }, 503);
          let videoId;
          try { videoId = decodeURIComponent(m[1]); } catch { return json({ error: "bad video id" }, 400); }
          if (request.method === "DELETE") {
            await store
              .prepare(`DELETE FROM ignored_videos WHERE video_id = ?`)
              .bind(videoId)
              .run();
            return json({ deleted: true });
          }
          return json({ error: "method not allowed" }, 405);
        }
      }
      if (!env.CLOUD_LIBRARY_ID || !env.CLOUD_API_KEY) {
        return json({ error: "signer not configured (CLOUD_LIBRARY_ID / CLOUD_API_KEY)" }, 500);
      }
      const url = new URL(request.url);
      // Pipeline proxy: lets the local pipeline list videos without
      // holding the vendor API key (it sends X-Signer-Token). Behind
      // the token check like every other route — an open proxy would
      // leak the library listing to anyone — and behind the config
      // check: an empty AccessKey's vendor 401 would read like a bad
      // signer token.
      if (normPath === "/pipeline/videos") {
        const page = parseInt(url.searchParams.get("page") || "1", 10) || 1;
        const br = await fetch(CLOUD_API + "/library/" + env.CLOUD_LIBRARY_ID + "/videos?page=" + page + "&itemsPerPage=100&orderBy=date", {
          headers: { AccessKey: env.CLOUD_API_KEY, Accept: "application/json" }
        });
        return new Response(await br.text(), { status: br.status, headers: Object.assign({ "Content-Type": "application/json" }, cors) });
      }
      if (normPath === "/hub/publish" && request.method === "POST") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        const body = await request.json().catch(() => ({}));
        const videoId = String(body.videoId || "").trim();
        if (!videoId) return json({ error: "videoId required" }, 400);
        const now = Math.floor(Date.now() / 1000);
        const durationSeconds = Math.max(0, Math.floor(Number(body.durationSeconds) || 0));
        let hubTitle = String(body.title || "");
        if (hubTitle) {
          const dup = await store.prepare(`SELECT video_id FROM sessions WHERE title = ? AND video_id != ? LIMIT 1`).bind(hubTitle, videoId).first();
          if (dup) {
            const chs = Array.isArray(body.chapters) ? body.chapters : [];
            const STOP = new Set(["introduction","intro","overview","welcome","summary","conclusion","closing","next","steps","questions","answered","discussion","explained","general","and","the","a","an","of","for","in","on","to","with"]);
            const baseWords = new Set((hubTitle.toLowerCase().match(/[a-z0-9]+/g) || []));
            let phrase = "";
            for (const ch of chs) {
              const label = ch && ch.label ? String(ch.label) : "";
              const words = (label.toLowerCase().match(/[a-z0-9]+/g) || []);
              const keep = words.filter(w => !STOP.has(w) && !baseWords.has(w));
              if (keep.length) { phrase = keep.slice(0,3).map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(" "); break; }
            }
            if (!phrase) {
              for (const ch of chs) {
                const label = ch && ch.label ? String(ch.label) : "";
                const words = (label.toLowerCase().match(/[a-z0-9]+/g) || []);
                const keep = words.filter(w => !STOP.has(w));
                if (keep.length) { const cand = keep.slice(0,3).map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(" "); if (cand.toLowerCase() !== hubTitle.toLowerCase()) { phrase = cand; break; } }
              }
            }
            let cand = "";
            if (phrase) cand = `${hubTitle} \u2014 ${phrase}`;
            else if (body.lessonDate) cand = `${hubTitle} \u2014 ${String(body.lessonDate)}`;
            if (cand) {
              let tries = cand, n = 2;
              while (await store.prepare(`SELECT video_id FROM sessions WHERE title = ? AND video_id != ? LIMIT 1`).bind(tries, videoId).first()) { tries = `${cand} (${n++})`; }
              hubTitle = tries;
            } else {
              let tries = hubTitle, n = 2;
              do { tries = `${hubTitle} (${n++})`; } while (await store.prepare(`SELECT video_id FROM sessions WHERE title = ? AND video_id != ? LIMIT 1`).bind(tries, videoId).first());
              hubTitle = tries;
            }
          }
        }
        await store
          .prepare(
            `INSERT INTO sessions
                (video_id, library_id, title, lesson_date, hls_url, mp4_url,
                 writeup_md, corrections_json, chapters_json, glossary_json,
                 published_at, duration_seconds)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
              ON CONFLICT(video_id) DO UPDATE SET
                library_id=excluded.library_id, title=excluded.title,
                lesson_date=excluded.lesson_date, hls_url=excluded.hls_url,
                mp4_url=excluded.mp4_url, writeup_md=excluded.writeup_md,
                corrections_json=excluded.corrections_json,
                chapters_json=excluded.chapters_json,
                glossary_json=excluded.glossary_json,
                published_at=excluded.published_at,
                duration_seconds=excluded.duration_seconds`
          )
          .bind(
            videoId,
            String(body.libraryId || env.CLOUD_LIBRARY_ID || ""),
            hubTitle,
            String(body.lessonDate || ""),
            String(body.hlsUrl || ""),
            String(body.mp4Url || ""),
            String(body.writeupMd || ""),
            JSON.stringify(body.corrections || []),
            JSON.stringify(body.chapters || []),
            JSON.stringify(body.glossary || {}),
            now,
            durationSeconds
          )
          .run();
        return json({ published: videoId });
      }
      if (normPath === "/hub/sessions" && request.method === "GET") {
        const store = hubStore(env);
        if (!store) return json({ error: "hub store not configured" }, 503);
        const rows = await store
          .prepare(
            `SELECT video_id, library_id, title, lesson_date, published_at, duration_seconds
             FROM sessions
             WHERE video_id NOT IN (SELECT video_id FROM ignored_videos)
             ORDER BY published_at DESC, video_id ASC`
          )
          .all();
        const parts = await store
          .prepare(
            `SELECT p.video_id, p.group_id, p.position,
                    (s.video_id IS NOT NULL) AS published
             FROM session_parts p LEFT JOIN sessions s ON s.video_id = p.video_id
             WHERE p.video_id NOT IN (SELECT video_id FROM ignored_videos)
             ORDER BY p.group_id ASC, p.position ASC, p.video_id ASC`
          )
          .all();
        // Collapse each tied session into one row, placed where its
        // newest part falls in the newest-first order.
        const partOf = {}, pending = {}, firstOf = {};
        for (const p of parts.results || []) {
          if (!p.published) { pending[p.group_id] = (pending[p.group_id] || 0) + 1; continue; }
          partOf[p.video_id] = p.group_id;
          if (!(p.group_id in firstOf)) firstOf[p.group_id] = p.video_id;
        }
        const out = [], byGroup = {};
        const all = rows.results || [];
        const rowById = {};
        for (const r of all) rowById[r.video_id] = r;
        for (const r of all) {
          const g = partOf[r.video_id] || "";
          if (!g) {
            out.push({
              videoId: r.video_id, libraryId: r.library_id, title: r.title,
              lessonDate: r.lesson_date, durationSeconds: r.duration_seconds | 0,
              publishedAt: r.published_at, partCount: 1, groupId: "", pendingParts: 0,
            });
            continue;
          }
          if (byGroup[g]) {
            byGroup[g].partCount++;
            byGroup[g].durationSeconds += r.duration_seconds | 0;
            continue;
          }
          const first = rowById[firstOf[g]] || r;
          byGroup[g] = {
            videoId: first.video_id, libraryId: first.library_id, title: first.title,
            lessonDate: first.lesson_date, durationSeconds: r.duration_seconds | 0,
            publishedAt: r.published_at, partCount: 1, groupId: g, pendingParts: pending[g] || 0,
          };
          out.push(byGroup[g]);
        }
        // A session whose only published part is alone with parts
        // still processing keeps its group, so the count shows.
        for (const row of out) {
          if (row.groupId && row.partCount === 1 && !row.pendingParts) row.groupId = "";
        }
        return json(out);
      }
      {
        const m = normPath.match(/^\/hub\/sessions\/([^/]+)$/);
        if (m) {
          const store = hubStore(env);
          if (!store) return json({ error: "hub store not configured" }, 503);
          let videoId;
          try { videoId = decodeURIComponent(m[1]); } catch { return json({ error: "bad video id" }, 400); }
          if (request.method === "GET") {
            const row = await store
              .prepare(`SELECT * FROM sessions WHERE video_id = ?`)
              .bind(videoId)
              .first();
            if (!row) return json({ error: "not found" }, 404);
            const snubbed = await store
              .prepare(`SELECT video_id FROM ignored_videos WHERE video_id = ?`)
              .bind(videoId)
              .first();
            if (snubbed) return json({ error: "not found" }, 404);
            // The whole session this video is a part of (just itself
            // when untied): published, non-ignored parts in order.
            const mine = await store
              .prepare(`SELECT group_id FROM session_parts WHERE video_id = ?`)
              .bind(videoId).first();
            let members = [row], pendingParts = 0, groupId = "";
            if (mine) {
              const ps = await store
                .prepare(
                  `SELECT s.*, (s.video_id IS NOT NULL) AS published, p.video_id AS part_id
                   FROM session_parts p LEFT JOIN sessions s ON s.video_id = p.video_id
                   WHERE p.group_id = ?
                     AND p.video_id NOT IN (SELECT video_id FROM ignored_videos)
                   ORDER BY p.position ASC, p.video_id ASC`
                )
                .bind(mine.group_id).all();
              const pub = (ps.results || []).filter((p) => p.published);
              pendingParts = (ps.results || []).length - pub.length;
              if (pub.length) members = pub;
              if (members.length > 1 || pendingParts) groupId = mine.group_id;
            }
            const multi = members.length > 1;
            const head = members[0];
            const tag = (list, part) => list.map((x) =>
              x && typeof x === "object" && !Array.isArray(x) ? Object.assign({}, x, { part }) : x);
            let corrections = [], chapters = [], duration = 0;
            const writeups = [];
            members.forEach((m, i) => {
              corrections = corrections.concat(tag(parseList(m.corrections_json), i + 1));
              chapters = chapters.concat(tag(parseList(m.chapters_json), i + 1));
              duration += m.duration_seconds | 0;
              const w = String(m.writeup_md || "");
              if (!multi) writeups.push(w);
              else writeups.push(`**Part ${i + 1} — ${m.title || m.video_id}**\n\n` + (w.trim() || "_No write-up for this part yet._"));
            });
            return json({
              videoId: head.video_id,
              libraryId: head.library_id,
              title: head.title,
              lessonDate: head.lesson_date,
              hlsUrl: head.hls_url,
              mp4Url: head.mp4_url,
              writeupMd: writeups.join("\n\n"),
              corrections,
              chapters,
              glossary: parseObj(head.glossary_json),
              durationSeconds: duration,
              publishedAt: Math.max(...members.map((m) => m.published_at | 0)),
              groupId,
              pendingParts,
              parts: members.map((m) => ({
                videoId: m.video_id,
                libraryId: m.library_id,
                title: m.title,
                lessonDate: m.lesson_date,
                durationSeconds: m.duration_seconds | 0,
                hlsUrl: m.hls_url,
                mp4Url: m.mp4_url,
              })),
            });
          }
          if (request.method === "DELETE") {
            // Untie first: a failed untie leaves the session in place
            // instead of a session_parts row pointing at nothing.
            await untiePart(store, videoId);
            await store
              .prepare(`DELETE FROM sessions WHERE video_id = ?`)
              .bind(videoId)
              .run();
            return json({ deleted: true });
          }
          return json({ error: "method not allowed" }, 405);
        }
      }
      // Only / mints videos and proxies status/delete: any other
      // path 404s instead of falling into the trio below (a typo'd
      // client must never mint or delete a video by accident).
      if (normPath !== "/") return json({ error: "not found" }, 404);
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
        const r = await fetch(`${CLOUD_API}/library/${env.CLOUD_LIBRARY_ID}/videos/${encodeURIComponent(videoId)}`, {
          headers: { "AccessKey": env.CLOUD_API_KEY, "Accept": "application/json" },
        });
        let body;
        try { body = await r.json(); } catch (_) { body = { status: r.status, error: r.status === 404 ? "not found" : "empty response" }; }
        return json(body, r.status);
      }
      if (request.method === "DELETE") {
        const videoId = url.searchParams.get("videoId");
        if (!videoId) return json({ error: "videoId required" }, 400);
        const r = await fetch(`${CLOUD_API}/library/${env.CLOUD_LIBRARY_ID}/videos/${encodeURIComponent(videoId)}`, {
          method: "DELETE",
          headers: { "AccessKey": env.CLOUD_API_KEY, "Accept": "application/json" },
        });
        if (!r.ok && r.status !== 404) return json({ error: "cloud delete failed", status: r.status }, 502);
        return json({ deleted: true });
      }
      return json({ error: "method not allowed" }, 405);
    } catch (e) {
      return failed(e);
    }
  },
};

/* Ties ids onto ids[0]'s session, in order. A video already in
   another session brings that whole session along (its order kept);
   one already in the target stays where it is. Sequential statements
   (no batch) so the D1 stub and real D1 behave alike; the cron loop
   and the apps never tie the same session concurrently in practice,
   and a crash mid-way leaves every row in some valid group. */
async function tieParts(store, ids, now) {
  const groupOf = async (id) => {
    const r = await store.prepare(`SELECT group_id FROM session_parts WHERE video_id = ?`).bind(id).first();
    return r ? r.group_id : "";
  };
  const membersOf = async (g) => {
    const rs = await store
      .prepare(`SELECT video_id FROM session_parts WHERE group_id = ? ORDER BY position ASC, video_id ASC`)
      .bind(g).all();
    return (rs.results || []).map((r) => r.video_id);
  };
  let target = await groupOf(ids[0]);
  const ordered = target ? await membersOf(target) : [ids[0]];
  if (!target) target = "grp_" + crypto.randomUUID().replace(/-/g, "");
  for (const id of ids.slice(1)) {
    if (ordered.includes(id)) continue;
    const g = await groupOf(id);
    const bring = g && g !== target ? await membersOf(g) : [id];
    for (const v of bring) if (!ordered.includes(v)) ordered.push(v);
  }
  for (let i = 0; i < ordered.length; i++) {
    await store
      .prepare(
        `INSERT INTO session_parts (video_id, group_id, position, linked_at) VALUES (?, ?, ?, ?)
         ON CONFLICT(video_id) DO UPDATE SET group_id=excluded.group_id, position=excluded.position,
           linked_at=excluded.linked_at`
      )
      .bind(ordered[i], target, i, now).run();
  }
  return { groupId: target, parts: ordered };
}

/* Unties one video; a session left with a single part dissolves.
   Returns whether the video was tied at all. */
async function untiePart(store, videoId) {
  const r = await store.prepare(`SELECT group_id FROM session_parts WHERE video_id = ?`).bind(videoId).first();
  if (!r) return false;
  await store.prepare(`DELETE FROM session_parts WHERE video_id = ?`).bind(videoId).run();
  const left = await store
    .prepare(`SELECT COUNT(*) AS n FROM session_parts WHERE group_id = ?`).bind(r.group_id).first();
  if (left && (left.n | 0) <= 1)
    await store.prepare(`DELETE FROM session_parts WHERE group_id = ?`).bind(r.group_id).run();
  return true;
}

function hubStore(env) {
  return (env && env.DB) || null;
}

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => ("0" + b.toString(16)).slice(-2)).join("");
}
