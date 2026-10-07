# Local AI model

JayAI uses Ollama on the same machine where its API runs. Planning is local and does not require an OpenAI API key or paid model API. The model does not execute tools; JayAI validates its proposed JSON action against a fixed read-only allowlist. A plan must be reviewed and approved by exact digest before an available PC check runs.

## Supported model IDs

- `qwen2.5:0.5b` — recommended for this setup; Windows PC produced a valid plan with it after `qwen2.5:3b` timed out.
- `qwen2.5:1.5b`
- `qwen2.5:3b` — default planner fallback when `JAYAI_LOCAL_MODEL` is not set in direct/manual launches; may be slow on lower-powered hardware.

Install a model from the same machine that runs JayAI:

```powershell
ollama pull qwen2.5:0.5b
ollama list
```

On Chromebook Linux, install Ollama using its official Linux instructions and check `free -h` and `df -h ~` before downloading models. The 0.5b model is the only recommended option for a constrained 2.7 GiB RAM / 5 GiB disk container.

The standalone launchers select `qwen2.5:0.5b` by default and honor `JAYAI_LOCAL_MODEL` when set. The API uses `http://127.0.0.1:11434` and `trust_env=False`, unless `JAYAI_OLLAMA_ENDPOINT` is set to an explicitly managed forwarded endpoint. A small model can still return invalid structured output; verify a live plan on the target device.

## Troubleshooting

- `Local model unavailable`: start Ollama on the API host.
- `Local model missing`: pull the configured exact model ID.
- `ReadTimeout`: use the smaller installed model and ensure the machine is not memory constrained.
- `Local model request failed or returned invalid data`: inspect the chained error privately; do not paste dashboard keys or credentials.

For Windows-to-Chromebook model forwarding, see `STANDALONE.md`. This model tunnel uses destination `127.0.0.1:11434`; the separate companion check uses `127.0.0.1:8765`.
