#!/usr/bin/env bash
# Set up Unwritten Craft on this machine (Ubuntu/WSL2, no sudo needed).
# Idempotent: safe to re-run. Everything lands in the project (.venv,
# pipeline/models) or ~/.local/bin.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

# uv manages the project venv (system python3-venv/ensurepip is absent here)
command -v uv >/dev/null || curl -fsSL https://astral.sh/uv/install.sh | sh
[ -d .venv ] || uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
uv pip install --python .venv/bin/python -r requirements-retired.txt

# ffmpeg/ffprobe as static binaries (no apt/sudo), built for this
# machine: an amd64 build cannot run on arm64 Linux, and there is no
# static Linux build that runs on macOS.
if ! command -v ffmpeg >/dev/null; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) FFARCH=amd64 ;;
    Linux-aarch64|Linux-arm64) FFARCH=arm64 ;;
    *) echo "ffmpeg not found, and no static build for $(uname -s)-$(uname -m) — install it (macOS: brew install ffmpeg), then re-run setup.sh." >&2
       exit 1 ;;
  esac
  FFTMP="$(mktemp -d)"
  (cd "$FFTMP" && curl -fsSL -o ffmpeg.tar.xz "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-$FFARCH-static.tar.xz" \
    && tar -xf ffmpeg.tar.xz && mkdir -p "$HOME/.local/bin" \
    && cp ffmpeg-*-"$FFARCH"-static/ffmpeg ffmpeg-*-"$FFARCH"-static/ffprobe "$HOME/.local/bin/")
  rm -rf "$FFTMP"
fi

# SAM ViT-B checkpoint (375 MB, git-ignored). Lands via .part + mv: an
# interrupted download must never pass the existence check as complete.
mkdir -p pipeline/models
SAM=pipeline/models/sam_vit_b_01ec64.pth
[ -f "$SAM" ] || { curl -fL -o "$SAM.part" \
  https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth && mv "$SAM.part" "$SAM"; }

# Android (optional): JDK 17 in ~/opt, SDK in ~/Android/Sdk (both user-local,
# env persisted in ~/.bashrc). Rebuild the app APK with:
#   cd app/android && bash build.sh    # needs SDK cmake bin on PATH for ninja

.venv/bin/python -m unittest discover -s tests
echo "OK. Run:  source .venv/bin/activate"
echo "Next: read docs/SETUP.md (secrets, token pool, service, builds)."
echo "Web app:  bash app/recorder/build.sh  # needs app/cloud-signer/tokens.txt"
echo "          .venv/bin/python -m http.server 8765 --directory app/recorder/dist  ->  http://localhost:8765"
echo "Pipeline: .venv/bin/python pipeline/run_pipeline.py <session_dir> <work_dir>"
