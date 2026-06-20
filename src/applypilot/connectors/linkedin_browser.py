from __future__ import annotations

import json
import logging
import platform
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..applications import ApplicationRecord
from ..career import load_profile_answers
from ..form_filler import AIFormFiller, load_profile
from ..human import BETWEEN_JOBS, READING_TIME, human_pause
from ..models import Evaluation, Job
from ..policy import AutomationPolicy

logger = logging.getLogger(__name__)


class LinkedInBrowserConnector:
    """Local desktop LinkedIn connector using the user's logged-in Chrome.

    This connector deliberately does not launch Playwright, Chromium, or a new
    browser profile. On macOS it controls the existing Google Chrome app through
    AppleScript, so LinkedIn uses the user's real logged-in session.
    """

    name = "linkedin-browser"

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.max_steps = 12
        self._apply_count = 0

    def apply(self, job: Job, evaluation: Evaluation, policy: AutomationPolicy) -> ApplicationRecord:
        if platform.system() != "Darwin":
            return self._record(
                job,
                evaluation,
                policy,
                "blocked",
                "Active Chrome connector currently requires macOS.",
            )
        if not job.url:
            return self._record(job, evaluation, policy, "skipped", "Job has no URL.")
        if policy.require_easy_apply and not job.easy_apply:
            return self._record(job, evaluation, policy, "skipped", "Policy requires Easy Apply jobs.")
        if evaluation.score < policy.min_score_to_submit:
            return self._record(job, evaluation, policy, "skipped", "Score below auto-submit threshold.")

        if self._apply_count > 0:
            human_pause(*BETWEEN_JOBS)
        self._apply_count += 1

        try:
            opened = self._open_job_in_existing_chrome(job.url)
            if not opened.startswith("http"):
                return self._record(job, evaluation, policy, "blocked", opened)

            human_pause(4, 7)
            current_url = self._current_url()
            if "login" in current_url or "authwall" in current_url:
                return self._record(job, evaluation, policy, "blocked", "LinkedIn login required in existing Chrome.")

            unavailable = self._unavailable_reason()
            if unavailable:
                status = "skipped" if unavailable != "Already applied" else "skipped"
                return self._record(job, evaluation, policy, status, unavailable)

            if self._rate_limited():
                return self._record(job, evaluation, policy, "blocked", "LinkedIn rate limit or security check detected.")

            read_time = random.uniform(*READING_TIME)
            self._scroll_page(random.randint(1, 3))
            time.sleep(read_time)

            if not self._click_easy_apply():
                unavailable = self._unavailable_reason()
                return self._record(job, evaluation, policy, "skipped", unavailable or "No Easy Apply button found.")

            human_pause(2, 4)
            profile_answers = self._load_profile_answers()
            ai_filler = self._init_ai_filler()

            for _ in range(self.max_steps):
                self._fill_fields(profile_answers, ai_filler)
                human_pause(1, 2.5)

                action = self._advance_or_submit(stop_before_submit=policy.should_stop_before_submit)
                if action == "prepared":
                    return self._record(job, evaluation, policy, "prepared", "Stopped before final submit.")
                if action == "submitted":
                    human_pause(2, 4)
                    self._dismiss_success()
                    return self._record(job, evaluation, policy, "applied", "Application submitted.")
                if action in {"next", "review", "continue"}:
                    human_pause(2, 5)
                    continue
                if action == "no_modal":
                    return self._record(job, evaluation, policy, "failed", "Easy Apply modal was not open.")
                return self._record(job, evaluation, policy, "failed", "Could not find next/review/submit button.")

            return self._record(job, evaluation, policy, "failed", "Max application steps exceeded.")
        except Exception as exc:
            logger.exception("Active Chrome connector failed")
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

    def _open_job_in_existing_chrome(self, url: str) -> str:
        script = f'''
        tell application "Google Chrome"
            activate
            if (count of windows) = 0 then
                return "No existing Chrome window. Open logged-in Chrome first."
            end if

            repeat with wi from 1 to count of windows
                set w to window wi
                repeat with ti from 1 to count of tabs of w
                    if URL of tab ti of w contains "linkedin.com" then
                        set active tab index of w to ti
                        set index of w to 1
                        set URL of tab ti of w to "{self._as_applescript_string(url)}"
                        return URL of tab ti of w
                    end if
                end repeat
            end repeat

            tell front window
                make new tab with properties {{URL:"{self._as_applescript_string(url)}"}}
                set active tab index to (count of tabs)
                return URL of active tab
            end tell
        end tell
        '''
        return self._osascript(script, timeout=20)

    def _current_url(self) -> str:
        return self._osascript(
            'tell application "Google Chrome" to return URL of active tab of front window',
            timeout=5,
        )

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

    def _js(self, code: str, timeout: int = 30) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(code)
            js_path = handle.name
        script = (
            'tell application "Google Chrome" to tell active tab of front window '
            f'to execute javascript (read POSIX file "{js_path}" as text)'
        )
        result = self._osascript(script, timeout=timeout)
        return "" if result == "missing value" else result

    def _unavailable_reason(self) -> str:
        text = self._js('document.body ? document.body.innerText.substring(0, 8000) : ""').lower()
        if "no longer accepting applications" in text:
            return "No longer accepting applications"
        if "this job is no longer available" in text or "job is no longer available" in text:
            return "Job is no longer available"
        if "you've already applied" in text or "you have already applied" in text:
            return "Already applied"
        return ""

    def _rate_limited(self) -> bool:
        text = self._js('document.body ? document.body.innerText.substring(0, 5000) : ""').lower()
        return "429" in text or "rate limit" in text or "let's do a quick security check" in text

    def _scroll_page(self, times: int) -> None:
        for _ in range(times):
            amount = random.randint(150, 500)
            if random.random() < 0.15:
                amount = -random.randint(50, 200)
            self._js(f"window.scrollBy(0, {amount})", timeout=10)
            human_pause(1.5, 4)

    def _click_easy_apply(self) -> bool:
        result = self._js("""
        (function() {
            function visible(el) {
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.y >= 0 && !el.disabled;
            }
            var buttons = Array.from(document.querySelectorAll("button"));
            for (var i = 0; i < buttons.length; i++) {
                var aria = buttons[i].getAttribute("aria-label") || "";
                if (aria.indexOf("Easy Apply") > -1 && visible(buttons[i])) {
                    buttons[i].click();
                    return "clicked";
                }
            }
            for (var j = 0; j < buttons.length; j++) {
                var text = (buttons[j].innerText || buttons[j].textContent || "").trim();
                var cls = buttons[j].className || "";
                if (text === "Easy Apply" && cls.indexOf("artdeco-pill") === -1 && visible(buttons[j])) {
                    buttons[j].click();
                    return "clicked";
                }
            }
            return "not_found";
        })()
        """)
        return result == "clicked"

    def _fill_fields(self, answers: dict[str, str], ai_filler: AIFormFiller | None) -> None:
        self._fill_text_fields(answers, ai_filler)
        self._fill_selects(answers, ai_filler)
        self._fill_radios(answers, ai_filler)

    def _fill_text_fields(self, answers: dict[str, str], ai_filler: AIFormFiller | None) -> None:
        fields = self._json_js("""
        (function() {
            function visible(el) {
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            function labelFor(el) {
                if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
                if (el.getAttribute("placeholder")) return el.getAttribute("placeholder");
                if (el.id) {
                    var byFor = document.querySelector("label[for='" + CSS.escape(el.id) + "']");
                    if (byFor) return byFor.innerText || byFor.textContent || "";
                }
                var wrap = el.closest(".fb-dash-form-element, .jobs-easy-apply-form-section__grouping");
                if (wrap) {
                    var lbl = wrap.querySelector("label, legend, span[class*='label']");
                    if (lbl) return lbl.innerText || lbl.textContent || "";
                }
                return "";
            }
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var els = Array.from(root.querySelectorAll("input[type='text'], input[type='email'], input[type='tel'], input[type='number'], textarea"));
            return JSON.stringify(els.map(function(el, idx) {
                return {index: idx, label: labelFor(el), value: el.value || "", type: el.getAttribute("type") || el.tagName};
            }).filter(function(item, idx) { return visible(els[idx]) && !item.value.trim(); }));
        })()
        """)
        for field in fields:
            label = field.get("label", "")
            answer = self._answer_for(label, answers)
            if not answer and ai_filler and label:
                answer = ai_filler.answer(label)
            if not answer:
                continue
            if field.get("type") == "number":
                nums = re.findall(r"[\d.]+", answer)
                answer = nums[0] if nums else ""
            if answer:
                self._set_text_field(int(field["index"]), answer)

    def _fill_selects(self, answers: dict[str, str], ai_filler: AIFormFiller | None) -> None:
        selects = self._json_js("""
        (function() {
            function visible(el) {
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            function labelFor(el) {
                if (el.id) {
                    var byFor = document.querySelector("label[for='" + CSS.escape(el.id) + "']");
                    if (byFor) return byFor.innerText || byFor.textContent || "";
                }
                var wrap = el.closest(".fb-dash-form-element, .jobs-easy-apply-form-section__grouping");
                if (wrap) {
                    var lbl = wrap.querySelector("label, legend, span[class*='label']");
                    if (lbl) return lbl.innerText || lbl.textContent || "";
                }
                return "";
            }
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var els = Array.from(root.querySelectorAll("select"));
            return JSON.stringify(els.map(function(el, idx) {
                return {
                    index: idx,
                    label: labelFor(el),
                    value: el.value || "",
                    options: Array.from(el.options).map(function(o) { return {text: o.text, value: o.value}; })
                };
            }).filter(function(item, idx) { return visible(els[idx]) && !item.value; }));
        })()
        """)
        for select in selects:
            options = [item.get("text", "") for item in select.get("options", []) if item.get("value")]
            label = select.get("label", "")
            answer = self._answer_for(label, answers, options=options)
            if not answer and ai_filler and label:
                answer = ai_filler.answer(label, options=options)
            self._choose_select(int(select["index"]), answer)

    def _fill_radios(self, answers: dict[str, str], ai_filler: AIFormFiller | None) -> None:
        fieldsets = self._json_js("""
        (function() {
            function visible(el) {
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var els = Array.from(root.querySelectorAll("fieldset"));
            return JSON.stringify(els.map(function(el, idx) {
                var checked = !!el.querySelector("input[type='radio']:checked");
                var legend = el.querySelector("legend, span[class*='label']");
                var options = Array.from(el.querySelectorAll("label")).map(function(lbl) {
                    return (lbl.innerText || lbl.textContent || "").trim();
                }).filter(Boolean);
                return {index: idx, label: legend ? (legend.innerText || legend.textContent || "") : el.innerText, checked: checked, options: options};
            }).filter(function(item, idx) { return visible(els[idx]) && !item.checked; }));
        })()
        """)
        for fieldset in fieldsets:
            label = fieldset.get("label", "")
            options = fieldset.get("options", [])
            answer = self._answer_for(label, answers, options=options)
            if not answer and ai_filler and label:
                answer = ai_filler.answer(label, options=options)
            self._choose_radio(int(fieldset["index"]), answer)

    def _set_text_field(self, index: int, value: str) -> None:
        self._js(f"""
        (function() {{
            function visible(el) {{
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }}
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var els = Array.from(root.querySelectorAll("input[type='text'], input[type='email'], input[type='tel'], input[type='number'], textarea")).filter(visible);
            var el = els[{index}];
            if (!el) return;
            el.focus();
            el.value = {json.dumps(value)};
            el.dispatchEvent(new Event("input", {{bubbles:true}}));
            el.dispatchEvent(new Event("change", {{bubbles:true}}));
        }})()
        """)

    def _choose_select(self, index: int, answer: str) -> None:
        self._js(f"""
        (function() {{
            function visible(el) {{
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }}
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var els = Array.from(root.querySelectorAll("select")).filter(visible);
            var el = els[{index}];
            if (!el) return;
            var wanted = {json.dumps((answer or "").lower())};
            for (var i = 0; i < el.options.length; i++) {{
                var opt = el.options[i];
                if (opt.value && wanted && opt.text.toLowerCase().indexOf(wanted) > -1) {{
                    el.selectedIndex = i;
                    el.dispatchEvent(new Event("change", {{bubbles:true}}));
                    return;
                }}
            }}
            for (var j = 0; j < el.options.length; j++) {{
                if (el.options[j].value) {{
                    el.selectedIndex = j;
                    el.dispatchEvent(new Event("change", {{bubbles:true}}));
                    return;
                }}
            }}
        }})()
        """)

    def _choose_radio(self, index: int, answer: str) -> None:
        self._js(f"""
        (function() {{
            function visible(el) {{
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }}
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']") || document;
            var fieldsets = Array.from(root.querySelectorAll("fieldset")).filter(visible);
            var fs = fieldsets[{index}];
            if (!fs) return;
            var wanted = {json.dumps((answer or "").lower())};
            var labels = Array.from(fs.querySelectorAll("label"));
            for (var i = 0; i < labels.length; i++) {{
                var text = (labels[i].innerText || labels[i].textContent || "").trim().toLowerCase();
                if (wanted && text.indexOf(wanted) > -1) {{
                    labels[i].click();
                    return;
                }}
            }}
            if (labels[0]) labels[0].click();
        }})()
        """)

    def _advance_or_submit(self, stop_before_submit: bool) -> str:
        stop = "true" if stop_before_submit else "false"
        return self._js(f"""
        (function() {{
            var root = document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog']");
            if (!root) return "no_modal";
            function visible(el) {{
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && !el.disabled;
            }}
            var buttons = Array.from(root.querySelectorAll("button")).filter(visible);
            function text(btn) {{
                return ((btn.innerText || btn.textContent || btn.getAttribute("aria-label") || "") + "").trim().toLowerCase();
            }}
            for (var i = 0; i < buttons.length; i++) {{
                var label = text(buttons[i]);
                if (label.indexOf("submit") > -1) {{
                    if ({stop}) return "prepared";
                    buttons[i].click();
                    return "submitted";
                }}
            }}
            for (var j = 0; j < buttons.length; j++) {{
                var review = text(buttons[j]);
                if (review.indexOf("review") > -1) {{
                    buttons[j].click();
                    return "review";
                }}
            }}
            for (var k = 0; k < buttons.length; k++) {{
                var next = text(buttons[k]);
                if (next.indexOf("next") > -1 || next.indexOf("continue") > -1) {{
                    buttons[k].click();
                    return next.indexOf("continue") > -1 ? "continue" : "next";
                }}
            }}
            return "no_button";
        }})()
        """)

    def _dismiss_success(self) -> None:
        self._js("""
        (function() {
            var buttons = Array.from(document.querySelectorAll("button"));
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || buttons[i].textContent || "").trim().toLowerCase();
                if (text === "done" || text === "dismiss" || text === "not now") {
                    buttons[i].click();
                    return;
                }
            }
        })()
        """)

    def _json_js(self, code: str) -> list[dict[str, Any]]:
        raw = self._js(code)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _load_profile_answers(self) -> dict[str, str]:
        return load_profile_answers(self.workspace)

    def _init_ai_filler(self) -> AIFormFiller | None:
        try:
            profile_text = load_profile(self.workspace)
            if not profile_text or profile_text.startswith("# Candidate Profile\n\nReplace this"):
                return None
            return AIFormFiller(profile_text=profile_text)
        except Exception as exc:
            logger.warning("AI form filler init failed: %s", exc)
            return None

    def _answer_for(self, label: str, answers: dict[str, str], options: list[str] | None = None) -> str:
        normalized = (label or "").lower()
        for key, value in answers.items():
            if key.lower() in normalized and value:
                return str(value)

        defaults = {
            "first name": answers.get("first_name", ""),
            "last name": answers.get("last_name", ""),
            "email": answers.get("email", ""),
            "phone": answers.get("phone", ""),
            "mobile": answers.get("phone", ""),
            "city": answers.get("city", ""),
            "location": answers.get("city", ""),
            "linkedin": answers.get("linkedin_url", ""),
            "github": answers.get("website", ""),
            "portfolio": answers.get("website", ""),
            "years": answers.get("years_experience", ""),
            "experience": answers.get("years_experience", ""),
            "sponsor": answers.get("sponsorship_needed", "No"),
            "visa": answers.get("sponsorship_needed", "No"),
            "authorized": answers.get("authorized_to_work", "Yes"),
            "legally": answers.get("authorized_to_work", "Yes"),
            "relocate": answers.get("willing_to_relocate", "Yes"),
            "notice": answers.get("notice_period", ""),
        }
        for key, value in defaults.items():
            if key in normalized and value:
                return str(value)

        if options:
            lower_options = [option.lower() for option in options]
            if ("yes" in lower_options or "yes " in " ".join(lower_options)) and (
                "authorized" in normalized or "legally" in normalized or "relocate" in normalized
            ):
                return "Yes"
            if ("no" in lower_options or "no " in " ".join(lower_options)) and (
                "sponsor" in normalized or "visa" in normalized
            ):
                return "No"

        if re.search(r"\byes\b.*\bno\b|\bno\b.*\byes\b", normalized):
            return "Yes"
        return ""

    def _as_applescript_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
