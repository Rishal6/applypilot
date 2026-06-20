"""Naukri.com auto-apply connector using the user's logged-in Chrome session.

Handles:
- Chatbot questions (career break, location, experience, notice period)
- Skills chips (click all clickable)
- Already Applied detection
- No Apply button detection
"""

from __future__ import annotations

import json
import logging
import platform
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..applications import ApplicationRecord
from ..human import BETWEEN_JOBS, READING_TIME, human_pause
from ..models import Evaluation, Job
from ..policy import AutomationPolicy

logger = logging.getLogger(__name__)

# Safe default: do not guess personal chatbot answers such as CTC,
# experience, notice period, location, or disability. Customers can provide
# explicit answers in config.json under "naukri_chatbot_answers".
DEFAULT_CHATBOT_ANSWERS: dict[str, str] = {}


class NaukriBrowserConnector:
    """Local desktop Naukri connector using the user's logged-in Chrome.

    Controls the existing Google Chrome app through AppleScript on macOS,
    so Naukri uses the user's real logged-in session.
    """

    name = "naukri-browser"

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._apply_count = 0
        self._chatbot_answers = self._load_chatbot_answers()

    def apply(self, job: Job, evaluation: Evaluation, policy: AutomationPolicy) -> ApplicationRecord:
        if platform.system() != "Darwin":
            return self._record(
                job, evaluation, policy,
                "blocked",
                "Active Chrome connector currently requires macOS.",
            )
        if not job.url:
            return self._record(job, evaluation, policy, "skipped", "Job has no URL.")
        if evaluation.score < policy.min_score_to_submit:
            return self._record(job, evaluation, policy, "skipped", "Score below auto-submit threshold.")

        if self._apply_count > 0:
            human_pause(*BETWEEN_JOBS)
        self._apply_count += 1

        try:
            self._navigate(job.url)
            human_pause(*READING_TIME)

            # Check already applied
            if self._is_already_applied():
                return self._record(job, evaluation, policy, "skipped", "Already applied.")

            if policy.should_stop_before_submit:
                return self._record(
                    job,
                    evaluation,
                    policy,
                    "prepared",
                    "Opened Naukri job and stopped before clicking Apply.",
                )

            # Click Apply
            human_pause(1, 3)
            if not self._click_apply():
                return self._record(job, evaluation, policy, "skipped", "No Apply button found.")

            # Handle chatbot questions
            result = self._handle_chatbot()
            if result == "applied":
                return self._record(job, evaluation, policy, "applied", "Application submitted.")
            elif result == "no_chatbot":
                return self._record(job, evaluation, policy, "prepared", "No confirmation detected after Apply; review manually.")
            elif result == "needs_review":
                return self._record(job, evaluation, policy, "prepared", "Naukri asked an unconfigured question; review manually.")
            else:
                return self._record(job, evaluation, policy, "prepared", "Timed out before submit confirmation; review manually.")

        except Exception as exc:
            logger.exception("Naukri Chrome connector failed")
            return self._record(job, evaluation, policy, "failed", str(exc))

    def _record(self, job: Job, evaluation: Evaluation, policy: AutomationPolicy, status: str, reason: str) -> ApplicationRecord:
        return ApplicationRecord(
            job_id=job.id,
            status=status,
            reason=reason,
            score=evaluation.score,
            mode=policy.mode,
            connector=self.name,
            metadata={"url": job.url, "title": job.title, "company": job.company},
        )

    def _load_chatbot_answers(self) -> dict[str, str]:
        """Load chatbot answers from workspace config, falling back to defaults."""
        config_file = self.workspace / "config.json"
        if not config_file.exists():
            return dict(DEFAULT_CHATBOT_ANSWERS)
        try:
            with config_file.open() as f:
                config = json.load(f)
            answers = dict(DEFAULT_CHATBOT_ANSWERS)
            answers.update(config.get("naukri_chatbot_answers") or {})
            return answers
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CHATBOT_ANSWERS)

    def _navigate(self, url: str) -> None:
        escaped = self._as_applescript_string(url)
        self._osascript(
            f'tell application "Google Chrome" to set URL of active tab of front window to "{escaped}"',
            timeout=20,
        )

    def _is_already_applied(self) -> bool:
        text = self._js('document.body ? document.body.innerText.substring(0, 3000) : ""')
        return "Already Applied" in text or "already applied" in text

    def _click_apply(self) -> bool:
        result = self._js(
            'var btn = document.getElementById("apply-button"); '
            'if(btn && !btn.disabled) { btn.click(); "clicked"; } else { "no_button"; }'
        )
        return result == "clicked"

    def _handle_chatbot(self) -> str:
        """Handle chatbot questions after clicking Apply.

        Returns "applied", "no_chatbot", "needs_review", or "timeout".
        """
        for attempt in range(8):
            human_pause(2, 4)

            chatbot_text = self._js_file("""
            (function() {
                var chatbot = document.querySelector('.chatbot-container, [class*=chatbot]');
                if (!chatbot || chatbot.offsetHeight === 0) return 'no_chatbot';
                return chatbot.innerText.substring(chatbot.innerText.length - 300);
            })()
            """)

            if chatbot_text == "no_chatbot" or not chatbot_text:
                if self._is_already_applied():
                    return "applied"
                success = self._js(
                    'document.body.innerText.indexOf("successfully") > -1 '
                    '|| document.body.innerText.indexOf("Applied") > -1 ? "yes" : "no"'
                )
                if success == "yes":
                    return "applied"
                if attempt > 3:
                    return "no_chatbot"
                continue

            chatbot_lower = chatbot_text.lower()

            # Determine answer based on question content
            answer = None
            for keyword, ans in self._chatbot_answers.items():
                if keyword in chatbot_lower:
                    answer = ans
                    break

            if answer:
                answer_json = json.dumps(answer)
                # Click the chip/button with that answer
                self._js_file(f"""
                (function() {{
                    var chips = document.querySelectorAll('.chatbot_Chip, .chipItem, [class*=Chip], [class*=chip]');
                    for (var i = 0; i < chips.length; i++) {{
                        var text = chips[i].textContent.trim();
                        if (text === {answer_json}) {{
                            chips[i].click();
                            return 'clicked:' + text;
                        }}
                    }}
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
                logger.info("Chatbot: '%s' -> answered '%s'", chatbot_lower[:50], answer)
            else:
                logger.info("Chatbot: unknown question in '%s'", chatbot_lower[:50])
                return "needs_review"

            # Click skills chips (click all clickable ones)
            self._js_file("""
            (function() {
                var chips = document.querySelectorAll('[class*=clickable]');
                for (var i = 0; i < chips.length; i++) {
                    chips[i].click();
                }
            })()
            """)

        return "timeout"

    def _js(self, code: str, timeout: int = 15) -> str:
        escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        script = (
            f'tell application "Google Chrome" to tell active tab of front window '
            f'to execute javascript "{escaped}"'
        )
        result = self._osascript(script, timeout=timeout)
        return "" if result == "missing value" else result

    def _js_file(self, code: str, timeout: int = 30) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(code)
            js_path = handle.name
        script = (
            'tell application "Google Chrome" to tell active tab of front window '
            f'to execute javascript (read POSIX file "{js_path}" as text)'
        )
        result = self._osascript(script, timeout=timeout)
        return "" if result == "missing value" else result

    def _osascript(self, script: str, timeout: int = 30) -> str:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "AppleScript failed."
            raise RuntimeError(message)
        return result.stdout.strip()

    def _as_applescript_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
