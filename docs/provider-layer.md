# Provider Layer

ApplyPilot is BYOK by design. Users should be able to use paid cloud models, cheap API gateways, or local models.

## Implemented In This MVP

### `rules`

No key. No network. Good for first-pass filtering and free users.

```bash
applypilot score --provider rules
```

### `ollama`

Local model through Ollama.

```bash
OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=llama3.1 applypilot score --provider ollama
```

### `openai`

OpenAI-compatible chat completions endpoint.

```bash
OPENAI_API_KEY=... OPENAI_MODEL=... applypilot score --provider openai
```

For OpenAI-compatible gateways:

```bash
OPENAI_BASE_URL=https://your-gateway.example.com OPENAI_API_KEY=... OPENAI_MODEL=... applypilot score --provider openai
```

### `groq`

Groq chat completions using `GROQ_API_KEY`.

```bash
GROQ_API_KEY=... GROQ_MODEL=llama-3.1-8b-instant applypilot score --provider groq
```

### `gemini`

Gemini API using `GEMINI_API_KEY`.

```bash
GEMINI_API_KEY=... GEMINI_MODEL=gemini-1.5-flash applypilot score --provider gemini
```

### `managed_preview`

No customer key. Rules-backed managed-plan preview until hosted model routing is live.

```bash
applypilot score --provider managed_preview
```

## Next Providers

- Anthropic / Claude
- Hugging Face Inference Endpoints
- managed ApplyPilot SaaS provider

## Contract

Every provider must return the same fields:

- score
- decision: `shortlist`, `review`, or `reject`
- reason
- matching terms
- missing terms

This keeps the CLI, desktop app, MCP server, and SaaS dashboard independent from provider-specific APIs.
