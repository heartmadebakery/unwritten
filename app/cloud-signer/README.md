# Unwritten Craft — Cloud signer

A ~100-line Cloudflare Worker that holds the Stream library API key
so the recorder clients (web + Android) never ship it. The clients POST a
lesson title here, get back presigned TUS credentials, and upload
straight to the Stream library. Nothing else passes through this Worker
except status checks and deletes.

It accepts a *pool* of signer tokens (one per distributed build) instead
of a single token: each build carries a different token baked in at
build time, so a leaked build revokes alone without touching the rest.

Why bother? The vendor's own docs: the TUS signature must be generated where
the API key lives — *never expose your API key in client-side code.* The
recorders work without this Worker (paste the library key into the app
instead), but then the key lives on the device. This is the safer path
and takes five minutes once.

## Deploy

You need: a bunny.net account with a Stream library, and a free
Cloudflare account.

```sh
cd app/cloud-signer
# edit wrangler.toml: set CORS_ORIGIN to where the web recorder is served
bash mint-tokens.sh                    # one-time: creates gitignored tokens.txt (pool of 10)
npx wrangler deploy
npx wrangler secret put CLOUD_API_KEY  # library's AccessKey (Stream → library → API)
paste -sd, tokens.txt | npx wrangler secret put SIGNER_TOKENS  # the pool, never printed
```

`CLOUD_LIBRARY_ID` is set as a plain var in `wrangler.toml`. After deploy,
Wrangler prints the Worker URL (`https://unwritten-cloud-signer.<you>.workers.dev`).

## Connect the clients

Nothing to type: each build stamps in the signer URL and one token from
the pool (see `app/recorder/build.sh` and `app/android/build.sh`), and
Cloud saving is on by default. The Cloud panel / Cloud settings still
exist for overrides and for turning Cloud saving off.

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
- When tokens are set, every request must carry a matching
  `X-Signer-Token` header; the clients do this automatically.

Keep `CORS_ORIGIN` pinned to your recorder's origin in production — CORS
is not authentication, the token is.
