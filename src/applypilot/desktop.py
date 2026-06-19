import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .career import load_career_profile, resume_markdown, save_career_profile
from .config import workspace_path, write_default_workspace
from .dashboard import build_dashboard_data
from .policy import load_policy, update_policy
from .saas_client import DEFAULT_ENDPOINT, activate_device, fetch_me, load_auth, save_auth, sync_workspace
from .scoring import score_jobs
from .search_plan import build_search_plan
from .storage import Store


class DesktopController:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.process: subprocess.Popen[str] | None = None
        self.started_at = ""
        self.mode = ""
        self.exit_code: int | None = None
        self.logs: deque[str] = deque(maxlen=250)
        self.lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            if self.process is not None and not running and self.exit_code is None:
                self.exit_code = self.process.returncode
            auth = load_auth(self.workspace)
            policy = load_policy(self.workspace)
            return {
                "running": running,
                "mode": self.mode,
                "started_at": self.started_at,
                "exit_code": self.exit_code,
                "logs": list(self.logs)[-80:],
                "policy": policy.to_dict(),
                "connected": bool(auth.get("device_token")),
                "customer": auth.get("customer") or {},
                "endpoint": auth.get("endpoint") or DEFAULT_ENDPOINT,
            }

    def activate(self, endpoint: str, license_key: str, device_id: str, device_name: str) -> dict[str, Any]:
        result = activate_device(endpoint, license_key, device_id=device_id, device_name=device_name)
        auth = {
            "endpoint": endpoint,
            "device_token": result["device_token"],
            "device": result["device"],
            "customer": result["customer"],
            "license": result["license"],
        }
        save_auth(self.workspace, auth)
        self.logs.append(f"Activated {result['device']['device_id']}")
        return {
            "device": result["device"],
            "customer": result["customer"],
            "license": result["license"],
        }

    def account(self) -> dict[str, Any]:
        auth = load_auth(self.workspace)
        token = str(auth.get("device_token") or "")
        if not token:
            raise PermissionError("Activate this desktop first.")
        return fetch_me(str(auth.get("endpoint") or DEFAULT_ENDPOINT), token)

    def career_profile(self) -> dict[str, Any]:
        return load_career_profile(self.workspace)

    def save_career_profile(self, profile: dict[str, Any], rescore: bool = False) -> dict[str, Any]:
        saved = save_career_profile(self.workspace, profile)
        self.logs.append("Updated candidate profile")
        result: dict[str, Any] = {"profile": saved, "scored": 0}
        if rescore:
            result["scored"] = self.score("rules")["scored"]
        return result

    def resume(self) -> str:
        return resume_markdown(self.career_profile())

    def dashboard(self) -> dict[str, Any]:
        data = build_dashboard_data(self.workspace)
        data["desktop"] = self.status()
        try:
            data["search_plan"] = [
                {
                    "keyword": item.keyword,
                    "remote_only": item.remote_only,
                    "time_filter": item.time_filter,
                    "location": item.location,
                }
                for item in build_search_plan(self.workspace)
            ]
        except ValueError:
            data["search_plan"] = []
        return data

    def score(self, provider: str = "rules") -> dict[str, Any]:
        store = Store(self.workspace)
        jobs = store.load_jobs()
        if not jobs:
            return {"status": "empty", "scored": 0}
        evaluations = score_jobs(self.workspace, jobs, provider_name=provider)
        store.save_evaluations(evaluations)
        self.logs.append(f"Scored {len(evaluations)} jobs with {provider}")
        return {"status": "complete", "scored": len(evaluations), "provider": provider}

    def set_policy(
        self,
        mode: str | None = None,
        daily_limit: int | None = None,
        min_score: int | None = None,
        require_easy_apply: bool | None = None,
    ) -> dict[str, Any]:
        try:
            policy = update_policy(
                self.workspace,
                mode=mode,
                daily_limit=daily_limit,
                min_score=min_score,
                require_easy_apply=require_easy_apply,
            )
        except SystemExit as exc:
            raise ValueError(str(exc)) from exc
        self.logs.append(
            f"Policy updated: {policy.mode}, score {policy.min_score_to_submit}, "
            f"daily limit {policy.max_applications_per_day}"
        )
        return policy.to_dict()

    def run(self, mode: str, confirmed: bool) -> dict[str, Any]:
        if mode not in {"linkedin", "naukri", "leads", "apply", "all", "search"}:
            raise ValueError("Invalid agent mode.")
        auth = load_auth(self.workspace)
        if not auth.get("device_token"):
            raise PermissionError("Activate this desktop before using job search or automation.")
        policy = load_policy(self.workspace)
        application_mode = mode in {"linkedin", "naukri", "apply", "all"}
        if application_mode and policy.mode != "auto-submit":
            raise PermissionError("Set policy mode to auto-submit before running application modes.")
        if application_mode and not confirmed:
            raise PermissionError("Confirm auto-submit before starting the agent.")
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("The desktop agent is already running.")
            command = agent_command(self.workspace, mode)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.process = subprocess.Popen(
                command,
                cwd=self.workspace.parent,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.mode = mode
            self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.exit_code = None
            self.logs.clear()
            self.logs.append(f"Started: {' '.join(command)}")
            threading.Thread(target=self._consume_output, daemon=True).start()
        return {"status": "started", "mode": mode}

    def stop(self) -> dict[str, Any]:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                return {"status": "idle"}
            self.logs.append("Stop requested")
            self.process.terminate()
            return {"status": "stopping"}

    def sync(self) -> dict[str, Any]:
        auth = load_auth(self.workspace)
        token = str(auth.get("device_token") or "")
        if not token:
            raise PermissionError("Activate this desktop first.")
        endpoint = str(auth.get("endpoint") or DEFAULT_ENDPOINT)
        result = sync_workspace(self.workspace, endpoint, token)
        self.logs.append(f"Synced at {result.get('synced_at', '')}")
        return result

    def _consume_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.logs.append(line.rstrip())
        exit_code = process.wait()
        with self.lock:
            self.exit_code = exit_code
            self.logs.append(f"Agent finished with exit code {exit_code}")
        if exit_code == 0:
            try:
                self.sync()
            except Exception as exc:
                self.logs.append(f"Automatic sync failed: {exc}")


def create_desktop_app(workspace: Path):
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import PlainTextResponse, Response
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install desktop dependencies with: pip install -e '.[desktop]'") from exc

    write_default_workspace(workspace)
    controller = DesktopController(workspace)
    app = FastAPI(title="ApplyPilot Desktop", docs_url=None, redoc_url=None)
    development_assets = project_root() / "apps" / "web"
    packaged_assets = Path(__file__).resolve().parent / "desktop_web"
    assets = development_assets if development_assets.exists() else packaged_assets

    def require_local_origin(request: Request) -> None:
        origin = request.headers.get("origin", "")
        host = urlparse(origin).hostname if origin else ""
        if host and host not in {"127.0.0.1", "localhost", "::1"}:
            raise HTTPException(status_code=403, detail="Local desktop origin required.")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return controller.status()

    @app.get("/api/profile")
    def career_profile() -> dict[str, Any]:
        return controller.career_profile()

    @app.put("/api/profile")
    async def update_career_profile(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        body = await request.json()
        profile = body.get("profile") if isinstance(body, dict) else None
        if not isinstance(profile, dict):
            raise HTTPException(status_code=400, detail="Profile must be a JSON object.")
        try:
            return controller.save_career_profile(profile, rescore=bool(body.get("rescore")))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/resume")
    def resume() -> PlainTextResponse:
        return PlainTextResponse(
            controller.resume(),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="applypilot-resume-draft.md"'},
        )

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        return controller.dashboard()

    @app.get("/api/search-plan")
    def search_plan() -> dict[str, Any]:
        try:
            return {"queries": controller.dashboard().get("search_plan") or []}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/score")
    async def score(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        body = await request.json()
        try:
            return controller.score(str(body.get("provider") or "rules"))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/policy")
    async def set_policy(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        body = await request.json()
        try:
            return controller.set_policy(
                mode=str(body["mode"]) if body.get("mode") is not None else None,
                daily_limit=int(body["daily_limit"]) if body.get("daily_limit") is not None else None,
                min_score=int(body["min_score"]) if body.get("min_score") is not None else None,
                require_easy_apply=(
                    bool(body["require_easy_apply"])
                    if body.get("require_easy_apply") is not None
                    else None
                ),
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/activate")
    async def activate(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        body = await request.json()
        try:
            return controller.activate(
                endpoint=str(body.get("endpoint") or DEFAULT_ENDPOINT),
                license_key=str(body.get("license_key") or ""),
                device_id=str(body.get("device_id") or socket.gethostname()),
                device_name=str(body.get("device_name") or socket.gethostname()),
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/run")
    async def run_agent(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        body = await request.json()
        try:
            return controller.run(str(body.get("mode") or "apply"), bool(body.get("confirmed")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/stop")
    async def stop_agent(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        return controller.stop()

    @app.post("/api/sync")
    async def sync_agent(request: Request) -> dict[str, Any]:
        require_local_origin(request)
        try:
            return controller.sync()
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/account")
    def account() -> dict[str, Any]:
        try:
            return controller.account()
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runtime.js")
    def runtime_config() -> Response:
        return Response(
            "window.APPLYPILOT_DESKTOP = true;",
            media_type="application/javascript",
        )

    app.mount("/", StaticFiles(directory=str(assets), html=True), name="desktop-web")
    return app


def agent_command(workspace: Path, mode: str) -> list[str]:
    executable = packaged_agent_executable()
    if executable:
        return [str(executable), "--workspace", str(workspace), "--mode", mode]
    if mode == "search":
        return [
            sys.executable,
            "-m",
            "applypilot",
            "--workspace",
            str(workspace),
            "search",
        ]
    return [
        sys.executable,
        "-m",
        "applypilot",
        "--workspace",
        str(workspace),
        "daily",
        "--mode",
        mode,
    ]


def packaged_agent_executable() -> Path | None:
    name = "applypilot-agent.exe" if sys.platform == "win32" else "applypilot-agent"
    candidates = [
        Path(sys.executable).resolve().with_name(name),
        Path(sys.argv[0]).resolve().with_name(name),
    ]
    return next((path for path in candidates if path.exists()), None)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="applypilot-desktop")
    parser.add_argument("--workspace", default=str(Path.home()))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    workspace = workspace_path(args.workspace)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install desktop dependencies with: pip install -e '.[desktop]'") from exc
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    uvicorn.run(create_desktop_app(workspace), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
