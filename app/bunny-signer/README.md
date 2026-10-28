# Unwritten Craft — Bunny signer

A ~100-line Cloudflare Worker that holds the Bunny Stream library API key
so the recorder clients (web + Android) never ship it. The clients POST a
lesson title here, get back presigned Bunny TUS credentials, and upload
straight to Bunny. Nothing else passes through this Worker.

Why bother? Bunny's own docs: the TUS signature must be generated where
the API key lives — *never expose your API key in client-side code.* The
recorders work without this Worker (paste the library key into the app
instead), but then the key lives on the device. This is the safer path
and takes five minutes once.

## Deploy

You need: a bunny.net account with a Stream library, and a free
Cloudflare account.

```sh
cd app/bunny-signer
# edit wrangler.toml: set CORS_ORIGIN to where the web recorder is served
npx wrangler deploy
npx wrangler secret put BUNNY_API_KEY     # library's AccessKey (Stream → library → API)
npx wrangler secret put SIGNER_TOKEN      # optional but recommended: any long random string
```

`BUNNY_LIBRARY_ID` is set as a plain var in `wrangler.toml`. After deploy,
Wrangler prints the Worker URL (`https://unwritten-bunny-signer.<you>.workers.dev`).

## Connect the clients

- Web recorder: ☁️ Bunny panel → paste the Worker URL (and the signer
  token, if you set one). Leave the library ID / API key fields empty.
- Android app: Bunny settings → same URL + token.

## Contract

- `POST /` JSON `{title}` (or `{title, videoId}` to re-sign an existing
  video so an interrupted upload can resume) →
  `{videoId, libraryId, signature, expire, embedUrl}`.
- `GET /?videoId=<guid>` → the Bunny video object (clients poll `status`;
  4 = finished/playable, 5/6 = failed).
- When `SIGNER_TOKEN` is set, every request must carry
  `X-Signer-Token: <token>`; the clients do this automatically.

Keep `CORS_ORIGIN` pinned to your recorder's origin in production — CORS
is not authentication, the token is.
