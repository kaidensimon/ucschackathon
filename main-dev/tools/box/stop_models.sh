#!/bin/bash
# Stop leftover model servers: llama-server processes the council started (ports 181xx),
# and every model loaded in both Ollama instances (11434 shared, 11435 council).
set -u
echo "llama-server before: $(pgrep -fc '[l]lama-server.*--port 181' || true)"
pkill -f "[l]lama-server.*--port 181" || echo "no council llama-server running"
sleep 2
echo "llama-server after: $(pgrep -fc '[l]lama-server.*--port 181' || true)"
for port in 11434 11435; do
  url="http://127.0.0.1:$port"
  if ! curl -s -m 5 "$url/api/version" > /dev/null; then echo "ollama $port: not answering"; continue; fi
  names=$(curl -s -m 10 "$url/api/ps" | python3 -c "import sys,json
try:
    for m in json.load(sys.stdin).get('models', []): print(m.get('name') or m.get('model'))
except Exception:
    pass")
  if [ -z "$names" ]; then echo "ollama $port: nothing loaded"; continue; fi
  while IFS= read -r name; do
    curl -s -m 30 "$url/api/generate" -d "{\"model\":\"$name\",\"keep_alive\":0}" > /dev/null
    echo "ollama $port: unloaded $name"
  done <<< "$names"
done
