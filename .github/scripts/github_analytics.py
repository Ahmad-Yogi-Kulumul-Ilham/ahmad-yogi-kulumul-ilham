"""Render an AI-themed GitHub analytics dashboard SVG from the GitHub GraphQL API.

Usage: GITHUB_TOKEN=... python github_analytics.py <username> <output.svg>
       python github_analytics.py --sample <output.svg>   (render with fake data)
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"


def gql(query, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch(user, token):
    base = gql(
        f"""{{
      user(login: "{user}") {{
        createdAt
        repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {{
          totalCount
          nodes {{
            stargazerCount
            languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
              edges {{ size node {{ name color }} }}
            }}
          }}
        }}
        followers {{ totalCount }}
      }}
    }}""",
        token,
    )["user"]

    today = dt.date.today()
    first_year = int(base["createdAt"][:4])
    parts = []
    for year in range(first_year, today.year + 1):
        parts.append(
            f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z") '
            "{ totalCommitContributions contributionCalendar { weeks { contributionDays { date contributionCount } } } }"
        )
    years = gql(f'{{ user(login: "{user}") {{ {" ".join(parts)} }} }}', token)["user"]

    days = {}
    commits_this_year = 0
    for key, coll in years.items():
        if key == f"y{today.year}":
            commits_this_year = coll["totalCommitContributions"]
        for week in coll["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    langs = {}
    stars = 0
    for repo in base["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = langs.get(name, (0, None))
            langs[name] = (size + edge["size"], edge["node"]["color"] or color or "#8b949e")

    return {
        "created": base["createdAt"][:10],
        "repos": base["repositories"]["totalCount"],
        "followers": base["followers"]["totalCount"],
        "stars": stars,
        "commits_this_year": commits_this_year,
        "days": days,
        "langs": langs,
    }


def sample():
    import random

    random.seed(7)
    today = dt.date.today()
    days = {}
    d = dt.date(2020, 6, 21)
    while d <= today:
        days[d.isoformat()] = random.choice([0, 0, 0, 1, 2, 3, 5, 8]) if d.year > 2023 else random.choice([0, 0, 0, 0, 1])
        d += dt.timedelta(days=1)
    langs = {
        "TypeScript": (520000, "#3178c6"),
        "Python": (310000, "#3572A5"),
        "PHP": (220000, "#4F5D95"),
        "Java": (120000, "#b07219"),
        "C++": (90000, "#f34b7d"),
        "JavaScript": (60000, "#f1e05a"),
        "HTML": (30000, "#e34c26"),
    }
    return {"created": "2020-06-21", "repos": 42, "followers": 18, "stars": 57,
            "commits_this_year": 640, "days": days, "langs": langs}


def streaks(days):
    today = dt.date.today()
    ordered = sorted((dt.date.fromisoformat(k), v) for k, v in days.items() if dt.date.fromisoformat(k) <= today)

    longest = run = 0
    longest_range = (None, None)
    start = None
    for day, count in ordered:
        if count > 0:
            if run == 0:
                start = day
            run += 1
            if run > longest:
                longest, longest_range = run, (start, day)
        else:
            run = 0

    # Current streak: today may still be empty without breaking the streak.
    lookup = dict(ordered)
    cursor = today if lookup.get(today, 0) > 0 else today - dt.timedelta(days=1)
    current = 0
    end = cursor
    while lookup.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    current_range = (cursor + dt.timedelta(days=1), end) if current else (None, None)
    return current, current_range, longest, longest_range


def weekly(days, weeks=52):
    today = dt.date.today()
    start = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks - 1)
    out = []
    for i in range(weeks):
        wk = start + dt.timedelta(weeks=i)
        total = sum(days.get((wk + dt.timedelta(days=j)).isoformat(), 0) for j in range(7))
        out.append((wk, total))
    return out


def fmt_range(r):
    a, b = r
    if not a:
        return "no active streak"
    return f"{a:%b %d} – {b:%b %d, %Y}" if a.year != b.year else f"{a:%b %d} – {b:%b %d}"


def render(user, data):
    W, H = 1200, 580
    total = sum(data["days"].values())
    current, cur_range, longest, long_range = streaks(data["days"])
    since = dt.date.fromisoformat(data["created"])
    today = dt.date.today()

    tiles = [
        ("TOTAL CONTRIBUTIONS", f"{total:,}", f"since {since:%b %Y}", "#00ffaa"),
        ("CURRENT STREAK", f"{current}", fmt_range(cur_range), "#ff9f1c"),
        ("LONGEST STREAK", f"{longest}", fmt_range(long_range), "#a78bfa"),
        (f"COMMITS {today.year}", f"{data['commits_this_year']:,}", "this year", "#22d3ee"),
        ("PUBLIC REPOS", f"{data['repos']}", f"★ {data['stars']} stars · {data['followers']} followers", "#f472b6"),
    ]

    s = []
    a = s.append
    a(f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
      f'aria-label="GitHub analytics for {escape(user)}: {total:,} total contributions, current streak {current} days, longest streak {longest} days">')
    a(f"<title>GitHub Analytics — {escape(user)}</title>")
    a("""<defs>
  <linearGradient id="gbg" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#0b1020"/><stop offset="50%" stop-color="#1a1840"/><stop offset="100%" stop-color="#0d1226"/>
  </linearGradient>
  <linearGradient id="gbar" x1="0%" y1="100%" x2="0%" y2="0%">
    <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.35"/><stop offset="100%" stop-color="#00ffaa"/>
  </linearGradient>
  <linearGradient id="garea" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%" stop-color="#a78bfa" stop-opacity="0.35"/><stop offset="100%" stop-color="#a78bfa" stop-opacity="0"/>
  </linearGradient>
  <pattern id="ggrid" width="40" height="40" patternUnits="userSpaceOnUse">
    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#00ffaa" stroke-opacity="0.05"/>
  </pattern>
  <filter id="gglow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>""")
    a(f'<rect width="{W}" height="{H}" rx="16" fill="url(#gbg)"/>')
    a(f'<rect width="{W}" height="{H}" rx="16" fill="url(#ggrid)"/>')

    # Title bar
    a('<path d="M16 0 H1184 A16 16 0 0 1 1200 16 V44 H0 V16 A16 16 0 0 1 16 0 Z" fill="#00ffaa" fill-opacity="0.08"/>')
    a('<circle cx="28" cy="22" r="6" fill="#ff5f56"/><circle cx="48" cy="22" r="6" fill="#ffbd2e"/><circle cx="68" cy="22" r="6" fill="#27c93f"/>')
    a(f'<text x="600" y="27" text-anchor="middle" font-family="monospace" font-size="13" fill="#9aa4c7">analytics.dashboard — github.com/{escape(user)}</text>')
    a('<g font-family="monospace" font-size="11" fill="#00ffaa" text-anchor="end">'
      f'<text x="1172" y="26">● SYNCED {today:%Y-%m-%d}<animate attributeName="opacity" values="1;0.4;1" dur="2.4s" repeatCount="indefinite"/></text></g>')

    # Stat tiles
    tw, gap = 208, 18
    for i, (label, value, sub, color) in enumerate(tiles):
        x = 44 + i * (tw + gap)
        delay = 0.1 + i * 0.12
        a(f'<g><animate attributeName="opacity" values="0;1" dur="0.6s" begin="{delay:.2f}s" fill="freeze"/>')
        a(f'<rect x="{x}" y="64" width="{tw}" height="112" rx="12" fill="#0b1024" fill-opacity="0.7" stroke="{color}" stroke-opacity="0.45"/>')
        a(f'<rect x="{x}" y="64" width="4" height="112" rx="2" fill="{color}"/>')
        a(f'<text x="{x + 20}" y="90" font-family="monospace" font-size="11" letter-spacing="1" fill="#9aa4c7">{escape(label)}</text>')
        a(f'<text x="{x + 20}" y="136" font-family="monospace" font-size="36" font-weight="bold" fill="{color}" filter="url(#gglow)">{escape(value)}</text>')
        if label.endswith("STREAK"):
            a(f'<text x="{x + 26 + len(value) * 22}" y="136" font-family="monospace" font-size="14" fill="#9aa4c7">days</text>')
        a(f'<text x="{x + 20}" y="160" font-family="monospace" font-size="11" fill="#c7cde6">{escape(sub)}</text>')
        a("</g>")

    # Weekly activity chart
    px, py, pw, ph = 44, 196, 720, 360
    a(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="12" fill="#0b1024" fill-opacity="0.6" stroke="#00ffaa" stroke-opacity="0.2"/>')
    a(f'<text x="{px + 20}" y="{py + 30}" font-family="monospace" font-size="14" font-weight="bold" fill="#e6e9f5">contribution.activity<tspan fill="#9aa4c7" font-weight="normal"> · last 52 weeks</tspan></text>')
    weeks = weekly(data["days"])
    peak = max((v for _, v in weeks), default=0) or 1
    cx0, cy0, cw, ch = px + 24, py + 316, pw - 48, 250
    bw = cw / len(weeks)
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = cy0 - ch * frac
        a(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx0 + cw}" y2="{y:.1f}" stroke="#9aa4c7" stroke-opacity="0.1" stroke-dasharray="3 5"/>')
    a(f'<text x="{cx0 + cw}" y="{cy0 - ch - 6}" text-anchor="end" font-family="monospace" font-size="10" fill="#9aa4c7">peak {peak}/week</text>')
    points = []
    last_month = None
    for i, (wk, v) in enumerate(weeks):
        h = max(2.0, ch * v / peak)
        x = cx0 + i * bw + 1.5
        y = cy0 - h
        points.append((x + (bw - 3) / 2, cy0 - ch * v / peak))
        a(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw - 3:.1f}" height="{h:.1f}" rx="2" fill="url(#gbar)" fill-opacity="{0.35 if v == 0 else 1}">'
          f'<animate attributeName="height" values="0;0;{h:.1f}" keyTimes="0;{i / (i + 40):.3f};1" dur="{1 + i * 0.015:.2f}s" fill="freeze"/>'
          f'<animate attributeName="y" values="{cy0};{cy0};{y:.1f}" keyTimes="0;{i / (i + 40):.3f};1" dur="{1 + i * 0.015:.2f}s" fill="freeze"/></rect>')
        if wk.month != last_month and wk.day <= 7:
            a(f'<text x="{x:.1f}" y="{cy0 + 20}" font-family="monospace" font-size="10" fill="#9aa4c7">{wk:%b}</text>')
            last_month = wk.month
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{points[0][0]:.1f},{cy0} {line} {points[-1][0]:.1f},{cy0}"
    a(f'<polygon points="{area}" fill="url(#garea)"/>')
    a(f'<polyline points="{line}" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linejoin="round" filter="url(#gglow)" '
      f'stroke-dasharray="4000" stroke-dashoffset="0"><animate attributeName="stroke-dashoffset" values="4000;0" dur="3s" fill="freeze"/></polyline>')
    a(f'<line x1="{cx0}" y1="{cy0}" x2="{cx0 + cw}" y2="{cy0}" stroke="#9aa4c7" stroke-opacity="0.35"/>')

    # Top languages
    lx, ly, lw, lh = 784, 196, 372, 360
    a(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="12" fill="#0b1024" fill-opacity="0.6" stroke="#a78bfa" stroke-opacity="0.25"/>')
    a(f'<text x="{lx + 20}" y="{ly + 30}" font-family="monospace" font-size="14" font-weight="bold" fill="#e6e9f5">language.model<tspan fill="#9aa4c7" font-weight="normal"> · by code size</tspan></text>')
    top = sorted(data["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    lang_total = sum(v[0] for _, v in data["langs"].items()) or 1
    # Stacked distribution bar
    sx, bar_w = lx + 20, lw - 40
    a(f'<clipPath id="lclip"><rect x="{sx}" y="{ly + 48}" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#lclip)">')
    off = 0.0
    for name, (size, color) in top:
        w = bar_w * size / lang_total
        a(f'<rect x="{sx + off:.1f}" y="{ly + 48}" width="{w:.1f}" height="10" fill="{color}"/>')
        off += w
    a(f'<rect x="{sx + off:.1f}" y="{ly + 48}" width="{max(0.0, bar_w - off):.1f}" height="10" fill="#9aa4c7" fill-opacity="0.3"/></g>')
    for i, (name, (size, color)) in enumerate(top):
        pct = 100 * size / lang_total
        y = ly + 96 + i * 44
        w = max(4.0, bar_w * pct / 100)
        a(f'<circle cx="{sx + 5}" cy="{y - 5}" r="5" fill="{color}"/>')
        a(f'<text x="{sx + 18}" y="{y}" font-family="monospace" font-size="14" fill="#e6e9f5">{escape(name)}</text>')
        a(f'<text x="{sx + bar_w}" y="{y}" text-anchor="end" font-family="monospace" font-size="13" fill="#9aa4c7">{pct:.1f}%</text>')
        a(f'<rect x="{sx}" y="{y + 9}" width="{bar_w}" height="6" rx="3" fill="#9aa4c7" fill-opacity="0.12"/>')
        a(f'<rect x="{sx}" y="{y + 9}" width="{w:.1f}" height="6" rx="3" fill="{color}" filter="url(#gglow)">'
          f'<animate attributeName="width" values="0;{w:.1f}" dur="1.2s" fill="freeze"/></rect>')

    a(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="#00ffaa" stroke-opacity="0.2"/>')
    a("</svg>")
    return "\n".join(s)


def main():
    if sys.argv[1] == "--sample":
        user, data, out = "yogicodee", sample(), sys.argv[2]
    else:
        user, out = sys.argv[1], sys.argv[2]
        data = fetch(user, os.environ["GITHUB_TOKEN"])
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(user, data))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
