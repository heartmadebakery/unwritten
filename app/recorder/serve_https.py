#!/usr/bin/env python3
"""Serve the recorder over local HTTPS so phones get a secure context
(in-page camera/mic recording requires HTTPS or localhost).

Certs come from the project-local mkcert CA in ../../.certs/ (git-ignored):
  CAROOT=$PWD/.certs mkcert -install
  (cd .certs && mkcert -cert-file recorder.pem -key-file recorder-key.pem \
      localhost 127.0.0.1 <WSL_IP> <WINDOWS_LAN_IP>)
Install .certs/rootCA.pem on each device, then run:
  .venv/bin/python app/recorder/serve_https.py [--port 8443]
Regenerate the cert with the device-facing IP added whenever it changes.
"""
import argparse, http.server, os, ssl

HERE = os.path.dirname(os.path.abspath(__file__))
CERTS = os.path.join(HERE, "..", "..", ".certs")

ap = argparse.ArgumentParser(description="Serve the recorder over HTTPS.")
ap.add_argument("--port", type=int, default=8443)
ap.add_argument("--cert", default=os.path.join(CERTS, "recorder.pem"))
ap.add_argument("--key", default=os.path.join(CERTS, "recorder-key.pem"))
args = ap.parse_args()

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(args.cert, args.key)
server = http.server.ThreadingHTTPServer(
    ("0.0.0.0", args.port),
    lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=HERE, **kw))
server.socket = ctx.wrap_socket(server.socket, server_side=True)
print(f"Recorder HTTPS on https://0.0.0.0:{args.port}/ (cert: {args.cert})")
server.serve_forever()
