#!/usr/bin/env python3
"""Auto-generate the TradeZara developer dashboard HTML from GitHub API data."""
import subprocess, json, os
from collections import defaultdict
from datetime import datetime, timezone

TOKEN = os.environ.get("GH_TOKEN", "")
HEADERS = ["-H", f"Authorization: Bearer {TOKEN}", "-H", "Accept: application/vnd.github+json"]

REPOS = [
    "TradeZara/pip-matrix",
    "TradeZara/backtesting-framework",
    "TradeZara/databento-server",
    "TradeZara/trading-view-ws",
    "TradeZara/pip-matrix-backend",
    "TradeZara/correlation-modelling",
    "TradeZara/graph_api_hft",
]

NAME_MAP = {
    "artbreguez": "ArtBreguez", "Arthur Breguez": "ArtBreguez",
    "Arthur Gonçalves Breguez": "ArtBreguez", "Arthur": "ArtBreguez", "arthur": "ArtBreguez",
    "Antonio Ramon": "Antonio-Ramon",
    "Robson Gomes": "robsongade",
    "Pranjal Biyani": "PranjalBiyani",
    "Allan Figueira": "allanfigueira", "Allan": "allanfigueira",
    "adonunes": "AdoNunes",
    "Fly.io": None,
}

AVATAR_MAP = {
    "ArtBreguez": "https://avatars.githubusercontent.com/u/98524696?v=4",
    "Antonio-Ramon": "https://avatars.githubusercontent.com/u/88857776?v=4",
    "robsongade": "https://avatars.githubusercontent.com/u/69439752?v=4",
    "allanfigueira": "https://avatars.githubusercontent.com/u/100035050?v=4",
    "AdoNunes": "https://avatars.githubusercontent.com/u/17873774?v=4",
}

def gh_api(url):
    r = subprocess.run(["curl", "-s"] + HEADERS + [url], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return []

commit_timeline = defaultdict(list)
repo_stats = {}

for repo in REPOS:
    short = repo.split("/")[1]
    commits_all = []
    for page in range(1, 4):
        data = gh_api(f"https://api.github.com/repos/{repo}/commits?per_page=100&page={page}")
        if not isinstance(data, list) or not data:
            break
        for c in data:
            commits_all.append({
                "author": c.get("commit", {}).get("author", {}).get("name", ""),
                "date": c.get("commit", {}).get("author", {}).get("date", "")[:10],
            })

    repo_stats[short] = {"commits": len(commits_all), "contributors": set()}
    for c in commits_all:
        canonical = NAME_MAP.get(c["author"], c["author"])
        if canonical is None:
            continue
        repo_stats[short]["contributors"].add(canonical)
        commit_timeline[canonical].append({"date": c["date"], "repo": short})

pr_counts = defaultdict(int)
for repo in REPOS[:2]:
    data = gh_api(f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=100")
    if isinstance(data, list):
        for pr in data:
            if pr.get("merged_at"):
                login = pr.get("user", {}).get("login", "")
                canonical = NAME_MAP.get(login, login)
                if canonical:
                    pr_counts[canonical] += 1

contributors = {}
for author, events in commit_timeline.items():
    dates = sorted([e["date"] for e in events])
    from collections import Counter
    week_counts = Counter()
    for e in events:
        d = datetime.strptime(e["date"], "%Y-%m-%d")
        week_counts[d.strftime("%Y-W%V")] += 1
    contributors[author] = {
        "commits": len(events),
        "prs": pr_counts.get(author, 0),
        "repos": list(set(e["repo"] for e in events)),
        "first_commit": dates[0],
        "last_commit": dates[-1],
        "avatar": AVATAR_MAP.get(author, f"https://ui-avatars.com/api/?name={author}&background=0d1117&color=00ff41&size=64"),
        "week_sparkline": [week_counts.get(w, 0) for w in sorted(week_counts)[-12:]],
    }

for short in repo_stats:
    repo_stats[short]["contributors"] = list(repo_stats[short]["contributors"])

print(f"Built stats: {len(contributors)} contributors, {len(repo_stats)} repos")
# In production: regenerate full HTML here (same logic as initial generation)
