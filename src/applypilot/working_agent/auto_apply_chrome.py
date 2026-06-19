#!/usr/bin/env python3
"""
LinkedIn Auto-Apply — Human-like Chrome automation.
Mimics real browsing: reads jobs, scrolls feed, takes breaks, types slowly.
"""
import subprocess
import time
import json
import random
import re
import os
from datetime import datetime
from urllib.parse import quote

from .brain import evaluate_job, answer_form_question
from .runtime import log_file, output_dir, workspace
from ..policy import load_policy
from ..search_plan import build_search_plan

# ─── Config ───────────────────────────────────────────────────
MAX_APPLIES_PER_SESSION = 999     # No limit — apply to all matches until all searches done
READING_TIME = (4, 12)            # Seconds spent "reading" a job description
BETWEEN_JOBS = (10, 25)           # Seconds between clicking different jobs
BETWEEN_SEARCHES = (15, 40)       # Seconds between search queries
SCROLL_PAUSE = (1.5, 4)           # Pause between scrolls
TYPING_DELAY = (0.03, 0.12)      # Delay per character when "typing"
FEED_BREAK_CHANCE = 0.25          # 25% chance to browse feed between jobs
FEED_BREAK_DURATION = (30, 90)   # How long to browse feed
# ──────────────────────────────────────────────────────────────

LOG_FILE = str(log_file("apply"))

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ─── Chrome helpers ───────────────────────────────────────────

def js(code, timeout=15):
    escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    try:
        r = subprocess.run(
            ['osascript', '-e',
             f'tell application "Google Chrome" to tell active tab of window 1 to execute javascript "{escaped}"'],
            capture_output=True, text=True, timeout=timeout
        )
        result = r.stdout.strip()
        return "" if result == "missing value" else result
    except subprocess.TimeoutExpired:
        return ""

def js_file(code, timeout=30):
    with open("/tmp/li_auto.js", "w") as f:
        f.write(code)
    try:
        r = subprocess.run(
            ['osascript', '-e',
             'tell application "Google Chrome" to tell active tab of window 1 to execute javascript (read POSIX file "/tmp/li_auto.js" as text)'],
            capture_output=True, text=True, timeout=timeout
        )
        result = r.stdout.strip()
        return "" if result == "missing value" else result
    except subprocess.TimeoutExpired:
        return ""

def navigate(url):
    subprocess.run(
        ['osascript', '-e',
         f'tell application "Google Chrome" to set URL of active tab of window 1 to "{url}"'],
        capture_output=True, text=True
    )


# ─── Human behaviour ─────────────────────────────────────────

def human_pause(lo, hi):
    """Sleep a random duration like a human would."""
    time.sleep(random.uniform(lo, hi))

def human_scroll(times=None):
    """Scroll like a person reading — variable speed, sometimes back up."""
    if times is None:
        times = random.randint(2, 5)
    for _ in range(times):
        px = random.randint(150, 500)
        # 15% chance to scroll back up a bit
        if random.random() < 0.15:
            px = -random.randint(50, 200)
        js(f'window.scrollBy(0, {px})')
        human_pause(*SCROLL_PAUSE)

def human_scroll_job_list(times=None):
    """Scroll the job sidebar list."""
    if times is None:
        times = random.randint(2, 4)
    for _ in range(times):
        px = random.randint(200, 600)
        js(f'var l=document.querySelector(".jobs-search-results-list,.scaffold-layout__list");if(l)l.scrollBy(0,{px})')
        human_pause(*SCROLL_PAUSE)

def browse_feed():
    """Take a break — go to LinkedIn feed, scroll around, come back."""
    log("  Taking a feed break (like a real human)...")
    navigate("https://www.linkedin.com/feed/")
    human_pause(5, 10)
    human_scroll(random.randint(3, 8))
    human_pause(*FEED_BREAK_DURATION)
    # Occasionally "like" something (just hover, don't actually click)
    human_scroll(random.randint(1, 3))

def check_rate_limit():
    """Check if LinkedIn is showing rate limit signals."""
    text = js('document.body ? document.body.textContent.substring(0, 5000) : ""')
    if '429' in text or 'rate limit' in text.lower() or "let's do a quick security check" in text.lower():
        return True
    return False


# ─── Job extraction ──────────────────────────────────────────

