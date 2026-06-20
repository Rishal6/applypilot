from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_preferences, workspace_path, write_default_workspace
from .connectors.legacy_linkedin import load_legacy_jobs
from .connectors.linkedin_search import LinkedInSearcher, SearchQuery, DEFAULT_SEARCHES
from .agent import run_cycle, run_forever
from .applications import ApplicationHistory
from .dashboard import write_dashboard_data
from .legacy_agent import (
    run_native_agent,
    resolve_legacy_dir,
    run_legacy_agent,
    sync_legacy_logs,
    sync_native_logs,
    totals_for_runs,
)
from .models import Evaluation, Job
from .policy import load_policy, update_policy
from .scoring import score_jobs
from .storage import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="applypilot")
    parser.add_argument("--workspace", default=".", help="Project root or .applypilot workspace path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a local ApplyPilot workspace")
    status_cmd = sub.add_parser("status", help="Show ApplyPilot and working-agent status")
    status_cmd.add_argument("--legacy-dir", default="", help="Path to the working linkedin-agent folder")

    import_cmd = sub.add_parser("import-linkedin", help="Import jobs from the current working agent JSON")
    import_cmd.add_argument("--source", required=True, help="Path to linkedin_jobs.json or similar JSON")

    score_cmd = sub.add_parser("score", help="Score queued jobs")
    score_cmd.add_argument("--provider", default="rules", help="Scoring provider, default: rules")

    review_cmd = sub.add_parser("review", help="Print the review queue")
    review_cmd.add_argument("--min-score", type=int, default=0)
    review_cmd.add_argument("--limit", type=int, default=20)

    report_cmd = sub.add_parser("report", help="Write a markdown review report")
    report_cmd.add_argument("--out", default="", help="Output markdown path")

    policy_cmd = sub.add_parser("policy", help="Show or update automation policy")
    policy_cmd.add_argument("--mode", choices=["review-only", "fill-only", "auto-submit"])
    policy_cmd.add_argument("--daily-limit", type=int)
    policy_cmd.add_argument("--min-score", type=int)
    policy_cmd.add_argument("--allow-non-easy-apply", action="store_true")

    search_cmd = sub.add_parser("search", help="Search LinkedIn or Naukri for jobs and save to store")
    search_cmd.add_argument("--browser-profile", default="", help="Reserved for packaged builds; active Chrome ignores this")
    search_cmd.add_argument("--source", default="linkedin", choices=["linkedin", "naukri"], help="Job board to search")

    run_cmd = sub.add_parser("run", help="Run the unattended local desktop agent")
    run_cmd.add_argument("--provider", default="rules")
    run_cmd.add_argument("--connector", default="none", help="none, linkedin-browser, or naukri-browser")
    run_cmd.add_argument("--once", action="store_true", help="Run one cycle and exit")
    run_cmd.add_argument("--interval-minutes", type=float, default=60)
    run_cmd.add_argument("--max-cycles", type=int, default=0)
    run_cmd.add_argument("--search", action="store_true", help="Search LinkedIn for jobs before scoring+applying")

    leads_cmd = sub.add_parser("leads", help="Run the Lead Hunter — search hashtags, extract contacts, draft emails")
    leads_cmd.add_argument("--max-searches", type=int, default=8, help="Max hashtag searches per run")
    leads_cmd.add_argument("--hashtags", nargs="*", help="Override hashtag list")

    premium_cmd = sub.add_parser("premium", help="Run Premium discovery — draft outreach and check Naukri status")
    premium_cmd.add_argument("--max-inmails", type=int, default=10, help="Max InMails per day")
    premium_cmd.add_argument("--max-connects", type=int, default=20, help="Max connections per day")

    daily_cmd = sub.add_parser("daily", help="Run the working-agent replica flow")
    daily_cmd.add_argument("--mode", choices=["all", "apply", "linkedin", "naukri", "leads"], default="all")
    daily_cmd.add_argument("--legacy-dir", default="", help="Path to the working linkedin-agent folder")
    daily_cmd.add_argument("--use-legacy", action="store_true", help="Run scripts from the old working-agent folder")
    daily_cmd.add_argument("--dry-run", action="store_true", help="Print which scripts would run without applying")

    sync_cmd = sub.add_parser("sync-legacy", help="Sync working-agent log summaries into ApplyPilot reports")
    sync_cmd.add_argument("--legacy-dir", default="", help="Path to the working linkedin-agent folder")

    dashboard_cmd = sub.add_parser("dashboard", help="Export dashboard data for the web UI")
    dashboard_cmd.add_argument("--out", default="apps/web/data/dashboard.json", help="Dashboard JSON output path")

    serve_cmd = sub.add_parser("serve", help="Run the ApplyPilot SaaS API and dashboard")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8787)
    serve_cmd.add_argument("--db", default="", help="SQLite database path for SaaS state")
    serve_cmd.add_argument("--web-dir", default="apps/web", help="Static dashboard directory to serve")

    customer_cmd = sub.add_parser("saas-create-customer", help="Create a SaaS customer and issue a license")
    customer_cmd.add_argument("--email", required=True)
    customer_cmd.add_argument("--name", default="")
    customer_cmd.add_argument("--company", default="")
    customer_cmd.add_argument("--plan", default="pro_byok", choices=["free_cli", "pro_byok", "pro_managed", "team"])
    customer_cmd.add_argument(
        "--ai-mode",
        default="byok_local",
        choices=["byok_local", "byok_cloud", "managed_api", "hosted_model", "hybrid"],
    )
    customer_cmd.add_argument("--seats", type=int, default=1)
    customer_cmd.add_argument("--expires-at", default="")
    customer_cmd.add_argument("--db", default="", help="SQLite database path for SaaS state")

    activate_cmd = sub.add_parser("saas-activate", help="Activate this desktop against a SaaS license")
    activate_cmd.add_argument("--endpoint", default="http://127.0.0.1:8787")
    activate_cmd.add_argument("--license-key", default="", help="Defaults to APPLYPILOT_LICENSE_KEY")
    activate_cmd.add_argument("--device-id", default="")
    activate_cmd.add_argument("--device-name", default="")
    activate_cmd.add_argument("--out", default="", help="Auth file path, defaults to .applypilot/saas_auth.json")

    sync_saas_cmd = sub.add_parser("saas-sync", help="Sync local dashboard data to the SaaS API")
    sync_saas_cmd.add_argument("--endpoint", default="")
    sync_saas_cmd.add_argument("--token", default="", help="Defaults to APPLYPILOT_DEVICE_TOKEN or saved auth")

    me_cmd = sub.add_parser("saas-me", help="Show the SaaS account linked to this workspace")
    me_cmd.add_argument("--endpoint", default="")
    me_cmd.add_argument("--token", default="", help="Defaults to APPLYPILOT_DEVICE_TOKEN or saved auth")

    resume_cmd = sub.add_parser("resume", help="Generate a resume PDF (or Markdown if fpdf2 not installed)")
    resume_cmd.add_argument("--job-url", default="", help="URL of a job to tailor the resume for")
    resume_cmd.add_argument("--job-id", default="", help="ID of a stored job to tailor for")
    resume_cmd.add_argument("--out", default="", help="Output file path")

    args = parser.parse_args(argv)
    workspace = workspace_path(args.workspace)
    store = Store(workspace)

    if args.command == "init":
        write_default_workspace(workspace)
        print(f"Initialized ApplyPilot workspace: {workspace}")
        return 0

    if args.command == "status":
        write_default_workspace(workspace)
        legacy_dir = resolve_legacy_dir(workspace, args.legacy_dir or None)
        print_status(workspace, store, legacy_dir)
        return 0

    if args.command == "import-linkedin":
        write_default_workspace(workspace)
        jobs = load_legacy_jobs(args.source)
        added = store.add_jobs(jobs)
        print(f"Imported {len(jobs)} jobs ({added} new) into {store.jobs_file}")
        return 0

    if args.command == "search":
        write_default_workspace(workspace)
        if args.source == "naukri":
            from .connectors.naukri_search import NaukriSearcher

            searcher_naukri = NaukriSearcher(workspace)
            jobs = searcher_naukri.search()
        else:
            profile_path = Path(args.browser_profile).expanduser() if args.browser_profile else None
            searcher = LinkedInSearcher(workspace, browser_profile_path=profile_path)
            jobs = searcher.search()
        if not jobs:
            print("No jobs found.")
            return 0
        added = store.add_jobs(jobs)
        easy = sum(1 for j in jobs if j.easy_apply)
        print(f"Search complete: {len(jobs)} jobs found ({easy} Easy Apply), {added} new added to store.")
        evaluations = score_jobs(workspace, store.load_jobs(), provider_name="rules")
        store.save_evaluations(evaluations)
        print(f"Scored {len(evaluations)} queued jobs using provider 'rules'.")
        return 0

    if args.command == "score":
        write_default_workspace(workspace)
        jobs = store.load_jobs()
        if not jobs:
            print("No jobs queued. Run import-linkedin first.")
            return 1
        evaluations = score_jobs(workspace, jobs, provider_name=args.provider)
        store.save_evaluations(evaluations)
        print(f"Scored {len(evaluations)} jobs using provider '{args.provider}'.")
        print(f"Saved: {store.evaluations_file}")
        return 0

    if args.command == "review":
        return print_review(store, args.min_score, args.limit)

    if args.command == "report":
        out = Path(args.out).expanduser() if args.out else store.reports_dir / "review.md"
        write_report(store, out)
        print(f"Wrote report: {out}")
        return 0

    if args.command == "policy":
        write_default_workspace(workspace)
        changed = args.mode is not None or args.daily_limit is not None or args.min_score is not None or args.allow_non_easy_apply
        if changed:
            policy = update_policy(
                workspace,
                mode=args.mode,
                daily_limit=args.daily_limit,
                min_score=args.min_score,
                require_easy_apply=False if args.allow_non_easy_apply else None,
            )
            print("Updated automation policy.")
        else:
            policy = load_policy(workspace)
        print_policy(policy)
        return 0

    if args.command == "run":
        write_default_workspace(workspace)
        if args.search:
            searcher = LinkedInSearcher(workspace)
            jobs = searcher.search()
            if jobs:
                added = store.add_jobs(jobs)
                print(f"Search: {len(jobs)} found, {added} new added.")
            else:
                print("Search: no jobs found.")
        interval_seconds = max(30, int(args.interval_minutes * 60))
        if args.once:
            summary = run_cycle(workspace, provider_name=args.provider, connector_name=args.connector)
            print(
                f"scored={summary.scored}, eligible={summary.eligible}, attempted={summary.attempted}, "
                f"applied={summary.applied}, prepared={summary.prepared}, skipped={summary.skipped}, "
                f"blocked={summary.blocked}, failed={summary.failed}"
            )
            return 0
        run_forever(
            workspace,
            provider_name=args.provider,
            connector_name=args.connector,
            interval_seconds=interval_seconds,
            max_cycles=args.max_cycles or None,
        )
        return 0

    if args.command == "leads":
        from .leads import LeadHunter

        write_default_workspace(workspace)
        page = _get_playwright_page(workspace)
        if page is None:
            print("Could not launch browser. Ensure Playwright is installed (pip install playwright && playwright install chromium).")
            return 1
        hunter = LeadHunter(workspace, hashtags=args.hashtags, max_searches=args.max_searches)
        leads = hunter.run(page)
        print(f"Lead Hunt complete: {len(leads)} leads found.")
        print(f"  With email: {sum(1 for l in leads if l.email)}")
        print(f"  With profile: {sum(1 for l in leads if l.profile_url)}")
        print(f"  Drafts written: {sum(1 for l in leads if l.draft_email)}")
        print(f"  Saved to: {workspace / 'leads'}")
        page.context.browser.close()
        return 0

    if args.command == "premium":
        from .premium import PremiumFeatures

        write_default_workspace(workspace)
        page = _get_playwright_page(workspace)
        if page is None:
            print("Could not launch browser. Ensure Playwright is installed (pip install playwright && playwright install chromium).")
            return 1
        pf = PremiumFeatures(workspace, max_inmails=args.max_inmails, max_connects=args.max_connects)
        summary = pf.run(page)
        print("Premium discovery complete (draft-only):")
        print(f"  Profile viewers found: {summary['profile_viewers_found']}")
        print(f"  Connection drafts: {summary.get('connection_drafts', 0)}")
        print(f"  InMail drafts: {summary.get('inmail_drafts', 0)}")
        print("  Connections sent: 0 (manual review required)")
        print("  InMails sent: 0 (manual review required)")
        print(f"  Naukri activity: {summary['naukri_activity']}")
        page.context.browser.close()
        return 0

    if args.command == "daily":
        write_default_workspace(workspace)
        if args.use_legacy:
            legacy_dir = resolve_legacy_dir(workspace, args.legacy_dir or None)
            results = run_legacy_agent(args.mode, legacy_dir, dry_run=args.dry_run)
        else:
            results = run_native_agent(args.mode, workspace, dry_run=args.dry_run)
        for script, code in results:
            prefix = "would run" if args.dry_run else "finished"
            print(f"{script}: {prefix} (exit={code})")
        if not args.dry_run:
            summaries = (
                sync_legacy_logs(workspace, legacy_dir)
                if args.use_legacy else sync_native_logs(workspace)
            )
            totals = totals_for_runs(summaries)
            print(
                "Synced run logs: "
                f"linkedin={totals['linkedin_applied']}, "
                f"naukri={totals['naukri_applied']}, "
                f"leads={totals['leads']}"
            )

        return 0

    if args.command == "sync-legacy":
        write_default_workspace(workspace)
        legacy_dir = resolve_legacy_dir(workspace, args.legacy_dir or None)
        summaries = sync_legacy_logs(workspace, legacy_dir)
        totals = totals_for_runs(summaries)
        print(f"Synced {len(summaries)} legacy runs into {workspace / 'reports' / 'legacy_runs.json'}")
        print(f"LinkedIn applied: {totals['linkedin_applied']}")
        print(f"Naukri applied: {totals['naukri_applied']}")
        print(f"Leads found: {totals['leads']}")
        print(f"Lead emails: {totals['lead_emails']}")
        return 0

    if args.command == "dashboard":
        write_default_workspace(workspace)
        out = Path(args.out).expanduser()
        if not out.is_absolute():
            out = Path.cwd() / out
        data = write_dashboard_data(workspace, out)
        print(f"Wrote dashboard data: {out}")
        print(f"Jobs: {data['summary']['jobs']}")
        print(f"Legacy applied: {data['summary']['legacy_linkedin_applied'] + data['summary']['legacy_naukri_applied']}")
        print(f"Native applied: {data['summary']['native_linkedin_applied'] + data['summary']['native_naukri_applied']}")
        return 0

    if args.command == "serve":
        from .saas_store import default_saas_db
        from .server import run_server

        write_default_workspace(workspace)
        db = Path(args.db).expanduser() if args.db else default_saas_db(workspace)
        web_dir = Path(args.web_dir).expanduser()
        if not web_dir.is_absolute():
            web_dir = Path.cwd() / web_dir
        print(f"ApplyPilot SaaS API: http://{args.host}:{args.port}")
        print(f"Database: {db}")
        print(f"Dashboard: {web_dir if web_dir.exists() else 'not mounted'}")
        run_server(args.host, args.port, db, web_dir if web_dir.exists() else None)
        return 0

    if args.command == "saas-create-customer":
        from .saas_store import SaasStore, default_saas_db

        write_default_workspace(workspace)
        db = Path(args.db).expanduser() if args.db else default_saas_db(workspace)
        saas = SaasStore(db)
        customer = saas.create_customer(
            email=args.email,
            name=args.name,
            company=args.company,
            plan=args.plan,
            ai_mode=args.ai_mode,
        )
        issued = saas.issue_license(customer["id"], seats=args.seats, expires_at=args.expires_at)
        safe = {"customer": customer, "license": issued["license"], "license_key": issued["license_key"]}
        print(json.dumps(safe, indent=2))
        return 0

    if args.command == "saas-activate":
        from .saas_client import activate_device, default_device_id, save_auth

        write_default_workspace(workspace)
        license_key = args.license_key or os.environ.get("APPLYPILOT_LICENSE_KEY", "")
        if not license_key:
            print("Missing license key. Pass --license-key or set APPLYPILOT_LICENSE_KEY.")
            return 1
        result = activate_device(
            endpoint=args.endpoint,
            license_key=license_key,
            device_id=args.device_id or default_device_id(),
            device_name=args.device_name or default_device_id(),
        )
        auth = {
            "endpoint": args.endpoint,
            "device_token": result["device_token"],
            "device": result["device"],
            "customer": result["customer"],
            "license": result["license"],
        }
        out = Path(args.out).expanduser() if args.out else workspace / "saas_auth.json"
        if out != workspace / "saas_auth.json":
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(auth, indent=2), encoding="utf-8")
        else:
            save_auth(workspace, auth)
        print(f"Activated device: {result['device']['device_id']}")
        print(f"Saved SaaS auth: {out}")
        return 0

    if args.command == "saas-sync":
        from .saas_client import DEFAULT_ENDPOINT, load_auth, sync_workspace

        write_default_workspace(workspace)
        auth = load_auth(workspace)
        endpoint = args.endpoint or auth.get("endpoint") or DEFAULT_ENDPOINT
        token = args.token or os.environ.get("APPLYPILOT_DEVICE_TOKEN", "") or auth.get("device_token", "")
        if not token:
            print("Missing device token. Run saas-activate or set APPLYPILOT_DEVICE_TOKEN.")
            return 1
        result = sync_workspace(workspace, endpoint, token)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "saas-me":
        from .saas_client import DEFAULT_ENDPOINT, fetch_me, load_auth

        write_default_workspace(workspace)
        auth = load_auth(workspace)
        endpoint = args.endpoint or auth.get("endpoint") or DEFAULT_ENDPOINT
        token = args.token or os.environ.get("APPLYPILOT_DEVICE_TOKEN", "") or auth.get("device_token", "")
        if not token:
            print("Missing token. Run saas-activate or set APPLYPILOT_DEVICE_TOKEN.")
            return 1
        print(json.dumps(fetch_me(endpoint, token), indent=2))
        return 0

    if args.command == "resume":
        from .resume_builder import ResumeBuilder as RB, load_profile

        write_default_workspace(workspace)
        profile = load_profile(workspace)
        if not profile.get("name") or profile.get("name") == "Candidate":
            if not profile.get("raw_text"):
                print(
                    "No resume data found. Create resume_data.json or profile.md "
                    f"in {workspace}"
                )
                return 1

        # Find job to tailor for
        target_job: Job | None = None
        if args.job_id:
            jobs = {j.id: j for j in store.load_jobs()}
            target_job = jobs.get(args.job_id)
            if not target_job:
                print(f"Job ID '{args.job_id}' not found in store.")
                return 1
        elif args.job_url:
            # Look up by URL or create a minimal Job for tailoring
            jobs = store.load_jobs()
            target_job = next((j for j in jobs if j.url == args.job_url), None)
            if not target_job:
                target_job = Job(id=args.job_url, title="", company="", url=args.job_url)
                print(f"Job URL not in store; tailoring with minimal info.")

        output = Path(args.out).expanduser() if args.out else None
        builder = RB()
        result_path = builder.build_resume(profile, job=target_job, output_path=output)
        print(f"Resume generated: {result_path}")
        return 0

    return 1


