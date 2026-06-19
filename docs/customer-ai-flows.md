# Customer AI setup flows

ApplyPilot supports three customer AI paths in the MVP.

## 1. Local model: Ollama

Use this when a customer wants privacy and no per-token API bill.

Customer steps:

```bash
brew install ollama
ollama pull llama3.1
applypilot-desktop
```

Inside the desktop app:

1. open **AI setup**;
2. choose **Ollama — local model**;
3. keep base URL `http://localhost:11434`;
4. choose model `llama3.1` or another local model;
5. save and score jobs.

Data behavior:

- profile, jobs, and prompts stay on the customer machine;
- no provider API key is needed;
- ApplyPilot SaaS only receives sync/license data if the user activates and syncs.

## 2. Bring your own API key

Use this when a customer already has provider credits.

Supported desktop providers:

- OpenAI-compatible API
- Groq
- Gemini
- Auto BYOK fallback

Customer steps:

1. open `applypilot-desktop`;
2. open **AI setup**;
3. choose the provider;
4. paste API key and model;
5. save.

Keys are saved locally in:

```text
.applypilot/provider.env
```

The desktop API redacts key values in status responses. The SaaS server does not need or receive these BYOK keys.

## 3. ApplyPilot managed preview

Use this when a customer chooses the managed plan and does not want to bring a key.

Current MVP behavior:

- no customer key is required;
- the provider is available as `managed_preview`;
- scoring is rules-backed and labelled as managed preview.

Production gap:

- true hosted model routing behind license checks still needs to be implemented before promising managed AI credits at scale.

## How to test

Rules/no-key:

```bash
applypilot score --provider rules
```

Ollama/local:

```bash
OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=llama3.1 applypilot score --provider ollama
```

OpenAI-compatible:

```bash
OPENAI_API_KEY=... OPENAI_MODEL=gpt-4o-mini applypilot score --provider openai
```

Groq:

```bash
GROQ_API_KEY=... GROQ_MODEL=llama-3.1-8b-instant applypilot score --provider groq
```

Gemini:

```bash
GEMINI_API_KEY=... GEMINI_MODEL=gemini-1.5-flash applypilot score --provider gemini
```

Managed preview:

```bash
applypilot score --provider managed_preview
```
