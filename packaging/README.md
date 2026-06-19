# Desktop Builds

Install build dependencies:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
pip install -e '.[desktop,package]'
```

Build for the current operating system:

```bash
python3 packaging/build_desktop.py --clean
```

Artifacts are written to `dist/`.

## macOS

The build creates `ApplyPilot.app`, a DMG, and an `applypilot-agent` sidecar inside the app bundle.

For signed/notarized builds:

```bash
APPLYPILOT_MAC_SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)" \
python3 packaging/build_desktop.py --clean --sign-identity "$APPLYPILOT_MAC_SIGN_IDENTITY"
```

Apple credentials and notarization setup must be configured on the build Mac.

## Windows

Run the same command on Windows. It creates:

- `ApplyPilot.exe`
- `applypilot-agent.exe`

Sign both executables with your organization’s Windows code-signing certificate before distribution.
