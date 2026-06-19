# ApplyPilot Desktop

The desktop product is implemented in:

- `src/applypilot/desktop.py`: localhost control API and agent process controller
- `src/applypilot/desktop_web/`: desktop control-center UI
- `packaging/build_desktop.py`: Nuitka builds for macOS and Windows

Run from source:

```bash
cd /Users/rishal/Desktop/bed_rock/applypilot
pip install -e '.[desktop]'
applypilot-desktop
```

The app opens `http://127.0.0.1:8765` and provides:

- SaaS license activation
- policy visibility
- LinkedIn/Naukri/Lead Hunter workflow selection
- explicit auto-submit confirmation
- start and stop controls
- activity logs
- SaaS dashboard sync

Build compiled artifacts:

```bash
pip install -e '.[desktop,package]'
python3 packaging/build_desktop.py --clean
```
