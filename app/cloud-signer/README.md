# Unwritten Craft — Cloud signer

A small Cloudflare Worker that holds the Stream library API key so the
app clients (web, Android, iOS) never ship it. The clients POST a
lesson title here, get back presigned TUS credentials, and upload
straight to the Stream library. The same Worker also serves status
checks and deletes, the pipeline's library-listing proxy, and the hub
store (D1) behind the in-app hub.

It accepts a *pool* of signer tokens (one per distributed build) instead
of a single token: each build carries a different token baked in at
build time, so a leaked build revokes alone without touching the rest.

Why bother? The vendor's own docs: the TUS signature must be generated where
the API key lives — *never expose your API key in client-side code.* The
apps work without this Worker (paste the library key into the app
instead), but then the key lives on the device — and direct mode has no
hub, since the hub lives here. This is the safer path
and takes five minutes once.

## Deploy

You need: a bunny.net account with a Stream library, and a free
Cloudflare account.

```sh
cd app/cloud-signer
# edit wrangler.toml: set CORS_ORIGIN to where the web app is served
bash mint-tokens.sh                    # one-time: creates gitignored tokens.txt (pool of 10)
npx wrangler deploy
npx wrangler secret put CLOUD_API_KEY  # library's AccessKey (Stream → library → API)
paste -sd, tokens.txt | npx wrangler secret put SIGNER_TOKENS  # the pool, never printed
```

Hub store (optional, powers the in-app hub, the URL fetch queue,
session parts, and the ignored-take badges): a D1 database behind the same worker.
Create it once, paste the printed id into `wrangler.toml`, run every
migration, redeploy. `--remote` matters: without it Wrangler
migrates a local dev copy and the deployed store never gets the
tables (the worker then answers 503 naming the missing file).

```sh
npx wrangler d1 create unwritten-hub
# database_id = "<printed>" in wrangler.toml
npx wrangler d1 execute unwritten-hub --remote --file migrations/0001_sessions.sql
npx wrangler d1 execute unwritten-hub --remote --file migrations/0002_fetch_jobs.sql
npx wrangler d1 execute unwritten-hub --remote --file migrations/0003_ignored.sql
npx wrangler d1 execute unwritten-hub --remote --file migrations/0004_duration.sql
npx wrangler d1 execute unwritten-hub --remote --file migrations/0005_parts.sql
npx wrangler deploy
```

An existing store applies just the files it is missing, then
redeploys. Apply a migration **before** deploying the worker that
reads it: the hub list reads `session_parts` (0005), so a new worker
on a store without it answers 503 naming the file until it is applied.

**Session parts** (0005): several videos tied into one overall
session — a lesson filmed in several takes, uploaded in pieces, or
fetched from more than one link. `POST /hub/parts {videoIds: [a, b,
…]}` ties b, … onto the end of a's session (a video already tied
elsewhere brings its whole session along, order kept); `DELETE
/hub/parts/<videoId>` unties one (a session left with one part
dissolves; deleting a hub session unties it too). A part may be a
video the pipeline has not published yet — the apps tie a take as
soon as its upload has an id — and the hub counts it as
`pendingParts` until it is published. `GET /hub/sessions` lists a
tied session once, under its first published part, with `partCount`,
`groupId`, `pendingParts` and the summed `durationSeconds`; `GET
/hub/sessions/<any part>` answers the whole session: one write-up
with a `**Part N — title**` heading per part, corrections and
chapters tagged with their `part`, and `parts` (each part's id,
title, length and streams) in order. A queued link continues a
session with `POST /fetch/jobs {url, joinTo}`; the pipeline reports
the fetched video's id on `/fetch/jobs/<id>/done` and the worker ties
it on. `node hub-check.mjs` drives all of it against real SQLite.

Then publish finished runs: `CLOUD_LIBRARY_ID=.. CLOUD_LIBRARY_KEY=..
CLOUD_CDN_HOSTNAME=.. HUB_SIGNER_URL=.. HUB_SIGNER_TOKEN=.. python3
pipeline/publish.py --work <work_dir>`. Without the binding the
`/hub/*` routes answer 503 and uploads keep working.

`CLOUD_LIBRARY_ID` is set as a plain var in `wrangler.toml`. After deploy,
Wrangler prints the Worker URL (`https://unwritten-cloud-signer.<you>.workers.dev`).

## Connect the clients

Nothing to type: each build stamps in the signer URL and one token from
the pool (see `app/recorder/build.sh`, `app/android/build.sh`, and
`app/ios/build.sh`), and Cloud saving is on by default. The Cloud panel
/ Cloud settings now only show those build values for debugging and
offer the on/off switch — there are no overrides to type.

## Revoking one build's token

Each build logs which pool slot it stamped (`token #N of 10`). To
revoke slot N: delete line N from a *copy* of `tokens.txt`, re-set the
secret from that copy, and redeploy. Builds carrying the other nine
tokens keep working. (The old single `SIGNER_TOKEN` secret still works
as a fallback if set.)

## Contract

- `POST /` JSON `{title}` (or `{title, videoId}` to re-sign an existing
  video so an interrupted upload can resume) →
  `{videoId, libraryId, signature, expire, embedUrl}`.
- `GET /?videoId=<guid>` → the Stream video object (clients poll `status`;
  4 = finished/playable, 5/6 = failed).
- `DELETE /?videoId=<guid>` → `{deleted: true}` (removes the cloud copy).
- `POST /hub/publish` JSON `{videoId, libraryId?, title?, lessonDate?,
  hlsUrl?, mp4Url?, writeupMd?, corrections?, chapters?, glossary?}` →
  `{published: videoId}` (upsert; run `node hub-check.mjs` to exercise
  these routes against real SQLite).
- `GET /hub/sessions` → newest-first session summaries;
  `GET /hub/sessions/<videoId>` → the full session record;
  `DELETE /hub/sessions/<videoId>` → `{deleted: true}`. Ignored
  videos are left out of both.
- `POST /hub/ignored` `{videoId, title?, reason?}` → `{ignored:
  videoId}`; `GET /hub/ignored` → the operator's set-asides;
  `DELETE /hub/ignored/<videoId>` → `{deleted: true}`.
- `POST /fetch/jobs` `{url}` → `{id, status}` queues a link for the
  pipeline; `GET /fetch/jobs?claim=1&by=<worker>[&includeFailed=1]`
  claims the oldest pending job (retries after it, least recently
  tried first); `POST /fetch/jobs/<id>/done|failed` closes it;
  `GET /fetch/jobs` lists the 50 newest.
- `GET /pipeline/videos?page=N` → the library listing, for the
  pipeline machine.
- Every request must carry an `X-Signer-Token` header matching a
  pool entry; the clients do this automatically. With no pool set
  the worker fails closed (500), never open.

Keep `CORS_ORIGIN` pinned to your app's origin in production — CORS
is not authentication, the token is.
