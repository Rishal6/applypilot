# Background Scheduling

ApplyPilot should run on the user's own desktop while they are away.

## Development Command

```bash
applypilot run --provider openai --connector linkedin-browser --interval-minutes 60
```

## macOS LaunchAgent Plan

The desktop app should install a LaunchAgent that runs:

```bash
applypilot run --provider openai --connector linkedin-browser --interval-minutes 60
```

The LaunchAgent should:

- start on login
- write logs to the local workspace
- stop when Away Mode is disabled
- respect the local automation policy

## Windows Task Scheduler Plan

The Windows installer should create a scheduled task that:

- starts on user login
- runs the local agent in the user's session
- does not run as a system service because browser automation needs the user's desktop session
- stops when Away Mode is disabled

## Important Detail

Browser automation must run in the user's desktop session. A cloud worker or system service cannot reliably control the user's authenticated LinkedIn browser.

