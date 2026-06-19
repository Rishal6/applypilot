#!/usr/bin/env python3
"""
LinkedIn Lead Hunter — Find jobs from posts, hashtags, hiring badges.
Extracts emails, drafts personalized outreach, saves to Excel.

Flow:
1. Search hashtags (#hiring #GenAI #AIjobs)
2. Scan posts for job opportunities + emails
3. Find people with hiring badges
4. AI drafts personalized email for each lead
5. Saves everything to Excel (leads.xlsx)
"""
import subprocess
import time
import json
import random
import re
import os
import csv
from datetime import datetime
from urllib.parse import quote

from .brain import ask_claude
from .runtime import log_file, output_dir, workspace
from ..career import load_career_profile
from ..config import load_preferences
from ..search_plan import build_search_plan, normalize

# ─── Config ───────────────────────────────────────────────────
HASHTAGS: list[str] = []

OUTPUT_DIR = str(output_dir())
LEADS_FILE = os.path.join(OUTPUT_DIR, "leads.csv")
LOG_FILE = str(log_file("leads"))
# ──────────────────────────────────────────────────────────────


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


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
    with open("/tmp/li_leads.js", "w") as f:
        f.write(code)
    try:
        r = subprocess.run(
            ['osascript', '-e',
             'tell application "Google Chrome" to tell active tab of window 1 to execute javascript (read POSIX file "/tmp/li_leads.js" as text)'],
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


def human_pause(lo, hi):
    time.sleep(random.uniform(lo, hi))


def scroll_feed(times=3):
    for _ in range(times):
        js('window.scrollBy(0, 800)')
        human_pause(2, 4)


def extract_emails(text):
    """Find all emails in text"""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    # Filter out common non-job emails
    filtered = [e for e in emails if not any(x in e.lower() for x in
                ['noreply', 'no-reply', 'support', 'info@linkedin', 'notifications'])]
    return filtered


def extract_phone(text):
    """Find phone numbers"""
    patterns = [
        r'\+91[\s-]?\d{5}[\s-]?\d{5}',
        r'\d{10}',
        r'\+\d{2}[\s-]?\d{5}[\s-]?\d{5}',
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group()
    return ""


def search_posts(query):
    """Search LinkedIn for posts matching query"""
    encoded = query.replace(' ', '%20').replace('#', '%23')
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded}&sortBy=%22date_posted%22"
    navigate(url)
    human_pause(4, 7)
    scroll_feed(3)

    # Extract post content
    code = """
    (function() {
        var posts = document.querySelectorAll('.feed-shared-update-v2, .update-components-text, [data-urn*="activity"]');
        var results = [];
        var seen = new Set();

        // Get all text blocks that look like posts
        var textBlocks = document.querySelectorAll('.feed-shared-text, .update-components-text__text-view, span[dir="ltr"]');
        for (var i = 0; i < textBlocks.length; i++) {
            var text = textBlocks[i].innerText.trim();
            if (text.length > 50 && text.length < 3000 && !seen.has(text.substring(0,50))) {
                seen.add(text.substring(0,50));

                // Find author name (nearby)
                var parent = textBlocks[i].closest('.feed-shared-update-v2, [data-urn]');
                var authorEl = parent ? parent.querySelector('.update-components-actor__name span, .feed-shared-actor__name span') : null;
                var author = authorEl ? authorEl.textContent.trim() : '';

                // Find author headline
                var headlineEl = parent ? parent.querySelector('.update-components-actor__description span, .feed-shared-actor__description span') : null;
                var headline = headlineEl ? headlineEl.textContent.trim() : '';

                // Find profile link
                var linkEl = parent ? parent.querySelector('a[href*="/in/"]') : null;
                var profileUrl = linkEl ? linkEl.href.split('?')[0] : '';

                results.push(author + '|||' + headline + '|||' + text.substring(0, 1000) + '|||' + profileUrl);
            }
        }
        return results.join('\\n===\\n');
    })()
    """
    raw = js_file(code)
    if not raw:
        return []

    posts = []
    for block in raw.split('\n===\n'):
        parts = block.split('|||')
        if len(parts) >= 3:
            posts.append({
                "author": parts[0].strip(),
                "headline": parts[1].strip() if len(parts) > 1 else "",
                "text": parts[2].strip() if len(parts) > 2 else "",
                "profile_url": parts[3].strip() if len(parts) > 3 else "",
            })
    return posts


def find_hiring_badges(query):
    """Search for people with #Hiring badge on their profile"""
    navigate(
        "https://www.linkedin.com/search/results/people/"
        f"?keywords={quote(query)}&openToHire=true"
    )
    human_pause(4, 7)
    scroll_feed(2)

    code = """
    (function() {
        var results = [];
        var cards = document.querySelectorAll('.entity-result, .reusable-search__result-container');
        for (var i = 0; i < Math.min(cards.length, 15); i++) {
            var card = cards[i];
            var nameEl = card.querySelector('.entity-result__title-text a span span, .app-aware-link span');
            var headlineEl = card.querySelector('.entity-result__primary-subtitle, .entity-result__summary');
            var locationEl = card.querySelector('.entity-result__secondary-subtitle');
            var linkEl = card.querySelector('a[href*="/in/"]');
            var hiringBadge = card.querySelector('[class*="hiring"], [aria-label*="hiring"]');

            var name = nameEl ? nameEl.textContent.trim() : '';
            var headline = headlineEl ? headlineEl.textContent.trim() : '';
            var location = locationEl ? locationEl.textContent.trim() : '';
            var url = linkEl ? linkEl.href.split('?')[0] : '';
            var isHiring = hiringBadge ? true : card.textContent.indexOf('Hiring') > -1;

            if (name && name.length > 2) {
                results.push(name + '|||' + headline + '|||' + location + '|||' + url + '|||' + (isHiring ? 'HIRING' : ''));
            }
        }
        return results.join('\\n');
    })()
    """
    raw = js_file(code)
    if not raw:
        return []

    people = []
    for line in raw.split('\n'):
        parts = line.split('|||')
        if len(parts) >= 4:
            people.append({
                "name": parts[0].strip(),
                "headline": parts[1].strip(),
                "location": parts[2].strip(),
                "profile_url": parts[3].strip(),
                "hiring": parts[4].strip() if len(parts) > 4 else "",
            })
    return people


def draft_email(lead):
    """AI drafts personalized outreach email for a lead"""
    profile = load_career_profile(workspace())
    prompt = f"""Write a SHORT outreach email (5-6 lines max) for a job opportunity.

Candidate: {profile.get('name') or 'Candidate'}
Target role: {profile.get('target') or 'Not provided'}
Skills: {', '.join(profile.get('skills') or []) or 'Not provided'}
Background: {profile.get('background') or 'Not provided'}
Location preference: {profile.get('location') or 'Not provided'}

Lead info:
- Person: {lead.get('author') or lead.get('name', 'Hiring Manager')}
- Their role: {lead.get('headline', '')}
- Post/context: {lead.get('text', '')[:200]}
- Email: {lead.get('email', '')}

Write a personalized, human email (not generic). Mention something specific from their post/role.
Format: Subject line first, then body. Keep it under 6 lines.
Sign with the candidate's name. Do not invent a phone number, employer, experience, achievement, or qualification.
Do NOT use bullet points. Write like a real person."""

    response = ask_claude(prompt)
    return response if response else ""


def is_job_post(text):
    """Check if a post is about hiring/jobs"""
    text_lower = text.lower()
    hiring_signals = [
        'hiring', 'we are looking', 'join our team', 'open position',
        'apply now', 'send resume', 'send cv', 'dm me', 'reach out',
        'immediate joiner', 'looking for', 'openings', 'vacancy',
        'job opportunity', 'we need', 'urgent requirement',
        'walk-in', 'interview scheduled', '#hiring',
    ]
    return any(signal in text_lower for signal in hiring_signals)


def is_relevant_job(text):
    """Check if the post overlaps the saved target roles or skills."""
    preferences = load_preferences(workspace())
    text_lower = normalize(text)
    if any(normalize(term) in text_lower for term in preferences.avoid_keywords):
        return False
    relevant_terms = preferences.target_roles + preferences.preferred_skills
    return any(normalize(term) in text_lower for term in relevant_terms if normalize(term))


def save_lead(lead):
    """Append lead to CSV file"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_exists = os.path.exists(LEADS_FILE)

    with open(LEADS_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'date', 'source', 'name', 'headline', 'email', 'phone',
            'profile_url', 'post_snippet', 'draft_email', 'status'
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'source': lead.get('source', 'hashtag'),
            'name': lead.get('author') or lead.get('name', ''),
            'headline': lead.get('headline', ''),
            'email': lead.get('email', ''),
            'phone': lead.get('phone', ''),
            'profile_url': lead.get('profile_url', ''),
            'post_snippet': (lead.get('text', '') or '')[:200],
            'draft_email': lead.get('draft_email', ''),
            'status': 'pending',
        })


def main():
    log("=" * 50)
    log("LinkedIn Lead Hunter")
    log("Hashtag search + Email extraction + Hiring badges")
    log("=" * 50)

    all_leads = []
    try:
        plan = build_search_plan(workspace(), max_queries=8)
    except ValueError as exc:
        log(f"Cannot search: {exc}")
        return
    queries = [f"hiring {item.keyword}" for item in plan]
    log("Profile lead plan: " + ", ".join(queries))

    # ─── Phase 1: Search hashtags for job posts ───
    log("\n--- Phase 1: Hashtag Search ---")

    for qi, query in enumerate(queries):
        log(f"\n[{qi+1}] Searching: '{query}'")
        posts = search_posts(query)
        log(f"  Found {len(posts)} posts")

        for post in posts:
            if not is_job_post(post['text']):
                continue
            if not is_relevant_job(post['text']):
                continue

            emails = extract_emails(post['text'])
            phone = extract_phone(post['text'])

            if emails or phone or post.get('profile_url'):
                lead = {
                    'source': 'hashtag',
                    'author': post['author'],
                    'headline': post['headline'],
                    'email': emails[0] if emails else '',
                    'phone': phone,
                    'profile_url': post['profile_url'],
                    'text': post['text'],
                }

                # Draft personalized email
                if emails:
                    log(f"  LEAD: {post['author']} | {emails[0]}")
                    draft = draft_email(lead)
                    lead['draft_email'] = draft
                else:
                    log(f"  LEAD: {post['author']} (no email, has profile)")
                    lead['draft_email'] = ''

                all_leads.append(lead)
                save_lead(lead)

        human_pause(8, 15)

    # ─── Phase 2: Find people with hiring badges ───
    log("\n--- Phase 2: Hiring Badge People ---")
    hiring_people = find_hiring_badges(plan[0].keyword)
    log(f"  Found {len(hiring_people)} people")

    for person in hiring_people:
        if person.get('hiring') or 'hiring' in person.get('headline', '').lower():
            lead = {
                'source': 'hiring_badge',
                'name': person['name'],
                'headline': person['headline'],
                'email': '',
                'phone': '',
                'profile_url': person['profile_url'],
                'text': f"Hiring badge - {person['headline']}",
            }
            log(f"  HIRING: {person['name']} | {person['headline'][:50]}")
            all_leads.append(lead)
            save_lead(lead)

    # ─── Summary ───
    log(f"\n{'='*50}")
    log(f"LEAD HUNT COMPLETE")
    log(f"{'='*50}")
    log(f"Total leads found: {len(all_leads)}")
    log(f"With email: {sum(1 for l in all_leads if l.get('email'))}")
    log(f"With profile: {sum(1 for l in all_leads if l.get('profile_url'))}")
    log(f"Drafts written: {sum(1 for l in all_leads if l.get('draft_email'))}")
    log(f"Saved to: {LEADS_FILE}")
    log(f"Log: {LOG_FILE}")

    # Print leads with emails (action items for you)
    email_leads = [l for l in all_leads if l.get('email')]
    if email_leads:
        log(f"\n--- LEADS WITH EMAILS (send these!) ---")
        for l in email_leads:
            log(f"\n  To: {l['email']}")
            log(f"  Person: {l.get('author') or l.get('name')}")
            log(f"  Context: {l.get('text', '')[:100]}...")
            if l.get('draft_email'):
                log(f"  Draft:\n{l['draft_email'][:300]}")


if __name__ == "__main__":
    main()
