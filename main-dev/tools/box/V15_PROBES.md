# V15 probe training on the box

1. Sync main-dev to the box (edit on Windows, deploy; never edit on the GX10).
2. Check that `~/council/tap-build/actdump` exists and is executable. The script refuses to start without it.
3. Run all 11 models in order: `bash ~/council/main-dev/tools/box/train_probes.sh`
4. Or run some: `bash ~/council/main-dev/tools/box/train_probes.sh qwen3-14b falcon3-10b` (registry ids, not Ollama tags).
5. First, unload every model on Ollama port 11435 (done by the script). Nothing else is stopped.
6. Per-model log: `~/council/logs/probe_<id>.log`. Summary: `~/council/logs/probe_summary.txt`.
7. Each summary line: id, exit code (rc=1 means error), seconds, and the verdict with held-out AUROC.
8. A failing model does not stop the loop. The script exits 1 if any model failed.
9. Duration: UNKNOWN, must be measured. Time one model first, then multiply by the count.
10. Ids: gpt-oss-20b qwen35-9b phi4-14b ministral3-14b granite41-8b qwen3-14b deepseek-r1-14b phi4-reasoning mistral-small32 falcon3-10b gemma4-12b. Excluded: llama32-vision (purged), gemma4-12b-q4.
