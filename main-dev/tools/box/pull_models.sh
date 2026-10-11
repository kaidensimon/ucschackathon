#!/usr/bin/env bash
# Download the eight models we recommend, through Ollama (about 82 GB in total).
# The council is not tied to them: it seats 2 to 6 of whatever chat models Ollama has downloaded
# (python -m council.cli models lists what it found). These eight are the ones tuned and measured
# on the ASUS Ascent GX10; when they are installed the router prefers them.
# The council does not serve them with Ollama: llama.cpp loads the files Ollama downloaded.
# Usage: bash tools/box/pull_models.sh
TAGS=(
  "gpt-oss:20b"                 # OpenAI, 13 GB
  "qwen3.5:9b-q8_0"             # Alibaba, 10 GB
  "qwen3:14b"                   # Alibaba, 9.3 GB
  "phi4:14b"                    # Microsoft, 9.1 GB
  "granite4.1:8b-q8_0"          # IBM, 9.3 GB
  "deepseek-r1:14b"             # DeepSeek, 9.0 GB
  "falcon3:10b-instruct-q8_0"   # TII, 10 GB
  "gemma4:12b-it-q8_0"          # Google, 12 GB
)
command -v ollama >/dev/null || { echo "Ollama is not installed: https://ollama.com/download"; exit 1; }
failed=0
for tag in "${TAGS[@]}"; do
  echo "== $tag =="
  ollama pull "$tag" || { echo "FAILED: $tag"; failed=$((failed + 1)); }
done
echo
ollama list
[ "$failed" = 0 ] && echo "all eight models are here" || echo "$failed model(s) did not download"
