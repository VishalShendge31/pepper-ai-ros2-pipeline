#!/usr/bin/env bash
set -euo pipefail

# Virtualenv-based Spark-TTS setup for Pepper custom TTS.
# No conda is used.
#
# Default layout:
#   ~/pepper_ws/custom_tts/Spark-TTS
#   ~/pepper_ws/custom_tts/Spark-TTS-0.5B
#   ~/pepper_ws/custom_tts/spark_tts_finetune
#   ~/pepper_ws/sparktts_venv
#
# To install into your already-active venv instead:
#   USE_ACTIVE_VENV=1 bash ~/pepper_ws/src/pepper_custom_tts/scripts/install_spark_tts_env.sh
#
# To select a specific venv:
#   VENV_DIR=~/pepper_venv bash ~/pepper_ws/src/pepper_custom_tts/scripts/install_spark_tts_env.sh

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/pepper_ws}"
CUSTOM_TTS_DIR="${CUSTOM_TTS_DIR:-$WORKSPACE_ROOT/custom_tts}"
VENV_DIR="${VENV_DIR:-$WORKSPACE_ROOT/sparktts_venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SPARK_REPO_URL="https://github.com/SparkAudio/Spark-TTS.git"
SPARK_REPO_DIR="$CUSTOM_TTS_DIR/Spark-TTS"
SPARK_BASE_DIR="$CUSTOM_TTS_DIR/Spark-TTS-0.5B"
FINETUNED_MODEL_DIR="$CUSTOM_TTS_DIR/spark_tts_finetune"

mkdir -p "$CUSTOM_TTS_DIR"
cd "$CUSTOM_TTS_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is not installed. Run: sudo apt install -y git"
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN is not available. Install Python first."
  exit 1
fi

if [ "${USE_ACTIVE_VENV:-0}" = "1" ]; then
  if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "ERROR: USE_ACTIVE_VENV=1 was set, but no virtual environment is active."
    echo "Run: source ~/pepper_venv/bin/activate"
    exit 1
  fi
  VENV_DIR="$VIRTUAL_ENV"
  echo "Using active virtual environment: $VENV_DIR"
else
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR" || {
      echo "ERROR: Could not create virtual environment."
      echo "Install venv support first: sudo apt install -y python3-venv"
      exit 1
    }
  else
    echo "Virtual environment already exists: $VENV_DIR"
  fi
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Python used for Spark-TTS: $(which python3)"
python3 --version

if [ ! -d "$SPARK_REPO_DIR/.git" ]; then
  git clone "$SPARK_REPO_URL" "$SPARK_REPO_DIR"
else
  echo "Spark-TTS repo already exists: $SPARK_REPO_DIR"
fi

python3 -m pip install --upgrade pip setuptools wheel

# Spark-TTS dependencies. The official requirements file is used first.
python3 -m pip install -r "$SPARK_REPO_DIR/requirements.txt"

# Extra runtime dependencies used by this ROS package/server.
# This package uses the exact Hugging Face model-card path with Unsloth FastLanguageModel.
python3 -m pip install \
  unsloth \
  transformers \
  soundfile \
  huggingface_hub \
  accelerate \
  safetensors \
  "numpy<2"

python3 - <<PY
from huggingface_hub import snapshot_download

snapshot_download(
    "SparkAudio/Spark-TTS-0.5B",
    local_dir="$SPARK_BASE_DIR",
)

snapshot_download(
    "Vishalshendge3198/spark_tts_finetune",
    local_dir="$FINETUNED_MODEL_DIR",
)
PY

echo "Done."
echo "Spark repo:       $SPARK_REPO_DIR"
echo "Base model dir:   $SPARK_BASE_DIR"
echo "Fine-tuned dir:   $FINETUNED_MODEL_DIR"
echo "Virtualenv:       $VENV_DIR"
echo "Python:           $VENV_DIR/bin/python3"
