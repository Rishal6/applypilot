import argparse

from applypilot.config import workspace_path, write_default_workspace
from applypilot.connectors.linkedin_search import LinkedInSearcher
from applypilot.legacy_agent import run_native_agent, sync_native_logs, totals_for_runs
from applypilot.scoring import score_jobs
from applypilot.storage import Store


def main() -> int:
    parser = argparse.ArgumentParser(prog="applypilot-agent")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--mode", choices=["all", "apply", "linkedin", "naukri", "leads", "search"], default="apply")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = workspace_path(args.workspace)
    write_default_workspace(workspace)
    if args.mode == "search":
        store = Store(workspace)
        jobs = LinkedInSearcher(workspace).search()
        added = store.add_jobs(jobs) if jobs else 0
        evaluations = score_jobs(workspace, store.load_jobs(), provider_name="rules") if store.load_jobs() else []
        if evaluations:
            store.save_evaluations(evaluations)
        print(
            f"search found={len(jobs)} added={added} scored={len(evaluations)}",
            flush=True,
        )
        return 0
    results = run_native_agent(args.mode, workspace, dry_run=args.dry_run)
    for module, code in results:
        print(f"{module}: exit={code}", flush=True)
        if code:
            return code
    if not args.dry_run:
        totals = totals_for_runs(sync_native_logs(workspace))
        print(
            f"synced linkedin={totals['linkedin_applied']} "
            f"naukri={totals['naukri_applied']} leads={totals['leads']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
