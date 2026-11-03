#!/usr/bin/env python3
"""Serve the web app over local HTTPS so phones get a secure context
(in-page camera/mic recording requires HTTPS or localhost).

Certs come from the project-local mkcert CA in ../../.certs/ (git-ignored):
  CAROOT=$PWD/.certs mkcert -install
  (cd .certs && mkcert -cert-file recorder.pem -key-file recorder-key.pem \
      localhost 127.0.0.1 <WSL_IP> <WINDOWS_LAN_IP>)
Install .certs/rootCA.pem on each device, then run:
  .venv/bin/python app/recorder/serve_https.py [--port 8443]
Regenerate the cert with the device-facing IP added whenever it changes.
Serves the built, token-stamped dist/ (bash app/recorder/build.sh) — the
same build as the plain-HTTP command; without a build it falls back to
the unstamped source and says so (Cloud upload then needs a pasted token).
"""
import argparse, http.server, os, ssl

HERE = os.path.dirname(os.path.abspath(__file__))
CERTS = os.path.join(HERE, "..", "..", ".certs")
DIST = os.path.join(HERE, "dist")
SITE = DIST if os.path.isdir(DIST) else HERE

ap = argparse.ArgumentParser(description="Serve the web app over HTTPS.")
ap.add_argument("--port", type=int, default=8443)
ap.add_argument("--cert", default=os.path.join(CERTS, "recorder.pem"))
ap.add_argument("--key", default=os.path.join(CERTS, "recorder-key.pem"))
args = ap.parse_args()

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(args.cert, args.key)
server = http.server.ThreadingHTTPServer(
    ("0.0.0.0", args.port),
    lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=SITE, **kw))
server.socket = ctx.wrap_socket(server.socket, server_side=True)
if SITE == HERE:
    print("No dist/ build: serving the unstamped source (Cloud upload "
          "needs a pasted token). Run bash app/recorder/build.sh first.")
print(f"Recorder HTTPS on https://0.0.0.0:{args.port}/ (cert: {args.cert}, serving {SITE})")
server.serve_forever()
