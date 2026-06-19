# ApplyPilot Web Dashboard

SaaS control plane for the local ApplyPilot desktop agent. It can read local JSON during development or authenticated SaaS data from the ApplyPilot API.

The hosted public page starts in private local mode and must not ship with generated `apps/web/data/dashboard.json`. That file is local-only and ignored by Git/Docker so old candidate or agent history is not exposed to new users.

The main experience is chat-first:

- learns the candidate's target role, background, skills, and location conversationally
- stores the private career profile in the browser
- creates and exports a truthful resume draft without inventing experience
- explains scored job matches and synced activity
- prepares application runs, then hands execution to the local desktop agent for confirmation

For the functional local product, run `applypilot-desktop` and open
`http://127.0.0.1:8765`. Opening `index.html` directly is preview-only because
`file://` pages cannot access the local profile, resume, scoring, or agent APIs.

Generate fresh data:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
PYTHONPATH=src python3 -m applypilot --workspace . dashboard
```

Serve locally:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot/apps/web
python3 -m http.server 4173
```

Serve through the SaaS API:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
PYTHONPATH=src python3 -m applypilot --workspace . serve --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787`, then use Connect with the API endpoint and license/device token.

For first-time customer testing in the same browser, open the hosted page with `?fresh=1`:

```text
https://YOUR_RENDER_SERVICE.onrender.com/?fresh=1
```

This clears ApplyPilot browser-local profile, chat, and connection state for that origin.
