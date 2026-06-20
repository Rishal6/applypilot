#!/usr/bin/env python3
"""
Naukri Auto-Apply — Chrome automation for Naukri.com
Uses same AppleScript approach as LinkedIn agent.
Handles chatbot questions, skills chips, and location prompts.
"""
import subprocess
import time
import json
import random
import re
import os
from datetime import datetime

from .brain import evaluate_job
from .runtime import log_file, workspace
from ..career import load_career_profile
from ..policy import load_policy
from ..search_plan import build_search_plan

# ─── Config ───────────────────────────────────────────────────
MAX_APPLIES_PER_SESSION = 999
READING_TIME = (3, 8)
BETWEEN_JOBS = (8, 20)
BETWEEN_SEARCHES = (12, 25)
# ──────────────────────────────────────────────────────────────

LOG_FILE = str(log_file("naukri"))

SEARCHES: list[str] = []

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


WINDOW = 1  # Use window 1 (change to 2 if running parallel with LinkedIn)


def js(code, timeout=15):
    escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    try:
        r = subprocess.run(
            ['osascript', '-e',
             f'tell application "Google Chrome" to tell active tab of window {WINDOW} to execute javascript "{escaped}"'],
            capture_output=True, text=True, timeout=timeout
        )
        result = r.stdout.strip()
        return "" if result == "missing value" else result
    except subprocess.TimeoutExpired:
        return ""


def js_file(code, timeout=30):
    with open("/tmp/naukri_auto.js", "w") as f:
        f.write(code)
    try:
        r = subprocess.run(
            ['osascript', '-e',
             f'tell application "Google Chrome" to tell active tab of window {WINDOW} to execute javascript (read POSIX file "/tmp/naukri_auto.js" as text)'],
            capture_output=True, text=True, timeout=timeout
        )
        result = r.stdout.strip()
        return "" if result == "missing value" else result
    except subprocess.TimeoutExpired:
        return ""


def navigate(url):
    subprocess.run(
        ['osascript', '-e',
         f'tell application "Google Chrome" to set URL of active tab of window {WINDOW} to "{url}"'],
        capture_output=True, text=True
    )


def human_pause(lo, hi):
    time.sleep(random.uniform(lo, hi))


def get_job_listings():
    """Extract job titles and links from search results page"""
    code = """
    (function() {
        var links = document.querySelectorAll('a');
        var jobs = [];
        for (var i = 0; i < links.length; i++) {
            var href = links[i].href || '';
            if (href.indexOf('job-listings') > -1 && href.indexOf('naukri.com') > -1) {
                var title = links[i].textContent.trim();
                if (title.length > 3 && title.length < 100 && jobs.length < 20) {
                    jobs.push(title + '|||' + href);
                }
            }
        }
        // Deduplicate
        var seen = {};
        var unique = [];
        for (var i = 0; i < jobs.length; i++) {
            if (!seen[jobs[i]]) {
                seen[jobs[i]] = true;
                unique.push(jobs[i]);
            }
        }
        return unique.join('\\n');
    })()
    """
    raw = js_file(code)
    if not raw:
        return []
    results = []
    for line in raw.split('\n'):
        parts = line.split('|||')
        if len(parts) == 2:
            results.append({"title": parts[0], "url": parts[1]})
    return results


def get_company_from_page():
    """Get company name from job detail page"""
    return js('var el = document.querySelector("[class*=comp-name], .styles_jd-header-comp-name, a[class*=company]"); el ? el.textContent.trim() : ""')


def get_job_description():
    """Get job description text"""
    return js_file("""
    (function() {
        var selectors = [".styles_JDC__dang-inner-html", ".job-desc", "[class*=job-desc]", "[class*=description]"];
        for (var i = 0; i < selectors.length; i++) {
            var el = document.querySelector(selectors[i]);
            if (el && el.innerText.length > 50) return el.innerText.substring(0, 2000);
        }
        return "";
    })()
    """)


def is_already_applied():
    """Check if already applied to this job"""
    text = js('document.body.innerText.substring(0, 3000)')
    if "Already Applied" in text or "already applied" in text:
        return True
    return False


def click_apply():
    """Click the Apply button"""
    result = js('var btn = document.getElementById("apply-button"); if(btn && !btn.disabled) { btn.click(); "clicked"; } else { "no_button"; }')
    return result == "clicked"


