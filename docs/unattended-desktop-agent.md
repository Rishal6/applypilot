# Unattended Desktop Agent

The core product should work while the user is away.

This means the agent runs locally on the user's own desktop, keeps the browser session local, scores jobs automatically, and submits applications when the user's policy allows it.

## Command

```bash
applypilot policy --mode auto-submit --daily-limit 25 --min-score 70
applypilot run --provider rules --connector linkedin-browser --interval-minutes 60
```

With a cloud model:

```bash
OPENAI_API_KEY=... OPENAI_MODEL=... \
applypilot run --provider openai --connector linkedin-browser --interval-minutes 60
```

With local Ollama:

```bash
OLLAMA_MODEL=llama3.1 \
applypilot run --provider ollama --connector linkedin-browser --interval-minutes 60
```

## What Happens Each Cycle

1. load local job queue
2. score jobs
3. skip jobs already completed
4. enforce minimum score
5. enforce Easy Apply requirement
6. enforce daily application limit
7. open or focus LinkedIn in the user's existing logged-in Chrome profile
8. fill application
9. submit if mode is `auto-submit`
10. log result to `.applypilot/queues/applications.json`

## Local Browser Session

On macOS, the connector uses the user's normal Google Chrome profile. The user should already be logged into LinkedIn in Chrome before starting Away Mode.

## Desktop Product UX

The desktop app should expose this as "Away Mode":

- toggle on/off
- interval selector
- provider selector
- daily cap
- minimum submit score
- application count today
- last run status
- pause immediately

## SaaS Role

SaaS should configure and monitor away mode, not run the LinkedIn session itself.

The SaaS can store:

- license status
- preferences
- high-level application stats
- optional encrypted sync

The SaaS should not need:

- LinkedIn password
- LinkedIn cookies
- raw browser session