def print_review(store: Store, min_score: int, limit: int) -> int:
    jobs = {job.id: job for job in store.load_jobs()}
    evaluations = [
        item for item in store.load_evaluations()
        if item.score >= min_score and item.job_id in jobs
    ]
    evaluations.sort(key=lambda item: item.score, reverse=True)

    if not evaluations:
        print("No evaluated jobs matched. Run score first.")
        return 1

    for idx, evaluation in enumerate(evaluations[:limit], 1):
        job = jobs[evaluation.job_id]
        print(f"{idx:>2}. [{evaluation.score:>3}] {evaluation.decision.upper()} - {job.title} @ {job.company}")
        if job.location:
            print(f"    Location: {job.location}")
        print(f"    Reason: {evaluation.reason}")
        if job.url:
            print(f"    URL: {job.url}")
    return 0


def write_report(store: Store, out: Path) -> None:
    jobs = {job.id: job for job in store.load_jobs()}
    evaluations = [item for item in store.load_evaluations() if item.job_id in jobs]
    evaluations.sort(key=lambda item: item.score, reverse=True)

    lines = [
        "# ApplyPilot Review Queue",
        "",
        "| Score | Decision | Role | Company | Location |",
        "|---:|---|---|---|---|",
    ]
    for evaluation in evaluations:
        job = jobs[evaluation.job_id]
        lines.append(
            f"| {evaluation.score} | {evaluation.decision} | "
            f"{escape_md(job.title)} | {escape_md(job.company)} | {escape_md(job.location)} |"
        )

    lines.extend(["", "## Details", ""])
    for evaluation in evaluations:
        job = jobs[evaluation.job_id]
        lines.extend([
            f"### {job.title} @ {job.company}",
            "",
            f"- Score: {evaluation.score}",
            f"- Decision: {evaluation.decision}",
            f"- Reason: {evaluation.reason}",
            f"- Location: {job.location or 'Unknown'}",
            f"- URL: {job.url or 'N/A'}",
            "",
        ])

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def print_policy(policy) -> None:
    print(f"Mode: {policy.mode}")
    print(f"Auto-submit enabled: {'yes' if policy.can_auto_submit else 'no'}")
    print(f"Stop before submit: {'yes' if policy.should_stop_before_submit else 'no'}")
    print(f"Daily application limit: {policy.max_applications_per_day}")
    print(f"Minimum score to submit: {policy.min_score_to_submit}")
    print(f"Easy Apply required: {'yes' if policy.require_easy_apply else 'no'}")


