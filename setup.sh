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
uv pip install --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchvision
uv pip install --python .venv/bin/python faster-whisper segment-anything Pillow numpy

# ffmpeg/ffprobe as static binaries (no apt/sudo)
if ! command -v ffmpeg >/dev/null; then
  (cd /tmp && curl -fsSL -o ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    && tar -xf ffmpeg.tar.xz && cp ffmpeg-*-amd64-static/ffmpeg ffmpeg-*-amd64-static/ffprobe "$HOME/.local/bin/")
fi

# SAM ViT-B checkpoint (375 MB, git-ignored)
mkdir -p pipeline/models
[ -f pipeline/models/sam_vit_b_01ec64.pth ] || curl -L -o pipeline/models/sam_vit_b_01ec64.pth \
  https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth

# Android (optional): JDK 17 in ~/opt, SDK in ~/Android/Sdk (both user-local,
# env persisted in ~/.bashrc). Rebuild the recorder APK with:
#   cd app/android && bash build.sh    # needs SDK cmake bin on PATH for ninja

.venv/bin/python -m unittest discover -s tests
echo "OK. Run:  source .venv/bin/activate"
echo "Recorder: .venv/bin/python -m http.server 8765 --directory app/recorder  ->  http://localhost:8765"
echo "Pipeline: .venv/bin/python pipeline/run_pipeline.py <session_dir> <work_dir>"
