from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "nuitka"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ApplyPilot desktop and agent binaries with Nuitka.")
    parser.add_argument("--target", choices=["current", "macos", "windows"], default="current")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--skip-desktop", action="store_true")
    parser.add_argument("--sign-identity", default=os.environ.get("APPLYPILOT_MAC_SIGN_IDENTITY", ""))
    args = parser.parse_args()

    target = current_target() if args.target == "current" else args.target
    ensure_host_matches(target)
    ensure_nuitka()
    if args.clean:
        shutil.rmtree(BUILD, ignore_errors=True)
        shutil.rmtree(DIST, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    sync_desktop_web_assets()

    agent_name = "applypilot-agent.exe" if target == "windows" else "applypilot-agent"
    agent = DIST / agent_name if args.skip_agent else build_agent(target)
    if not agent.exists():
        raise SystemExit(f"Agent artifact not found: {agent}")
    if args.skip_desktop:
        desktop = existing_desktop_artifact(target)
    else:
        desktop = build_desktop(target, args.sign_identity)
    if target == "macos":
        desktop = normalize_macos_app_name(desktop)
        bundle_agent_into_macos_app(desktop, agent)
        sign_macos_bundle(desktop, args.sign_identity)
        create_macos_dmg(desktop)

    print(f"Desktop artifact: {desktop}")
    print(f"Agent artifact: {agent}")
    return 0


def build_agent(target: str) -> Path:
    output_name = "applypilot-agent.exe" if target == "windows" else "applypilot-agent"
    command = common_command() + [
        "--mode=onefile",
        f"--output-filename={output_name}",
        "--include-module=applypilot.working_agent.auto_apply_chrome",
        "--include-module=applypilot.working_agent.auto_apply_naukri",
        "--include-module=applypilot.working_agent.lead_hunter",
        "--output-dir=" + str(DIST),
        str(ROOT / "packaging" / "agent_launcher.py"),
    ]
    if target == "windows":
        command.insert(-1, "--windows-console-mode=disable")
    run(command)
    return DIST / output_name


def build_desktop(target: str, sign_identity: str) -> Path:
    command = common_command() + [
        "--include-package-data=applypilot",
        "--output-dir=" + str(DIST),
        "--product-name=ApplyPilot",
        "--file-description=ApplyPilot Desktop Agent",
        "--company-name=ApplyPilot",
        "--product-version=0.1.0",
        "--file-version=0.1.0",
    ]
    if target == "macos":
        command.extend([
            "--mode=app",
            "--macos-app-name=ApplyPilot",
            "--macos-app-version=0.1.0",
        ])
        if sign_identity:
            command.extend([
                f"--macos-sign-identity={sign_identity}",
            ])
        artifact = DIST / "desktop_launcher.app"
    else:
        command.extend([
            "--mode=onefile",
            "--output-filename=ApplyPilot.exe",
            "--windows-console-mode=disable",
        ])
        artifact = DIST / "ApplyPilot.exe"
    command.append(str(ROOT / "packaging" / "desktop_launcher.py"))
    run(command)
    return artifact


def sync_desktop_web_assets() -> None:
    source = ROOT / "apps" / "web"
    destination = ROOT / "src" / "applypilot" / "desktop_web"
    if not source.exists():
        raise RuntimeError(f"Desktop web source not found: {source}")
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("data"),
    )


def common_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--assume-yes-for-downloads",
        "--deployment",
        "--remove-output",
        "--report=" + str(BUILD / "compilation-report.xml"),
    ]


def bundle_agent_into_macos_app(app: Path, agent: Path) -> None:
    destination = app / "Contents" / "MacOS" / "applypilot-agent"
    if not app.exists():
        raise RuntimeError(f"macOS app bundle not found: {app}")
    shutil.copy2(agent, destination)
    destination.chmod(0o755)


def normalize_macos_app_name(app: Path) -> Path:
    destination = DIST / "ApplyPilot.app"
    if app == destination:
        return destination
    if destination.exists():
        shutil.rmtree(destination)
    app.rename(destination)
    return destination


def create_macos_dmg(app: Path) -> Path:
    dmg = DIST / "ApplyPilot.dmg"
    if dmg.exists():
        dmg.unlink()
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "ApplyPilot",
            "-srcfolder",
            str(app),
            "-ov",
            "-format",
            "UDZO",
            str(dmg),
        ],
        check=True,
    )
    return dmg


def sign_macos_bundle(app: Path, identity: str) -> None:
    signer = identity or "-"
    agent = app / "Contents" / "MacOS" / "applypilot-agent"
    base = ["codesign", "--force", "--sign", signer]
    if identity:
        base.extend(["--options", "runtime", "--timestamp"])
    subprocess.run([*base, str(agent)], check=True)
    subprocess.run([*base, "--deep", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)


def existing_desktop_artifact(target: str) -> Path:
    if target == "windows":
        artifact = DIST / "ApplyPilot.exe"
    else:
        artifact = DIST / "ApplyPilot.app"
        if not artifact.exists():
            artifact = DIST / "desktop_launcher.app"
    if not artifact.exists():
        raise SystemExit(f"Desktop artifact not found: {artifact}")
    return artifact


def current_target() -> str:
    return "windows" if platform.system() == "Windows" else "macos"


def ensure_host_matches(target: str) -> None:
    host = current_target()
    if host != target:
        raise SystemExit(f"Build {target} on a {target} host. Nuitka does not cross-compile this product.")


def ensure_nuitka() -> None:
    try:
        __import__("nuitka")
    except ImportError as exc:
        raise SystemExit("Install packaging dependencies with: pip install -e '.[package]'") from exc


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