def print_status(workspace: Path, store: Store, legacy_dir: Path) -> None:
    jobs = store.load_jobs()
    evaluations = store.load_evaluations()
    history = ApplicationHistory(workspace).load()
    policy = load_policy(workspace)

    print(f"Workspace: {workspace}")
    print(f"Policy: {policy.mode} | min_score={policy.min_score_to_submit} | daily_limit={policy.max_applications_per_day}")
    print(f"Jobs queued: {len(jobs)}")
    print(f"Easy Apply jobs: {sum(1 for job in jobs if job.easy_apply)}")
    print(f"Evaluations: {len(evaluations)}")
    print(f"Shortlist >= min score: {sum(1 for item in evaluations if item.score >= policy.min_score_to_submit)}")
    print(f"ApplyPilot application records: {len(history)}")

    try:
        native_summaries = sync_native_logs(workspace)
        native_totals = totals_for_runs(native_summaries)
        print(f"Native runs synced: {len(native_summaries)}")
        print(f"Native LinkedIn applied: {native_totals['linkedin_applied']}")
        print(f"Native Naukri applied: {native_totals['naukri_applied']}")
        print(f"Native leads found: {native_totals['leads']}")
    except Exception as exc:
        print(f"Native runs: unavailable ({exc})")

    try:
        summaries = sync_legacy_logs(workspace, legacy_dir)
        totals = totals_for_runs(summaries)
        print(f"Working agent: {legacy_dir}")
        print(f"Legacy runs synced: {len(summaries)}")
        print(f"Legacy LinkedIn applied: {totals['linkedin_applied']}")
        print(f"Legacy Naukri applied: {totals['naukri_applied']}")
        print(f"Legacy leads found: {totals['leads']}")
    except SystemExit as exc:
        print(f"Working agent: unavailable ({exc})")


def _get_playwright_page(workspace: Path):
    """Launch Playwright Chromium with a persistent profile so LinkedIn stays logged in."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    user_data_dir = workspace / "browser_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    browser = pw.chromium.launch_persistent_context(
        str(user_data_dir),
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    return page


if __name__ == "__main__":
    raise SystemExit(main())