def wait_for_cards(max_wait=20):
    for _ in range(max_wait // 3):
        human_pause(2, 4)
        try:
            count = js('document.querySelectorAll(".scaffold-layout__list-item, li.ember-view.occludable-update").length.toString()')
        except Exception:
            continue
        if count and count.isdigit() and int(count) > 0:
            return int(count)
    return 0

def get_job_cards():
    code = """
    (function() {
        var cards = document.querySelectorAll('.scaffold-layout__list-item, li.ember-view.occludable-update');
        var results = [];
        for (var i = 0; i < cards.length; i++) {
            var card = cards[i];
            var titleEl = card.querySelector('a.job-card-container__link, a.job-card-list__title--link, a[class*="job-card"]');
            var companyEl = card.querySelector('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description');
            var locationEl = card.querySelector('.artdeco-entity-lockup__caption, .job-card-container__metadata-item');
            var title = titleEl ? titleEl.textContent.trim().replace(/\\s+/g,' ').substring(0, 100) : '';
            var href = titleEl ? titleEl.href : '';
            var company = companyEl ? companyEl.textContent.trim().replace(/\\s+/g,' ').substring(0, 80) : '';
            var location = locationEl ? locationEl.textContent.trim().replace(/\\s+/g,' ').substring(0, 80) : '';
            var isEasy = card.textContent.indexOf('Easy Apply') > -1;
            if (title) {
                results.push(title + '|||' + company + '|||' + location + '|||' + (isEasy ? '1' : '0') + '|||' + i.toString() + '|||' + href);
            }
        }
        return results.join('\\n');
    })()
    """
    raw = js_file(code)
    if not raw:
        return []
    jobs = []
    for line in raw.split('\n'):
        parts = line.split('|||')
        if len(parts) >= 5:
            jobs.append({
                'title': parts[0], 'company': parts[1],
                'location': parts[2], 'easy_apply': parts[3] == '1',
                'index': int(parts[4]),
                'url': parts[5] if len(parts) > 5 else '',
            })
    return jobs

def get_job_description():
    """Wait for and return job description text."""
    # Scroll the detail pane to trigger lazy loading
    js('var d=document.querySelector(".scaffold-layout__detail,.jobs-search__job-details");if(d)d.scrollBy(0,200)')
    for _ in range(8):
        desc = js_file("""
        (function() {
            var selectors = [
                ".jobs-description",
                ".jobs-description__container",
                ".jobs-description__content",
                ".jobs-box__html-content",
                "#job-details",
                ".jobs-description-content",
                ".jobs-unified-description",
                "[class*='jobs-description']",
                "[class*='jobs-box__html-content']"
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = document.querySelector(selectors[i]);
                if (el && el.innerText && el.innerText.trim().length > 30) {
                    return el.innerText.trim().substring(0, 3000);
                }
            }
            var body = document.body ? document.body.innerText : "";
            var idx = body.indexOf("About the job");
            if (idx > -1) {
                return body.substring(idx, idx + 3000).trim();
            }
            return "";
        })()
        """)
        if desc and len(desc) > 30:
            return desc
        time.sleep(1.5)
    # Try the detail pane itself
    desc = js('var el = document.querySelector(".scaffold-layout__detail, .jobs-search__job-details"); el ? el.textContent.trim().substring(0, 3000) : ""')
    if desc and len(desc) > 50:
        return desc
    return ""


def get_job_unavailable_reason():
    """Return a LinkedIn page-state reason that means submitting is impossible."""
    text = js('document.body ? document.body.innerText.substring(0, 6000) : ""').lower()
    if "no longer accepting applications" in text:
        return "No longer accepting applications"
    if "this job is no longer available" in text or "job is no longer available" in text:
        return "Job is no longer available"
    if "you've already applied" in text or "you have already applied" in text:
        return "Already applied"
    return ""


# ─── Apply flow ───────────────────────────────────────────────

def click_job_card(index):
    # Click the card container to load detail in split-pane (NOT the <a> which navigates away)
    result = js_file(f"""(function() {{
        var cards = document.querySelectorAll('.scaffold-layout__list-item, li.ember-view.occludable-update');
        if (!cards[{index}]) return 'no_card_at_' + {index};
        var card = cards[{index}];
        // Scroll card into view
        card.scrollIntoView({{block:'center'}});
        // Click the card container itself (not the <a> link which navigates away)
        var clickTarget = card.querySelector('.job-card-container, .job-card-list, [data-job-id]') || card;
        clickTarget.click();
        // Also fire pointer events for React/Ember handlers
        ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(evt) {{
            clickTarget.dispatchEvent(new MouseEvent(evt, {{bubbles:true, view:window}}));
        }});
        return 'clicked_card_' + {index};
    }})()""")
    log(f"  Card click: {result}")
    human_pause(2, 5)

def click_easy_apply():
    code = """
    (function() {
        var allBtns = document.querySelectorAll('button');
        // Priority 1: button with aria-label "Easy Apply to ..." (most reliable)
        for (var i = 0; i < allBtns.length; i++) {
            var aria = allBtns[i].getAttribute('aria-label') || '';
            if (aria.indexOf('Easy Apply to') > -1 && !allBtns[i].disabled) {
                var rect = allBtns[i].getBoundingClientRect();
                if (rect.y > 0 && rect.width > 0) {
                    allBtns[i].click();
                    return 'clicked:aria';
                }
            }
        }
        // Priority 2: button with jobs-apply-button in class (skip filter pills)
        for (var i = 0; i < allBtns.length; i++) {
            var cls = allBtns[i].className || '';
            if (cls.indexOf('jobs-apply-button') > -1 && cls.indexOf('artdeco-pill') === -1) {
                var rect = allBtns[i].getBoundingClientRect();
                if (rect.y > 0 && rect.width > 0 && !allBtns[i].disabled) {
                    allBtns[i].click();
                    return 'clicked:class';
                }
            }
        }
        // Priority 3: "Easy Apply" text inside detail pane only (not filter bar)
        var detail = document.querySelector('.scaffold-layout__detail, .jobs-search__job-details, .job-view-layout');
        if (detail) {
            var dbtns = detail.querySelectorAll('button');
            for (var i = 0; i < dbtns.length; i++) {
                var txt = dbtns[i].textContent.trim();
                if ((txt === 'Easy Apply' || txt === 'Apply') && !dbtns[i].disabled) {
                    dbtns[i].click();
                    return 'clicked:detail';
                }
            }
        }
        // Priority 4: any non-pill button with Easy Apply text, y > 100
        for (var i = 0; i < allBtns.length; i++) {
            var txt = allBtns[i].textContent.trim();
            var cls = allBtns[i].className || '';
            if (txt === 'Easy Apply' && cls.indexOf('artdeco-pill') === -1 && !allBtns[i].disabled) {
                var rect = allBtns[i].getBoundingClientRect();
                if (rect.y > 100 && rect.width > 0) {
                    allBtns[i].click();
                    return 'clicked:fallback';
                }
            }
        }
        return 'not_found';
    })()
    """
    result = js_file(code)
    log(f"  Easy Apply click: {result}")
    return result and result.startswith('clicked')

def fill_form_and_advance():
    human_pause(1.5, 3)

    modal = js('document.querySelector(".jobs-easy-apply-modal, .artdeco-modal") ? "open" : "closed"')
    if modal != 'open':
        return 'no_modal'

    fields_code = """
    (function() {
        var results = [];
        var inputs = document.querySelectorAll('.jobs-easy-apply-modal input[type="text"], .jobs-easy-apply-modal input[type="tel"], .jobs-easy-apply-modal input[type="email"], .jobs-easy-apply-modal input[type="number"]');
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            var label = '';
            var labelEl = inp.closest('.fb-dash-form-element') ? inp.closest('.fb-dash-form-element').querySelector('label, span.fb-dash-form-element__label') : null;
            if (!labelEl) labelEl = document.querySelector('label[for="' + inp.id + '"]');
            if (labelEl) label = labelEl.textContent.trim();
            var isNumeric = inp.id.indexOf('numeric') > -1 ? 'NUMERIC' : 'INPUT';
            results.push(isNumeric + '|||' + inp.id + '|||' + label + '|||' + inp.value);
        }
        var radios = document.querySelectorAll('.jobs-easy-apply-modal fieldset');
        for (var i = 0; i < radios.length; i++) {
            var fs = radios[i];
            var legend = fs.querySelector('legend, span[class*="label"]');
            var legendText = legend ? legend.textContent.trim() : '';
            var opts = fs.querySelectorAll('input[type="radio"]');
            var optTexts = [];
            for (var j = 0; j < opts.length; j++) {
                optTexts.push(opts[j].parentElement.textContent.trim());
            }
            if (legendText) results.push('RADIO|||' + i + '|||' + legendText + '|||' + optTexts.join(','));
        }
        var selects = document.querySelectorAll('.jobs-easy-apply-modal select');
        for (var i = 0; i < selects.length; i++) {
            var sel = selects[i];
            var label = '';
            var labelEl = sel.closest('.fb-dash-form-element') ? sel.closest('.fb-dash-form-element').querySelector('label') : null;
            if (labelEl) label = labelEl.textContent.trim();
            var opts = [];
            for (var j = 0; j < sel.options.length; j++) {
                if (sel.options[j].value) opts.push(sel.options[j].text);
            }
            results.push('SELECT|||' + sel.id + '|||' + label + '|||' + opts.join(','));
        }
        return results.join('\\n');
    })()
    """
    fields_raw = js_file(fields_code)

    if fields_raw:
        for line in fields_raw.split('\n'):
            parts = line.split('|||')
            if len(parts) < 4:
                continue
            ftype, fid, label, current = parts[0], parts[1], parts[2], parts[3]

            if ftype == 'NUMERIC' and not current:
                answer = answer_form_question(label + " (answer with ONLY a number, no text)")
                if answer:
                    nums = re.findall(r'[\d.]+', answer)
                    num_val = nums[0] if nums else '3'
                    js(f'var el=document.getElementById("{fid}");if(el){{el.value="{num_val}";el.dispatchEvent(new Event("input",{{bubbles:true}}));el.dispatchEvent(new Event("change",{{bubbles:true}}));}}')
                    human_pause(0.3, 0.8)

            elif ftype == 'INPUT' and not current:
                answer = answer_form_question(label)
                if answer:
                    safe = answer.replace("'", "\\'").replace('"', '\\"')
                    # Type character by character like a human
                    js(f'var el=document.getElementById("{fid}");if(el){{el.focus();el.value="";}}')
                    for ch in safe:
                        escaped_ch = ch.replace('\\', '\\\\').replace('"', '\\"')
                        js(f'var el=document.getElementById("{fid}");if(el){{el.value+="{escaped_ch}";el.dispatchEvent(new Event("input",{{bubbles:true}}));}}')
                        time.sleep(random.uniform(*TYPING_DELAY))
                    js(f'var el=document.getElementById("{fid}");if(el)el.dispatchEvent(new Event("change",{{bubbles:true}}))')
                    human_pause(0.3, 0.8)

            elif ftype == 'RADIO':
                options = current.split(',')
                answer = answer_form_question(label, options)
                if answer:
                    safe = answer.replace("'", "\\'")
                    js_file(f"""(function(){{var fs=document.querySelectorAll('.jobs-easy-apply-modal fieldset')[{fid}];if(!fs)return;var rs=fs.querySelectorAll('input[type="radio"]');for(var i=0;i<rs.length;i++){{if(rs[i].parentElement.textContent.trim().indexOf('{safe}')>-1){{rs[i].click();return;}}}}if(rs[0])rs[0].click();}})()""")
                    human_pause(0.5, 1.2)

            elif ftype == 'SELECT':
                options = current.split(',')
                answer = answer_form_question(label, options)
                if answer:
                    safe = answer.replace("'", "\\'")
                    js_file(f"""(function(){{var sel=document.getElementById('{fid}');if(!sel)return;for(var i=0;i<sel.options.length;i++){{if(sel.options[i].text.indexOf('{safe}')>-1){{sel.selectedIndex=i;sel.dispatchEvent(new Event('change',{{bubbles:true}}));return;}}}}}})()""")
                    human_pause(0.5, 1.0)

    human_pause(1, 2)

    # Click Submit > Review > Next
    button_code = """
    (function() {
        var modal = document.querySelector('.jobs-easy-apply-modal, .artdeco-modal');
        if (!modal) return 'no_modal';
        var buttons = modal.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
            var txt = buttons[i].textContent.trim().toLowerCase();
            if (txt.indexOf('submit') > -1) {
                buttons[i].click(); return 'submitted';
            }
        }
        for (var i = 0; i < buttons.length; i++) {
            var txt = buttons[i].textContent.trim().toLowerCase();
            if (txt.indexOf('review') > -1) {
                buttons[i].click(); return 'review';
            }
        }
        for (var i = 0; i < buttons.length; i++) {
            var txt = buttons[i].textContent.trim().toLowerCase();
            if (txt === 'next' || txt.indexOf('next') > -1 || txt.indexOf('continue') > -1) {
                buttons[i].click(); return 'next';
            }
        }
        return 'no_button';
    })()
    """
    result = js_file(button_code)
    return result or 'unknown'

def close_modal():
    js('var btn=document.querySelector(".artdeco-modal__dismiss,.jobs-easy-apply-modal button[aria-label*=\\"Dismiss\\"]");if(btn)btn.click()')
    human_pause(1, 2)
    js('var bs=document.querySelectorAll("button");for(var i=0;i<bs.length;i++){if(bs[i].textContent.trim()==="Discard"){bs[i].click();break;}}')
    human_pause(1, 2)

def apply_to_url_job_detail(url, title="", company="", pre_scored=False):
    """Apply to a direct job URL and return a structured status."""
    log(f"  Opening URL job: {title[:50]} @ {company}")
    navigate(url)
    human_pause(4, 7)

    unavailable = get_job_unavailable_reason()
    if unavailable:
        log(f"  {unavailable}")
        status = 'applied' if unavailable == "Already applied" else 'skipped'
        return {'status': status, 'reason': unavailable}

    desc = get_job_description()
    if not desc:
        human_pause(3, 5)
        desc = get_job_description()
    if not desc:
        desc = f"Job: {title} at {company}"
        log("  No description found; continuing with title/company")

    read_time = random.uniform(*READING_TIME)
    log(f"  Reading ({read_time:.0f}s)...")
    human_scroll(random.randint(1, 3))
    time.sleep(read_time)

    # Check title from page if not provided
    if not title:
        title = js('var el=document.querySelector(".jobs-unified-top-card__job-title, .t-24.t-bold");el?el.textContent.trim():""') or "Unknown"
    if not company:
        company = js('var el=document.querySelector(".jobs-unified-top-card__company-name, a[class*=\\"company\\"]");el?el.textContent.trim():""') or "Unknown"

    location = js('var el=document.querySelector(".jobs-unified-top-card__bullet, .t-black--light");el?el.textContent.trim():""') or ""

    if pre_scored:
        log("  Already scored by service; trying Easy Apply")
    else:
        evaluation = evaluate_job(title, company, desc, location)
        score = evaluation.get('score', 0)
        log(f"  Score: {score}/100 — {evaluation.get('reason', '')[:80]}")

        if not evaluation.get('apply'):
            log(f"  Not a match (requires {evaluation.get('minimum_score', 70)}+)")
            return {'status': 'skipped', 'reason': 'Score below profile policy threshold'}

    # Wait for apply button to load on the job page
    for wait in range(8):
        unavailable = get_job_unavailable_reason()
        if unavailable:
            log(f"  {unavailable}")
            status = 'applied' if unavailable == "Already applied" else 'skipped'
            return {'status': status, 'reason': unavailable}
        found = js_file("""(function(){
            var bs=document.querySelectorAll('button');
            for(var i=0;i<bs.length;i++){
                var a=bs[i].getAttribute('aria-label')||'';
                if(a.indexOf('Easy Apply to')>-1) return 'ready';
                var c=bs[i].className||'';
                if(c.indexOf('jobs-apply-button')>-1 && c.indexOf('artdeco-pill')===-1) return 'ready';
            }
            return 'waiting';
        })()""")
        if found == 'ready':
            break
        time.sleep(1.5)

    for attempt in range(3):
        if click_easy_apply():
            break
        human_pause(2, 4)
    else:
        log("  No Easy Apply button")
        return {'status': 'skipped', 'reason': 'No Easy Apply button'}

    human_pause(2, 4)

    for step in range(15):
        result = fill_form_and_advance()
        log(f"  Step {step+1}: {result}")
        if result == 'submitted':
            log("  >> SUBMITTED!")
            human_pause(2, 4)
            js('var bs=document.querySelectorAll("button");for(var i=0;i<bs.length;i++){var t=bs[i].textContent.trim().toLowerCase();if(t==="done"||t==="dismiss"||t==="not now"){bs[i].click();break;}}')
            return {'status': 'applied', 'reason': 'Submitted via active Chrome'}
        elif result in ('no_modal', 'no_button'):
            log(f"  Failed: {result}")
            close_modal()
            return {'status': 'failed', 'reason': result}
        human_pause(2, 5)

    log("  Too many steps")
    close_modal()
    return {'status': 'failed', 'reason': 'Too many form steps'}


def apply_to_url_job(url, title="", company=""):
    """Apply to a job by navigating directly to its URL (from feed scanner leads)."""
    return apply_to_url_job_detail(url, title, company).get('status') == 'applied'

def apply_to_job(job, search_url=""):
    log(f"  Opening: {job['title'][:50]} @ {job['company']}")

    # Evaluate based on title + company first (fast, no navigation needed)
    eval_text = f"Job: {job['title']} at {job['company']} in {job['location']}"
    evaluation = evaluate_job(job['title'], job['company'], eval_text, job['location'])
    score = evaluation.get('score', 0)
    should_apply = evaluation.get('apply', False)
    log(f"  Score: {score}/100 — {evaluation.get('reason', '')[:80]}")

    if not should_apply:
        log(f"  Not a match (requires {evaluation.get('minimum_score', 70)}+), moving on")
        return False

    # Good match — click the card in the list (stays on search page with split-pane)
    click_job_card(job['index'])
    human_pause(3, 5)

    # Wait for apply button to appear in the detail pane
    for wait_i in range(12):
        found = js_file("""(function(){
            var bs=document.querySelectorAll('button');
            for(var i=0;i<bs.length;i++){
                var a=bs[i].getAttribute('aria-label')||'';
                if(a.indexOf('Easy Apply to')>-1) {
                    var r=bs[i].getBoundingClientRect();
                    if(r.y>0 && r.width>0) return 'ready:aria';
                }
                var c=bs[i].className||'';
                if(c.indexOf('jobs-apply-button')>-1 && c.indexOf('artdeco-pill')===-1) {
                    var r=bs[i].getBoundingClientRect();
                    if(r.y>0 && r.width>0) return 'ready:class';
                }
            }
            // Check if detail pane loaded at all
            var detail=document.querySelector('.scaffold-layout__detail, .jobs-search__job-details');
            return detail ? 'waiting:detail_loaded' : 'waiting:no_detail';
        })()""")
        if found and found.startswith('ready'):
            log(f"  Button found: {found} (wait {wait_i+1})")
            break
        if wait_i == 5:
            log(f"  Still waiting for button... ({found})")
        time.sleep(1.5)

    # Click Easy Apply
    for attempt in range(3):
        if click_easy_apply():
            break
        human_pause(2, 4)
    else:
        log("  Easy Apply button not found")
        return False

    human_pause(3, 5)

    # Check if we got a modal (search page) or navigated to a new page
    modal = js('document.querySelector(".jobs-easy-apply-modal, .artdeco-modal, [role=\'dialog\']") ? "open" : "closed"')

    if modal == 'open':
        # Modal-based Easy Apply — walk through form steps
        for step in range(15):
            result = fill_form_and_advance()
            log(f"  Form step {step+1}: {result}")

            if result == 'submitted':
                log("  >> APPLICATION SUBMITTED!")
                human_pause(2, 4)
                js('var bs=document.querySelectorAll("button");for(var i=0;i<bs.length;i++){var t=bs[i].textContent.trim().toLowerCase();if(t==="done"||t==="dismiss"||t==="not now"){bs[i].click();break;}}')
                return True
            elif result == 'no_modal':
                log("  Modal closed unexpectedly")
                return False
            elif result == 'no_button':
                log("  Stuck — no button found, closing")
                close_modal()
                return False

            human_pause(2, 5)

        log("  Too many steps, closing modal")
        close_modal()
        return False
    else:
        # Page-based Easy Apply — check if we're on a new apply page
        current_url = js('window.location.href')
        if current_url and ('apply' in current_url.lower() or 'easy' in current_url.lower()):
            log("  Redirected to apply page, attempting form fill...")
            # Try the same form fill flow
            for step in range(8):
                result = fill_form_and_advance()
                log(f"  Form step {step+1}: {result}")
                if result == 'submitted':
                    log("  >> APPLICATION SUBMITTED!")
                    return True
                elif result in ('no_modal', 'no_button'):
                    break
                human_pause(2, 5)
        else:
            log("  No modal or apply page opened")
        return False


# ─── Main loop ────────────────────────────────────────────────

def main():
    log("=" * 50)
    log("LinkedIn Auto-Apply (Human Mode)")
    log("=" * 50)

    seen = set()
    applied = 0
    skipped = 0

    try:
        searches = build_search_plan(workspace())
    except ValueError as exc:
        log(f"Cannot search: {exc}")
        return
    policy = load_policy(workspace())
    session_limit = policy.max_applications_per_day
    log("Profile search plan: " + ", ".join(item.keyword for item in searches))
    log(f"Application gate: score >= {policy.min_score_to_submit}, daily limit {session_limit}")

    for qi, search in enumerate(searches):
        query = search.keyword
        remote_only = search.remote_only
        time_filter = search.time_filter
        if applied >= session_limit:
            log(f"Hit daily limit ({session_limit}), stopping.")
            break

        # Rate limit check
        if check_rate_limit():
            wait = random.uniform(300, 600)
            log(f"Rate limit detected! Waiting {wait/60:.0f} min...")
            time.sleep(wait)
            if check_rate_limit():
                log("Still rate-limited, stopping for today.")
                break

        tag = "remote" if remote_only else "any"
        time_tag = f", past {'24h' if time_filter == 'r86400' else 'week'}" if time_filter else ""
        log(f"\n[{qi+1}/{len(searches)}] Searching: '{query}' ({tag}{time_tag})")

        wt = "&f_WT=2" if remote_only else ""
        tpr = f"&f_TPR={time_filter}" if time_filter else ""
        location = f"&location={quote(search.location)}" if search.location else ""
        url = f"https://www.linkedin.com/jobs/search/?f_AL=true{wt}{tpr}{location}&keywords={quote(query)}&sortBy=DD"
        navigate(url)

        card_count = wait_for_cards(15)
        if card_count == 0:
            log("No results, next query")
            human_pause(5, 15)
            continue

        # Scroll the list like browsing
        human_scroll_job_list(random.randint(2, 5))
        human_pause(2, 4)

        jobs = get_job_cards()
        easy = [j for j in jobs if j['easy_apply']]
        log(f"Found {len(easy)} Easy Apply jobs out of {len(jobs)} total")

        for job in easy:
            if applied >= session_limit:
                break

            key = (job['title'][:50] + job['company'][:30]).lower()
            if key in seen:
                continue
            seen.add(key)

            log(f"\n--- {job['title'][:55]} @ {job['company']}")

            success = apply_to_job(job, search_url=url)
            if success:
                applied += 1
                log(f"  Total applied so far: {applied}")
            else:
                skipped += 1

            # Navigate back to search results for next job
            navigate(url)
            human_pause(3, 5)

            # Human-like gap between jobs
            wait = random.uniform(*BETWEEN_JOBS)
            log(f"  Pausing {wait:.0f}s before next job...")
            time.sleep(wait)

            # Occasionally browse feed
            if random.random() < FEED_BREAK_CHANCE:
                browse_feed()
                # Navigate back to search
                navigate(url)
                wait_for_cards(10)

        # Gap between searches
        gap = random.uniform(*BETWEEN_SEARCHES)
        log(f"Waiting {gap:.0f}s before next search...")
        time.sleep(gap)

    # ─── Phase 2: Apply to leads from Feed Scanner ─────────
    leads_file = str(output_dir() / "feed_leads.json")
    if os.path.exists(leads_file) and applied < session_limit:
        log("\n" + "=" * 50)
        log("Phase 2: Applying to Feed Scanner leads")
        try:
            with open(leads_file) as f:
                leads = json.load(f)
            url_leads = [l for l in leads if l.get('easy_apply') and l.get('url')]
            log(f"Found {len(url_leads)} Easy Apply leads from scanner")

            for lead in url_leads:
                if applied >= session_limit:
                    break
                key = (lead.get('title','')[:50] + lead.get('company','')[:30]).lower()
                if key in seen:
                    continue
                seen.add(key)

                log(f"\n--- {lead.get('title','')[:55]} @ {lead.get('company','')}")
                success = apply_to_url_job(
                    lead['url'],
                    lead.get('title', ''),
                    lead.get('company', '')
                )
                if success:
                    applied += 1
                else:
                    skipped += 1

                wait = random.uniform(*BETWEEN_JOBS)
                log(f"  Pausing {wait:.0f}s...")
                time.sleep(wait)

                if random.random() < FEED_BREAK_CHANCE:
                    browse_feed()
        except Exception as e:
            log(f"Error processing leads: {e}")

    log(f"\n{'='*50}")
    log(f"SESSION COMPLETE — Applied: {applied}, Skipped: {skipped}")
    log(f"Log saved to: {LOG_FILE}")

if __name__ == "__main__":
    main()
