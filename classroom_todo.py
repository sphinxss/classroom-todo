#!/usr/bin/env python3
"""Build a prioritized to-do list from your Google Classroom coursework.

First run opens a browser for Google sign-in and caches a token in token.json.
Run it again any time to refresh TODO.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN = BASE / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    # Read-write coursework scope: the readonly variant is not always offered in
    # the Cloud console scope picker, so this is the compatible choice. The script
    # only ever calls read-only list endpoints.
    "https://www.googleapis.com/auth/classroom.coursework.me",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
]

DONE_STATES = {"TURNED_IN", "RETURNED"}

# Classroom course name -> label shown in the list. Edit freely.
COURSE_LABELS = {
    "BSIT-BT 4-1 COMP 023 Social and Professional Issues in Computing": "COMP 023 - Social and Professional Issues in Computing",
    "IT Elective 4 (IT Elective 4)": "IT Elective 4 (ELEC IT-E4)",
    "INTE 30073 Information Assurance and Security": "INTE 401 - Information Assurance and Security 2",
}

# Preferred section order for --group course. Unlisted courses sort last, A-Z.
COURSE_ORDER = [
    "COMP 023",
    "IT Elective 4",
    "GEED 007",
    "INTE 401",
    "INTE 402",
    "INTE 403",
]


# ---------------------------------------------------------------- auth


def get_credentials(interactive=True):
    """Load cached credentials or run the installed-app OAuth flow."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            sys.exit(
                "Saved login is missing or expired.\n"
                "Run run.bat manually (without --noninteractive) to sign in again."
            )
        if not CLIENT_SECRET.exists():
            sys.exit(
                f"\nMissing {CLIENT_SECRET}\n\n"
                "Download your OAuth *Desktop app* client from Google Cloud Console,\n"
                "rename it to client_secret.json, and put it here:\n"
                f"  {CLIENT_SECRET}\n\n"
                "See SETUP.md for the full walkthrough.\n"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")

    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


# ------------------------------------------------------------ fetching


def fetch_courses(service):
    courses = []
    page_token = None
    while True:
        resp = (
            service.courses()
            .list(studentId="me", courseStates=["ACTIVE"], pageSize=100, pageToken=page_token)
            .execute()
        )
        courses.extend(resp.get("courses", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return courses


def fetch_coursework(service, course_id):
    items = []
    page_token = None
    while True:
        resp = (
            service.courses()
            .courseWork()
            .list(
                courseId=course_id,
                courseWorkStates=["PUBLISHED"],
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(resp.get("courseWork", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return items


def fetch_submission(service, course_id, coursework_id):
    """Return the student's submission state, or None if not available (e.g. teacher)."""
    try:
        resp = (
            service.courses()
            .courseWork()
            .studentSubmissions()
            .list(courseId=course_id, courseWorkId=coursework_id, userId="me")
            .execute()
        )
        subs = resp.get("studentSubmissions", [])
        return subs[0].get("state") if subs else None
    except Exception:
        return None


# ------------------------------------------------------------ shaping


def parse_due(item):
    due = item.get("dueDate")
    if not due:
        return None
    clock = item.get("dueTime") or {}
    # Classroom stores dueDate/dueTime in UTC.
    dt = datetime(
        due["year"],
        due["month"],
        due["day"],
        clock.get("hours", 23),
        clock.get("minutes", 59),
        tzinfo=timezone.utc,
    )
    return dt.astimezone()


def collect(service, include_done, since=None):
    tasks = []
    completed = 0
    courses = fetch_courses(service)
    print(f"Found {len(courses)} active course(s).")

    for course in courses:
        raw_name = " ".join(course.get("name", "(untitled course)").split())
        name = COURSE_LABELS.get(raw_name, raw_name)
        try:
            work = fetch_coursework(service, course["id"])
        except Exception as exc:
            print(f"  ! {name}: could not list coursework ({exc})")
            continue

        for item in work:
            state = fetch_submission(service, course["id"], item["id"])
            done = state in DONE_STATES
            if done:
                completed += 1
                if not include_done:
                    continue

            due = parse_due(item)
            tasks.append(
                {
                    "course": name,
                    "course_id": course["id"],
                    "title": item.get("title", "(untitled)"),
                    "type": item.get("workType", "ASSIGNMENT"),
                    "due": due.isoformat() if due else None,
                    "due_dt": due,
                    "state": state,
                    "done": done,
                    "late": bool(due and due < datetime.now().astimezone() and not done),
                    "link": item.get("alternateLink"),
                    "points": item.get("maxPoints"),
                }
            )

    if since:
        tasks = [t for t in tasks if t["due_dt"] is None or t["due_dt"] >= since]

    tasks.sort(key=lambda t: (t["due_dt"] is None, t["due_dt"] or datetime.max.replace(tzinfo=timezone.utc)))
    return tasks, completed


def bucket(task, now):
    if task["done"]:
        return "done"
    due = task["due_dt"]
    if due is None:
        return "nodate"
    if due < now:
        return "overdue"
    if due.date() == now.date():
        return "today"
    if due <= now + timedelta(days=7):
        return "week"
    return "later"


BUCKETS = [
    ("overdue", "Overdue", "red"),
    ("today", "Due today", "orange"),
    ("week", "Next 7 days", "yellow"),
    ("later", "Later", "blue"),
    ("nodate", "No due date", "grey"),
    ("done", "Completed", "green"),
]


def fmt_due(due, now):
    if due is None:
        return "no due date"
    clock = due.strftime("%I:%M %p").lstrip("0")
    days = (due.date() - now.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if days == -1:
        return f"yesterday at {clock}"
    if due.year != now.year:
        return f"{due.strftime('%a %b')} {due.day}, {due.year}, {clock}"
    return f"{due.strftime('%a %b')} {due.day}, {clock}"


def course_sort_key(name):
    upper = name.upper()
    for index, prefix in enumerate(COURSE_ORDER):
        if upper.startswith(prefix.upper()):
            return (index, name)
    return (len(COURSE_ORDER), name)


def task_line(t, now, show_course=True):
    box = "[x]" if t["done"] else "[ ]"
    title = f"[{t['title']}]({t['link']})" if t.get("link") else f"**{t['title']}**"
    meta = [fmt_due(t["due_dt"], now)]
    if show_course:
        meta.insert(0, t["course"])
    if t["type"] not in ("ASSIGNMENT", "COURSE_WORK_TYPE_UNSPECIFIED"):
        meta.append(t["type"].replace("_", " ").title())
    if t.get("points"):
        meta.append(f"{t['points']:g} pts")
    if t["late"]:
        meta.append("**LATE**")
    if t.get("state") == "CREATED" and not t["done"]:
        meta.append("started")
    return f"- {box} {title}  \n  {' | '.join(meta)}"


def render_markdown(tasks, now, out_path, completed=0, group="urgency"):
    open_tasks = [t for t in tasks if not t["done"]]
    overdue = sum(1 for t in open_tasks if t["late"])

    lines = [
        "# Google Classroom To-Do",
        "",
        f"_Updated {now.strftime('%a %b %d, %Y %I:%M %p')} | "
        f"{len(open_tasks)} open | {overdue} overdue | "
        f"{completed} completed_",
        "",
    ]

    if group == "course":
        by_course = {}
        for t in open_tasks:
            by_course.setdefault(t["course"], []).append(t)
        for name in sorted(by_course, key=course_sort_key):
            items = by_course[name]
            late = sum(1 for t in items if t["late"])
            suffix = f", {late} overdue" if late else ""
            lines.append(f"## {name} ({len(items)}{suffix})")
            lines.append("")
            for t in items:
                lines.append(task_line(t, now, show_course=False))
            lines.append("")
    else:
        by_course = {}
        for t in open_tasks:
            by_course[t["course"]] = by_course.get(t["course"], 0) + 1
        if by_course:
            lines.append("**Open by course:** " + " | ".join(f"{k} ({v})" for k, v in sorted(by_course.items())))
            lines.append("")

        for key, heading, _color in BUCKETS:
            if key == "done":
                continue
            group_tasks = [t for t in tasks if bucket(t, now) == key]
            if not group_tasks:
                continue
            lines.append(f"## {heading} ({len(group_tasks)})")
            lines.append("")
            for t in group_tasks:
                lines.append(task_line(t, now))
            lines.append("")

    done_tasks = [t for t in tasks if t["done"]]
    if done_tasks:
        lines.append(f"## Completed ({len(done_tasks)})")
        lines.append("")
        for t in done_tasks:
            lines.append(task_line(t, now))
        lines.append("")

    if not open_tasks:
        lines.append("_Nothing outstanding. You're all caught up._")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_html(tasks, now, out_path, completed=0, group="course"):
    open_tasks = [t for t in tasks if not t["done"]]
    overdue = sum(1 for t in open_tasks if t["late"])

    sections = []
    if group == "course":
        grouped = {}
        for t in open_tasks:
            grouped.setdefault(t["course"], []).append(t)
        for name in sorted(grouped, key=course_sort_key):
            sections.append((name, grouped[name], False))
    else:
        for key, heading, _color in BUCKETS:
            if key == "done":
                continue
            items = [t for t in open_tasks if bucket(t, now) == key]
            if items:
                sections.append((heading, items, True))

    done_tasks = [t for t in tasks if t["done"]]

    def item(t, show_course):
        state = "done" if t["done"] else bucket(t, now)
        title = escape(t["title"])
        if t.get("link"):
            body = f'<a href="{escape(t["link"], quote=True)}" target="_blank" rel="noopener">{title}</a>'
        else:
            body = f'<span class="title">{title}</span>'

        meta = []
        if show_course:
            meta.append(escape(t["course"]))
        meta.append(f'<span class="due">{escape(fmt_due(t["due_dt"], now))}</span>')
        if t.get("points"):
            meta.append(f"{t['points']:g} pts")
        if t["late"]:
            meta.append('<span class="badge late">late</span>')
        if t.get("state") == "CREATED" and not t["done"]:
            meta.append('<span class="badge">started</span>')

        key = escape(f"{t['course']}|{t['title']}", quote=True)
        return (
            f'      <li class="task {state}" data-key="{key}">\n'
            f'        <span class="check" aria-hidden="true"></span>\n'
            f'        <div class="body">\n'
            f'          <div class="title-line">{body}</div>\n'
            f'          <div class="meta">{" <span class=dot>&middot;</span> ".join(meta)}</div>\n'
            f'        </div>\n'
            f'      </li>'
        )

    parts = []
    for heading, items, show_course in sections:
        late = sum(1 for t in items if t["late"])
        count = f"{len(items)}" + (f" &middot; {late} late" if late else "")
        parts.append(f'  <section>\n    <h2>{escape(heading)} <span class="count">{count}</span></h2>\n    <ul>')
        parts.extend(item(t, show_course) for t in items)
        parts.append("    </ul>\n  </section>")

    if done_tasks:
        parts.append('  <section>\n    <h2>Completed <span class="count">%d</span></h2>\n    <ul>' % len(done_tasks))
        parts.extend(item(t, True) for t in done_tasks)
        parts.append("    </ul>\n  </section>")

    if not open_tasks and not done_tasks:
        parts.append('<p class="empty">Nothing outstanding. You\'re all caught up.</p>')

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Classroom To-Do</title>
<style>
  :root {{
    --bg: #0f1115; --card: #171a21; --line: #262b36; --text: #e6e9ef;
    --muted: #9aa3b2; --accent: #6ea8fe; --late: #ff6b6b; --today: #ffa94d;
    --week: #ffd43b; --ok: #51cf66;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg: #f6f7f9; --card: #fff; --line: #e3e6ec; --text: #1b1f27;
             --muted: #667085; --accent: #1c5fd4; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 20px 64px; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  header h1 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: -0.02em; }}
  .summary {{ color: var(--muted); font-size: 13px; margin-bottom: 28px; }}
  section {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 4px 18px 8px; margin-bottom: 16px; }}
  h2 {{ font-size: 14px; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase;
       color: var(--muted); margin: 16px 0 10px; display: flex; gap: 8px; align-items: baseline; }}
  .count {{ color: var(--muted); font-weight: 400; text-transform: none; letter-spacing: 0; opacity: .75; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li.task {{ display: flex; gap: 12px; align-items: flex-start; padding: 10px 0; border-top: 1px solid var(--line); cursor: pointer; }}
  li.task:first-child {{ border-top: 0; }}
  .check {{ flex: 0 0 18px; width: 18px; height: 18px; margin-top: 2px; border: 1.5px solid var(--muted);
           border-radius: 5px; position: relative; transition: all .12s ease; }}
  .task.done .check {{ background: var(--ok); border-color: var(--ok); }}
  .task.done .check::after {{ content: ""; position: absolute; left: 5px; top: 1px; width: 4px; height: 9px;
           border: solid #0b0d12; border-width: 0 2px 2px 0; transform: rotate(45deg); }}
  .body {{ flex: 1; min-width: 0; }}
  .title-line a, .title-line .title {{ color: var(--text); text-decoration: none; font-weight: 500; }}
  .title-line a:hover {{ color: var(--accent); text-decoration: underline; }}
  .meta {{ color: var(--muted); font-size: 12.5px; margin-top: 3px; }}
  .dot {{ opacity: .6; }}
  .task.late .due {{ color: var(--late); font-weight: 600; }}
  .task.today .due {{ color: var(--today); font-weight: 600; }}
  .task.week .due {{ color: var(--week); }}
  .badge {{ display: inline-block; padding: 0 6px; border-radius: 5px; font-size: 11px;
           border: 1px solid var(--line); color: var(--muted); }}
  .badge.late {{ color: var(--late); border-color: currentColor; font-weight: 600; }}
  .task.done .title-line {{ opacity: .5; text-decoration: line-through; }}
  .empty {{ color: var(--muted); text-align: center; padding: 40px 0; }}
  footer {{ max-width: 760px; margin: 28px auto 0; color: var(--muted); font-size: 12px; }}
  footer code {{ background: var(--card); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; }}
  @media print {{
    body {{ background: #fff; color: #000; padding: 0; }}
    section {{ border: 1px solid #ddd; break-inside: avoid; }}
    .check {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Classroom To-Do</h1>
    <div class="summary">
      Updated {now.strftime('%a %b %d, %Y %I:%M %p')} &middot;
      {len(open_tasks)} open &middot; {overdue} overdue &middot; {completed} completed
    </div>
  </header>
  <main>
{chr(10).join(parts)}
  </main>
  <footer>
    Click an item to tick it off here (saved in this browser only, not in Classroom).
    Generated by <code>classroom_todo.py</code>.
  </footer>
</div>
<script>
(function () {{
  var KEY = 'classroom-todo-done';
  var saved = {{}};
  try {{ saved = JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch (e) {{}}
  document.querySelectorAll('li.task').forEach(function (li) {{
    var k = li.dataset.key;
    if (saved[k]) li.classList.add('done');
    li.addEventListener('click', function (e) {{
      if (e.target.closest('a')) return;
      li.classList.toggle('done');
      saved[k] = li.classList.contains('done');
      try {{ localStorage.setItem(KEY, JSON.stringify(saved)); }} catch (e) {{}}
    }});
  }});
}})();
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


# -------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Turn Google Classroom coursework into a to-do list.")
    ap.add_argument("--out", default=str(BASE / "TODO.md"), help="markdown output path")
    ap.add_argument("--json", dest="json_out", help="also dump raw tasks to this JSON file")
    ap.add_argument("--include-done", action="store_true", help="keep completed items in the list")
    ap.add_argument(
        "--group",
        choices=["urgency", "course"],
        default="urgency",
        help="section layout: by due urgency (default) or by course",
    )
    ap.add_argument("--html", metavar="PATH", help="also write a styled HTML page")
    ap.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="ignore items due before this date (useful for skipping old semesters)",
    )
    ap.add_argument(
        "--noninteractive",
        action="store_true",
        help="never open a browser; exit if re-authentication is required",
    )
    args = ap.parse_args()

    try:
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("Dependencies missing. Run: .venv\\Scripts\\python.exe -m pip install -r requirements.txt")

    creds = get_credentials(interactive=not args.noninteractive)
    service = build("classroom", "v1", credentials=creds, cache_discovery=False)

    now = datetime.now().astimezone()
    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=now.tzinfo)
    tasks, completed = collect(service, args.include_done, since)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_markdown(tasks, now, out_path, completed, args.group)

    if args.html:
        html_path = Path(args.html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        render_html(tasks, now, html_path, completed, args.group)

    if args.json_out:
        serializable = [{k: v for k, v in t.items() if k != "due_dt"} for t in tasks]
        Path(args.json_out).write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    open_count = sum(1 for t in tasks if not t["done"])
    late = sum(1 for t in tasks if t["late"])
    print(f"\nTo-do list written to {out_path}")
    print(f"{open_count} open item(s), {late} overdue.")


if __name__ == "__main__":
    main()
