# Auto-Submit

Auto-submit means the local agent clicks the final **Submit application** button.

This is a required paid-product capability, especially for users who want the agent to run daily without reviewing every form.

## Modes

`review-only`

- imports jobs
- scores jobs
- creates review queue
- does not open or fill applications

`fill-only`

- opens jobs locally
- fills forms
- uploads resume if configured
- stops before final submit

`auto-submit`

- opens jobs locally
- fills forms
- submits the final application when policy passes
- logs the outcome

## Required Policy Checks

Before submitting:

- job score must be at least `min_score_to_submit`
- daily application count must be below `max_applications_per_day`
- connector must confirm it is on the expected submit step
- job must not be already applied/skipped
- application data must be logged

## CLI

```bash
applypilot policy
applypilot policy --mode fill-only --daily-limit 15 --min-score 70
applypilot policy --mode auto-submit --daily-limit 25 --min-score 70
applypilot run --provider rules --connector linkedin-browser --interval-minutes 60
```

## Away Mode

Away mode is the local desktop agent running while the user is not sitting at the machine.

```bash
pip install -e '.[desktop]'
applypilot policy --mode auto-submit --daily-limit 25 --min-score 70
applypilot run --provider openai --connector linkedin-browser --interval-minutes 60
```

The agent cycle:

1. loads queued jobs
2. scores or re-scores jobs
3. filters jobs by policy
4. opens or focuses LinkedIn in the user's existing logged-in Chrome profile
5. fills Easy Apply forms
6. clicks final submit when policy allows
7. writes application history

## Product UX

Desktop users should see:

- current mode
- today's application count
- pause/stop control
- current job being processed
- final log after each submitted application

MCP/ChatGPT/Codex users should need explicit approval before enabling or changing auto-submit mode.
