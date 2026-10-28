/* Unwritten Craft — Bunny Stream signer (Cloudflare Worker).
 *
 * Holds the Bunny Stream library API key as a Worker secret so neither
 * recorder client ever ships it. Two endpoints, both JSON:
 *
 *   POST /            {title, videoId?} -> {videoId, libraryId, signature,
 *                                          expire, embedUrl}
 *                     Creates the video object (or re-signs videoId so an
 *                     interrupted TUS upload can resume) and returns
 *                     presigned TUS credentials:
 *                     signature = SHA256(libraryId + apiKey + expire + videoId)
 *
 *   GET  /?videoId=X  -> the Bunny video object (status polling)
 *
 * Env: BUNNY_LIBRARY_ID (var), BUNNY_API_KEY (secret).
 * Optional: SIGNER_TOKEN (secret) — when set, callers must send it as
 * X-Signer-Token. CORS_ORIGIN (var) — default "*"; set to your recorder
 * origin before real use. Bunny's docs warn that an open create route
 * lets anyone fill your library; the token + origin are the minimum.
 */

const BUNNY_API = "https://video.bunnycdn.com";

export default {
  async fetch(request, env) {
    const origin = env.CORS_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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
    if (env.SIGNER_TOKEN && request.headers.get("X-Signer-Token") !== env.SIGNER_TOKEN) {
      return json({ error: "unauthorized" }, 401);
    }
    if (!env.BUNNY_LIBRARY_ID || !env.BUNNY_API_KEY) {
      return json({ error: "signer not configured (BUNNY_LIBRARY_ID / BUNNY_API_KEY)" }, 500);
    }
    const url = new URL(request.url);
    try {
      if (request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        let videoId = body.videoId || null;
        if (!videoId) {
          const create = await fetch(`${BUNNY_API}/library/${env.BUNNY_LIBRARY_ID}/videos`, {
            method: "POST",
            headers: {
              "AccessKey": env.BUNNY_API_KEY,
              "Accept": "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ title: body.title || "Untitled lesson" }),
          });
          if (!create.ok) return json({ error: "bunny create failed", status: create.status }, 502);
          const video = await create.json();
          videoId = video.guid || video.videoId || video.id;
          if (!videoId) return json({ error: "bunny create returned no id" }, 502);
        }
        const expire = Math.floor(Date.now() / 1000) + 86400;
        const signature = await sha256Hex(`${env.BUNNY_LIBRARY_ID}${env.BUNNY_API_KEY}${expire}${videoId}`);
        return json({
          videoId,
          libraryId: env.BUNNY_LIBRARY_ID,
          signature,
          expire,
          embedUrl: `https://player.mediadelivery.net/embed/${env.BUNNY_LIBRARY_ID}/${videoId}`,
        });
      }
      if (request.method === "GET") {
        const videoId = url.searchParams.get("videoId");
        if (!videoId) return json({ error: "videoId required" }, 400);
        const r = await fetch(`${BUNNY_API}/library/${env.BUNNY_LIBRARY_ID}/videos/${videoId}`, {
          headers: { "AccessKey": env.BUNNY_API_KEY, "Accept": "application/json" },
        });
        return json(await r.json(), r.status);
      }
      return json({ error: "method not allowed" }, 405);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => ("0" + b.toString(16)).slice(-2)).join("");
}