def handle_chatbot():
    """Handle chatbot questions after clicking Apply.

    Stops for manual review when Naukri asks an unconfigured question.
    """
    for attempt in range(8):
        human_pause(2, 4)

        # Check if chatbot is visible
        chatbot_text = js_file("""
        (function() {
            var chatbot = document.querySelector('.chatbot-container, [class*=chatbot]');
            if (!chatbot || chatbot.offsetHeight === 0) return 'no_chatbot';
            return chatbot.innerText.substring(chatbot.innerText.length - 300);
        })()
        """)

        if chatbot_text == "no_chatbot" or not chatbot_text:
            # No chatbot or it closed — check if applied
            if is_already_applied():
                return "applied"
            # Check for success indicators
            success = js('document.body.innerText.indexOf("successfully") > -1 || document.body.innerText.indexOf("Applied") > -1 ? "yes" : "no"')
            if success == "yes":
                return "applied"
            if attempt > 3:
                return "no_chatbot"
            continue

        chatbot_lower = chatbot_text.lower()

        # Determine answer based on question content
        answer = None
        for keyword, ans in _chatbot_answers().items():
            if keyword in chatbot_lower:
                answer = ans
                break

        if answer:
            answer_json = json.dumps(answer)
            # Click the chip/button with that answer
            clicked = js_file(f"""
            (function() {{
                var chips = document.querySelectorAll('.chatbot_Chip, .chipItem, [class*=Chip], [class*=chip]');
                for (var i = 0; i < chips.length; i++) {{
                    var text = chips[i].textContent.trim();
                    if (text === {answer_json}) {{
                        chips[i].click();
                        return 'clicked:' + text;
                    }}
                }}
                // Try buttons
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {{
                    var text = btns[i].textContent.trim();
                    if (text === {answer_json}) {{
                        btns[i].click();
                        return 'clicked_btn:' + text;
                    }}
                }}
                return 'not_found';
            }})()
            """)
            log(f"    Chatbot: '{chatbot_lower[:50]}' → answered '{answer}' ({clicked})")
        else:
            log(f"    Chatbot: unknown question, stopping for manual review: {chatbot_lower[:80]}")
            return "needs_review"

        # Click skills chips if they appear (click all clickable ones)
        js_file("""
        (function() {
            var chips = document.querySelectorAll('[class*=clickable]');
            for (var i = 0; i < chips.length; i++) {
                chips[i].click();
            }
        })()
        """)

    return "timeout"


def apply_to_job(job_url, job_title):
    """Full apply flow for one Naukri job"""
    navigate(job_url)
    human_pause(*READING_TIME)

    # Check already applied
    if is_already_applied():
        log("  Already applied, skipping")
        return False

    # Get company and description for scoring
    company = get_company_from_page()
    description = get_job_description()

    # AI score the job
    evaluation = evaluate_job(job_title, company, description or job_title, "India")
    score = evaluation.get('score', 0)
    log(f"  Score: {score}/100 — {evaluation.get('reason', '')[:80]}")

    if not evaluation.get("apply"):
        log(f"  Not a match (requires {evaluation.get('minimum_score', 70)}+), skipping")
        return False

    # Click Apply
    human_pause(1, 3)
    if not click_apply():
        log("  No Apply button found")
        return False

    # Handle chatbot questions
    result = handle_chatbot()
    if result == "applied":
        log("  >> APPLICATION SUBMITTED!")
        return True
    else:
        log(f"  Apply flow ended: {result}")
        return False


def main():
    log("=" * 50)
    log("Naukri Auto-Apply Agent")
    log("=" * 50)

    applied = 0
    seen_urls = set()

    try:
        searches = [item.keyword for item in build_search_plan(workspace())]
    except ValueError as exc:
        log(f"Cannot search: {exc}")
        return
    policy = load_policy(workspace())
    profile = load_career_profile(workspace())
    answers = _profile_answers()
    experience = str(answers.get("years_experience") or "").strip()
    location = str(profile.get("location") or "").strip()
    session_limit = policy.max_applications_per_day
    log("Profile search plan: " + ", ".join(searches))
    log(f"Application gate: score >= {policy.min_score_to_submit}, daily limit {session_limit}")

    for qi, query in enumerate(searches):
        if applied >= session_limit:
            break

        log(f"\n[{qi+1}/{len(searches)}] Searching: '{query}'")

        filters = "&jobAge=7"
        if experience.isdigit():
            filters += f"&experience={experience}"
        if location and "remote" not in location.lower():
            filters += f"&l={location.replace(' ', '+')}"
        url = f"https://www.naukri.com/{query.lower().replace(' ', '-')}-jobs?k={query.replace(' ', '+')}{filters}"
        navigate(url)
        human_pause(4, 7)

        # Get job listings
        jobs = get_job_listings()
        log(f"Found {len(jobs)} jobs")

        for job in jobs:
            if applied >= session_limit:
                break

            if job["url"] in seen_urls:
                continue
            seen_urls.add(job["url"])

            log(f"\n--- {job['title'][:55]}")

            success = apply_to_job(job["url"], job["title"])
            if success:
                applied += 1
                log(f"  Total applied: {applied}")

            human_pause(*BETWEEN_JOBS)

        human_pause(*BETWEEN_SEARCHES)

    log(f"\n{'='*50}")
    log(f"SESSION COMPLETE — Applied: {applied}")
    log(f"Log: {LOG_FILE}")


def _profile_answers():
    path = workspace() / "config.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    answers = raw.get("profile_answers") or {}
    return answers if isinstance(answers, dict) else {}


def _chatbot_answers():
    answers = _profile_answers()
    return {
        "career break": answers.get("career_break", ""),
        "based out": answers.get("willing_to_relocate", ""),
        "relocate": answers.get("willing_to_relocate", ""),
        "notice period": answers.get("notice_period", ""),
        "current ctc": answers.get("current_ctc", ""),
        "expected ctc": answers.get("expected_ctc", ""),
        "experience": answers.get("years_experience", ""),
        "gender": "",
        "disability": answers.get("disability", ""),
    }


if __name__ == "__main__":
    main()
