#!/usr/bin/env python3
"""Auto-generate the TradeZara developer dashboard HTML from GitHub API data."""
import subprocess, json, os
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta

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
    "Arthur Goncalves Breguez": "ArtBreguez", "Arthur": "ArtBreguez", "arthur": "ArtBreguez",
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

CONTRIBUTOR_COLORS = [
    "#00ff41", "#ff0055", "#00d4ff", "#ffbb00", "#bf00ff",
    "#00ff88", "#ff8800", "#00ffff", "#ff00ff",
]

REPO_COLORS = ["#00ff41", "#ff0055", "#00d4ff", "#ffbb00", "#bf00ff", "#00ff88", "#ff8800"]

PASSWORD_HASH = "04fe5b93af1f78ed781d304f98324461d28df1d1653b78b73f907f1272811c76"


def gh_api(url):
    r = subprocess.run(["curl", "-s"] + HEADERS + [url], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except Exception:
        return []


# Data collection
commit_timeline = defaultdict(list)
repo_stats = {}
recent_commits_raw = []

for repo in REPOS:
    short = repo.split("/")[1]
    commits_all = []
    for page in range(1, 11):
        data = gh_api(f"https://api.github.com/repos/{repo}/commits?per_page=100&page={page}")
        if not isinstance(data, list) or not data:
            break
        for c in data:
            author_name = c.get("commit", {}).get("author", {}).get("name", "")
            date_str = c.get("commit", {}).get("author", {}).get("date", "")
            message = c.get("commit", {}).get("message", "").split("\n")[0][:80]
            commits_all.append({
                "author": author_name,
                "date": date_str[:10],
                "datetime": date_str,
                "message": message,
            })

    repo_stats[short] = {"commits": len(commits_all), "contributors": set()}
    for c in commits_all:
        canonical = NAME_MAP.get(c["author"], c["author"])
        if canonical is None:
            continue
        repo_stats[short]["contributors"].add(canonical)
        commit_timeline[canonical].append({
            "date": c["date"],
            "datetime": c["datetime"],
            "repo": short,
            "message": c["message"],
        })
        recent_commits_raw.append({
            "author": canonical,
            "repo": short,
            "message": c["message"],
            "datetime": c["datetime"],
        })

pr_counts = defaultdict(int)
for repo in REPOS:
    for page in range(1, 20):  # paginate until exhausted
        data = gh_api(f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=100&page={page}")
        if not isinstance(data, list) or not data:
            break
        for pr in data:
            if pr.get("merged_at"):
                login = pr.get("user", {}).get("login", "")
                canonical = NAME_MAP.get(login, login)
                if canonical:
                    pr_counts[canonical] += 1

# Build contributor stats
now = datetime.now(timezone.utc)

recent_weeks = []
d = now
for _ in range(12):
    recent_weeks.append(d.strftime("%Y-W%V"))
    d -= timedelta(weeks=1)
recent_weeks = list(reversed(recent_weeks))

contributors = {}
for author, events in commit_timeline.items():
    dates = sorted([e["date"] for e in events])
    week_counts = Counter()
    hour_counts = Counter()
    for e in events:
        try:
            wd = datetime.strptime(e["date"], "%Y-%m-%d")
            week_counts[wd.strftime("%Y-W%V")] += 1
        except Exception:
            pass
        if e["datetime"] and len(e["datetime"]) >= 13:
            try:
                hour_counts[int(e["datetime"][11:13])] += 1
            except Exception:
                pass

    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    last_commit_dt = datetime.strptime(dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    recency_score = max(0, 100 - (now - last_commit_dt).days)

    contributors[author] = {
        "commits": len(events),
        "prs": pr_counts.get(author, 0),
        "repos": list(set(e["repo"] for e in events)),
        "first_commit": dates[0],
        "last_commit": dates[-1],
        "avatar": AVATAR_MAP.get(author, f"https://ui-avatars.com/api/?name={author}&background=0d1117&color=00ff41&size=64"),
        "week_sparkline": [week_counts.get(w, 0) for w in recent_weeks],
        "peak_hour": peak_hour,
        "recency_score": recency_score,
    }

for short in repo_stats:
    repo_stats[short]["contributors"] = list(repo_stats[short]["contributors"])

sorted_contribs = sorted(contributors.items(), key=lambda x: x[1]["commits"], reverse=True)
contrib_colors = {name: CONTRIBUTOR_COLORS[i % len(CONTRIBUTOR_COLORS)] for i, (name, _) in enumerate(sorted_contribs)}

total_commits = sum(v["commits"] for v in repo_stats.values())
total_prs = sum(pr_counts.values())
total_contributors = len(contributors)
total_repos = len(repo_stats)

recent_commits_raw.sort(key=lambda c: c["datetime"], reverse=True)
recent_feed = recent_commits_raw[:20]


def time_ago(dt_str):
    if not dt_str:
        return "?"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = now - dt
        days = delta.days
        hours = delta.seconds // 3600
        if days >= 365:
            return f"{days // 365}y ago"
        if days >= 30:
            return f"{days // 30}mo ago"
        if days >= 1:
            return f"{days}d ago"
        if hours >= 1:
            return f"{hours}h ago"
        return "just now"
    except Exception:
        return "?"


hour_totals = [0] * 24
for events in commit_timeline.values():
    for e in events:
        if e["datetime"] and len(e["datetime"]) >= 13:
            try:
                hour_totals[int(e["datetime"][11:13])] += 1
            except Exception:
                pass

peak_hour_global = hour_totals.index(max(hour_totals)) if any(hour_totals) else 0

top5 = sorted_contribs[:5]
week_labels = [f"W{i+1}" for i in range(12)]

act_datasets = []
for name, data in top5:
    color = contrib_colors[name]
    act_datasets.append({
        "label": name,
        "data": data["week_sparkline"],
        "borderColor": color,
        "backgroundColor": color + "22",
        "tension": 0.4,
        "fill": False,
        "pointRadius": 3,
    })

repo_labels = list(repo_stats.keys())
repo_data = [repo_stats[r]["commits"] for r in repo_labels]

max_commits = max((v["commits"] for v in contributors.values()), default=1)
max_prs_val = max(pr_counts.values(), default=1)
max_repos_val = max((len(v["repos"]) for v in contributors.values()), default=1)

radar_datasets = []
for name, data in top5:
    color = contrib_colors[name]
    radar_datasets.append({
        "label": name,
        "data": [
            round(data["commits"] / max_commits * 100),
            round(data["prs"] / max(max_prs_val, 1) * 100),
            round(len(data["repos"]) / max(max_repos_val, 1) * 100),
            data["recency_score"],
        ],
        "borderColor": color,
        "backgroundColor": color + "33",
        "pointBackgroundColor": color,
    })


def repo_color(repo_name):
    keys = list(repo_stats.keys())
    idx = keys.index(repo_name) if repo_name in keys else 0
    return REPO_COLORS[idx % len(REPO_COLORS)]


def feed_html(commits):
    rows = []
    for c in commits:
        author = c["author"]
        color = contrib_colors.get(author, "#00ff41")
        avatar = contributors.get(author, {}).get("avatar", f"https://ui-avatars.com/api/?name={author}&background=0d1117&color=00ff41&size=32")
        rcolor = repo_color(c["repo"])
        ago = time_ago(c["datetime"])
        msg = c["message"].replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            f'<div class="feed-row">'
            f'<img src="{avatar}" class="feed-av" onerror="this.src=\'https://ui-avatars.com/api/?name={author}&background=0d1117&color=00ff41&size=32\'">' 
            f'<div class="feed-body">'
            f'<span class="feed-author" style="color:{color}">{author}</span>'
            f'<span class="feed-repo" style="color:{rcolor}">[{c["repo"]}]</span>'
            f'<span class="feed-msg">{msg}</span>'
            f'</div>'
            f'<div class="feed-ago">{ago}</div>'
            f'</div>'
        )
    return "\n".join(rows)


def leaderboard_html(contribs):
    rows = []
    rank_icons = ["&#x1F451;", "&#x26A1;", "&#x1F525;", "#4", "#5", "#6", "#7", "#8"]
    for i, (name, data) in enumerate(contribs):
        color = contrib_colors.get(name, "#00ff41")
        icon = rank_icons[i] if i < len(rank_icons) else f"#{i+1}"
        peak = f'{data["peak_hour"]:02d}h UTC' if data["peak_hour"] is not None else "-"
        rows.append(
            f'<tr>'
            f'<td style="padding:8px 14px;color:{color};font-weight:700">{icon} {name}</td>'
            f'<td style="padding:8px 14px;color:#c9d1d9">{data["commits"]}</td>'
            f'<td style="padding:8px 14px;color:#c9d1d9">{data["prs"]}</td>'
            f'<td style="padding:8px 14px;color:#c9d1d9">{len(data["repos"])}</td>'
            f'<td style="padding:8px 14px;color:#8b949e">{peak}</td>'
            f'<td style="padding:8px 14px;color:#8b949e">{data["last_commit"]}</td>'
            f'</tr>'
        )
    return "\n".join(rows)


def contributor_cards_html(contribs):
    cards = []
    rank_icons = ["&#x1F451;", "&#x26A1;", "&#x1F525;", "#4", "#5", "#6", "#7", "#8"]
    for i, (name, data) in enumerate(contribs):
        color = contrib_colors.get(name, "#00ff41")
        icon = rank_icons[i] if i < len(rank_icons) else f"#{i+1}"
        avatar = data["avatar"]
        peak = f'peak {data["peak_hour"]:02d}h' if data["peak_hour"] is not None else ""
        peak_badge = (
            f'<span style="font-size:.58rem;padding:1px 5px;border:1px solid #30363d;border-radius:3px;color:#8b949e;background:#161b22">&#x23F0; {peak}</span>'
            if peak else ""
        )
        repo_tags = "".join(
            f'<span style="font-size:.58rem;padding:1px 6px;background:rgba(0,255,65,.07);border:1px solid rgba(0,255,65,.2);border-radius:3px;color:#00ff41">{r}</span>'
            for r in data["repos"]
        )
        spark = data["week_sparkline"]
        max_s = max(spark) if spark and max(spark) > 0 else 1
        spark_bars = "".join(
            f'<div style="flex:1;min-height:2px;height:{max(2, round(v / max_s * 26))}px;background:{color};border-radius:1px;opacity:.8"></div>'
            for v in spark
        )
        cards.append(
            f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;position:relative;transition:border-color .2s,transform .2s,box-shadow .2s"'
            f' onmouseover="this.style.borderColor=\'rgba(0,255,65,.35)\';this.style.transform=\'translateY(-2px)\';this.style.boxShadow=\'0 6px 24px rgba(0,0,0,.4)\'"'
            f' onmouseout="this.style.borderColor=\'#30363d\';this.style.transform=\'\';this.style.boxShadow=\'\'">'
            f'<div style="position:absolute;top:10px;right:12px;font-size:.68rem;font-weight:700;color:{color}">{icon}</div>'
            f'<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">'
            f'<img src="{avatar}" style="width:40px;height:40px;border-radius:50%;border:2px solid #30363d;flex-shrink:0"'
            f' onerror="this.src=\'https://ui-avatars.com/api/?name={name}&background=0d1117&color=00ff41&size=64\'">' 
            f'<div><div style="font-size:.85rem;font-weight:700;color:{color};margin-bottom:3px">{name}</div>'
            f'<div style="display:flex;gap:4px;flex-wrap:wrap">'
            f'<span style="font-size:.58rem;padding:1px 5px;border:1px solid #30363d;border-radius:3px;color:#8b949e;background:#161b22">{data["commits"]} commits</span>'
            f'<span style="font-size:.58rem;padding:1px 5px;border:1px solid #30363d;border-radius:3px;color:#8b949e;background:#161b22">{data["prs"]} PRs</span>'
            f'{peak_badge}'
            f'</div></div></div>'
            f'<div style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:8px">{repo_tags}</div>'
            f'<div style="display:flex;align-items:flex-end;gap:2px;height:28px;margin-bottom:8px">{spark_bars}</div>'
            f'<div style="display:flex;justify-content:space-between;font-size:.6rem;color:#8b949e">'
            f'<span>&#x26A1; {data["first_commit"]}</span><span>&#x1F550; {data["last_commit"]}</span>'
            f'</div></div>'
        )
    return "\n".join(cards)


def repo_cards_html():
    cards = []
    for i, (repo_name, stats) in enumerate(repo_stats.items()):
        color = REPO_COLORS[i % len(REPO_COLORS)]
        contrib_count = len(stats["contributors"])
        last_commit = "-"
        for events in commit_timeline.values():
            for e in events:
                if e["repo"] == repo_name and (last_commit == "-" or e["date"] > last_commit):
                    last_commit = e["date"]
        active = last_commit != "-" and (now - datetime.strptime(last_commit, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days < 30
        health = "&#x1F7E2; Active" if active else "&#x1F7E1; Quiet"
        cards.append(
            f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;transition:border-color .2s,transform .2s"'
            f' onmouseover="this.style.borderColor=\'{color}55\';this.style.transform=\'translateY(-2px)\'"'
            f' onmouseout="this.style.borderColor=\'#30363d\';this.style.transform=\'\'">'
            f'<div style="font-size:.75rem;font-weight:700;color:{color};margin-bottom:8px">{repo_name}</div>'
            f'<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:.6rem;color:#8b949e">'
            f'<span>&#x1F4E6; {stats["commits"]} commits</span>'
            f'<span>&#x1F465; {contrib_count} devs</span>'
            f'<span>{health}</span>'
            f'</div>'
            f'<div style="font-size:.58rem;color:#8b949e;margin-top:6px">last: {last_commit}</div>'
            f'</div>'
        )
    return "\n".join(cards)


sync_time = now.strftime("%Y-%m-%d %H:%M UTC")
sync_date = now.strftime("%Y-%m-%d")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TradeZara // Dev Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#0a0c0f;--bg2:#0d1117;--bg3:#161b22;--g:#00ff41;--r:#ff0055;--b:#00d4ff;--y:#ffbb00;--p:#bf00ff;--tx:#c9d1d9;--tx2:#8b949e;--bd:#30363d}}
*{{margin:0;padding:0;box-sizing:border-box}}html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--tx);font-family:'SF Mono','Fira Code',Consolas,monospace;font-size:13px;overflow-x:hidden}}
body::before{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.02) 2px,rgba(0,0,0,.02) 4px);pointer-events:none;z-index:9000}}
#auth{{position:fixed;inset:0;background:rgba(0,0,0,.94);z-index:9999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)}}
.abox{{background:var(--bg2);border:1px solid var(--g);border-radius:8px;padding:40px 32px;width:320px;text-align:center;box-shadow:0 0 40px rgba(0,255,65,.15)}}
.alogo{{font-size:1.2rem;font-weight:700;color:var(--g);letter-spacing:.1em;margin-bottom:4px}}
.asub{{font-size:.62rem;color:var(--tx2);letter-spacing:.12em;margin-bottom:22px}}
.ainp{{width:100%;background:var(--bg3);border:1px solid var(--bd);color:var(--tx);font-family:inherit;font-size:.85rem;padding:10px 12px;border-radius:4px;outline:none;margin-bottom:10px;transition:border-color .15s}}
.ainp:focus{{border-color:var(--g);box-shadow:0 0 8px rgba(0,255,65,.12)}}
.ainp.err{{animation:shk .3s;border-color:var(--r)}}
.abtn{{width:100%;background:rgba(0,255,65,.1);border:1px solid var(--g);color:var(--g);font-family:inherit;font-size:.82rem;padding:10px;border-radius:4px;cursor:pointer;letter-spacing:.1em;transition:background .15s}}
.abtn:hover{{background:rgba(0,255,65,.2)}}
.aerr{{color:var(--r);font-size:.62rem;margin-top:6px;display:none}}
@keyframes shk{{0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-5px)}}75%{{transform:translateX(5px)}}}}
body:not(.unl) .pg{{filter:blur(4px);pointer-events:none;user-select:none}}
nav{{position:sticky;top:0;z-index:100;background:rgba(10,12,15,.97);backdrop-filter:blur(10px);border-bottom:1px solid var(--g);padding:10px 24px;display:flex;align-items:center;gap:12px;box-shadow:0 0 20px rgba(0,255,65,.06)}}
.nl{{font-size:1rem;font-weight:700;color:var(--g);letter-spacing:.1em;text-shadow:0 0 8px var(--g)}}.nl span{{color:var(--tx2)}}
.ntag{{font-size:.62rem;color:var(--tx2);border:1px solid var(--bd);padding:2px 7px;border-radius:4px}}
.nlv{{margin-left:auto;display:flex;align-items:center;gap:5px;font-size:.65rem;color:var(--g)}}
.dot{{width:5px;height:5px;background:var(--g);border-radius:50%;box-shadow:0 0 5px var(--g);animation:bk 1.5s infinite}}
@keyframes bk{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.hero{{padding:24px 24px 16px;border-bottom:1px solid var(--bd);position:relative;overflow:hidden}}
.hero::before{{content:'TRADEZARA';position:absolute;right:-10px;top:50%;transform:translateY(-50%);font-size:6rem;font-weight:900;color:rgba(0,255,65,.02);pointer-events:none;letter-spacing:-.05em}}
.htitle{{font-size:1.4rem;font-weight:700;color:var(--g);text-shadow:0 0 16px rgba(0,255,65,.3);letter-spacing:.04em}}
.hsub{{color:var(--tx2);font-size:.65rem;margin-top:3px;letter-spacing:.12em}}
.hts{{font-size:.6rem;color:var(--tx2);margin-top:5px}}.hts span{{color:var(--g)}}
.cur{{animation:cr 1s step-end infinite}}@keyframes cr{{50%{{opacity:0}}}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--bd);border-bottom:1px solid var(--bd)}}
.met{{background:var(--bg2);padding:14px 20px;position:relative;transition:background .15s}}.met:hover{{background:var(--bg3)}}
.met::after{{content:'';position:absolute;top:0;left:0;right:0;height:2px}}
.met:nth-child(1)::after{{background:var(--g)}}.met:nth-child(2)::after{{background:var(--b)}}
.met:nth-child(3)::after{{background:var(--y)}}.met:nth-child(4)::after{{background:var(--p)}}
.mlb{{font-size:.58rem;color:var(--tx2);letter-spacing:.14em;text-transform:uppercase}}
.mv{{font-size:1.8rem;font-weight:700;margin-top:2px;line-height:1.1}}.ms{{font-size:.58rem;color:var(--tx2);margin-top:2px}}
.met:nth-child(1) .mv{{color:var(--g)}}.met:nth-child(2) .mv{{color:var(--b)}}
.met:nth-child(3) .mv{{color:var(--y)}}.met:nth-child(4) .mv{{color:var(--p)}}
.main{{padding:20px 24px;display:grid;gap:20px;max-width:1400px;margin:0 auto}}
.slbl{{font-size:.6rem;letter-spacing:.2em;text-transform:uppercase;color:var(--tx2);margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.slbl::before{{content:'//';color:var(--g)}}
.charts{{display:grid;grid-template-columns:1fr 1fr 280px;gap:14px}}
.cbox{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:16px;transition:border-color .2s}}
.cbox:hover{{border-color:rgba(0,255,65,.25)}}
.ctitle{{font-size:.6rem;color:var(--tx2);letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px}}
.ctitle b{{color:var(--g);margin-right:4px}}
.ch{{position:relative;height:180px}}.cr{{position:relative;height:180px}}.crad{{position:relative;height:200px}}
.feed-peak{{display:grid;grid-template-columns:1fr 380px;gap:14px;align-items:start}}
.feed-wrap{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;overflow:hidden}}
.feed-hdr{{padding:11px 18px;background:var(--bg3);border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
.feed-hdr-t{{font-size:.64rem;color:var(--g);letter-spacing:.14em;text-transform:uppercase}}
.feed-row{{display:flex;align-items:flex-start;gap:10px;padding:9px 16px;border-bottom:1px solid rgba(48,54,61,.3);transition:background .12s}}
.feed-row:hover{{background:var(--bg3)}}.feed-row:last-child{{border-bottom:none}}
.feed-av{{width:24px;height:24px;border-radius:50%;border:1px solid var(--bd);flex-shrink:0;margin-top:1px}}
.feed-body{{flex:1;min-width:0;font-size:.72rem;line-height:1.45}}
.feed-author{{font-weight:700;margin-right:4px}}
.feed-repo{{font-size:.65rem;margin-right:6px;opacity:.85}}
.feed-msg{{color:var(--tx2)}}
.feed-ago{{font-size:.6rem;color:var(--tx2);white-space:nowrap;flex-shrink:0;margin-top:2px;opacity:.65}}
.peak-wrap{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:16px}}
.peak-info{{font-size:.6rem;color:var(--tx2);margin-top:8px;text-align:center}}
.peak-info span{{color:var(--g);font-weight:700}}
.chour{{position:relative;height:160px}}
.lbw{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;overflow:hidden}}
.lbh{{padding:11px 18px;background:var(--bg3);border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
.lbt{{font-size:.64rem;color:var(--g);letter-spacing:.14em;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse}}
th{{padding:8px 14px;font-size:.58rem;letter-spacing:.14em;text-transform:uppercase;color:var(--tx2);text-align:left;background:var(--bg3);border-bottom:1px solid var(--bd)}}
tr:hover td{{background:var(--bg3)}}
td{{border-bottom:1px solid rgba(48,54,61,.4);font-size:.75rem}}
.cgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}}
.rgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}}
footer{{border-top:1px solid var(--bd);padding:14px 24px;display:flex;justify-content:space-between;font-size:.6rem;color:var(--tx2)}}
footer span{{color:var(--g)}}
@media(max-width:1050px){{.charts{{grid-template-columns:1fr 1fr}}.charts .cbox:last-child{{grid-column:span 2}}.feed-peak{{grid-template-columns:1fr}}}}
@media(max-width:680px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.charts{{grid-template-columns:1fr}}.ch,.cr,.crad,.chour{{height:150px}}nav,.hero,.main,footer{{padding-left:14px;padding-right:14px}}}}
</style>
</head>
<body>

<div id="auth">
  <div class="abox">
    <div class="alogo">TRADE<span style="color:var(--tx2)">ZARA</span></div>
    <div class="asub">// INTERNAL DASHBOARD &middot; ACCESS REQUIRED</div>
    <input class="ainp" id="apw" type="password" placeholder="password"
      autocomplete="current-password" onkeydown="if(event.key==='Enter')ca()">
    <button class="abtn" onclick="ca()">&#x25B8; UNLOCK DASHBOARD</button>
    <div class="aerr" id="aerr">Incorrect password.</div>
  </div>
</div>

<nav class="pg">
  <div class="nl">TRADE<span>ZARA</span></div>
  <div class="ntag">internal</div>
  <div class="ntag">v2.1</div>
  <div class="nlv"><div class="dot"></div>LIVE</div>
</nav>

<div class="hero pg">
  <div class="htitle">// DEVELOPER COMMAND CENTER<span class="cur">_</span></div>
  <div class="hsub">CONTRIBUTOR INTELLIGENCE &amp; CODEBASE ANALYTICS</div>
  <div class="hts">LAST SYNC: <span>{sync_time}</span></div>
</div>

<div class="metrics pg">
  <div class="met"><div class="mlb">Total Commits</div><div class="mv">{total_commits}</div><div class="ms">all repos</div></div>
  <div class="met"><div class="mlb">PRs Merged</div><div class="mv">{total_prs}</div><div class="ms">reviewed &amp; shipped</div></div>
  <div class="met"><div class="mlb">Contributors</div><div class="mv">{total_contributors}</div><div class="ms">active devs</div></div>
  <div class="met"><div class="mlb">Repositories</div><div class="mv">{total_repos}</div><div class="ms">codebases</div></div>
</div>

<div class="main pg">

  <div>
    <div class="slbl">Activity Intelligence</div>
    <div class="charts">
      <div class="cbox"><div class="ctitle"><b>&#x25B8;</b> Weekly Activity &mdash; Top 5</div><div class="ch"><canvas id="actChart"></canvas></div></div>
      <div class="cbox"><div class="ctitle"><b>&#x25B8;</b> Commits per Repository</div><div class="cr"><canvas id="repoChart"></canvas></div></div>
      <div class="cbox"><div class="ctitle"><b>&#x25B8;</b> Contributor Radar</div><div class="crad"><canvas id="radChart"></canvas></div></div>
    </div>
  </div>

  <div>
    <div class="slbl">Live Activity</div>
    <div class="feed-peak">
      <div class="feed-wrap">
        <div class="feed-hdr">
          <div class="feed-hdr-t">&#x26A1; Recent Commits</div>
          <div style="font-size:.58rem;color:var(--tx2)">latest 20 across all repos</div>
        </div>
        {feed_html(recent_feed)}
      </div>
      <div class="peak-wrap">
        <div class="ctitle"><b>&#x25B8;</b> Commit Hours (UTC)</div>
        <div class="chour"><canvas id="hourChart"></canvas></div>
        <div class="peak-info">peak activity <span>{peak_hour_global:02d}h UTC</span></div>
      </div>
    </div>
  </div>

  <div>
    <div class="slbl">Leaderboard</div>
    <div class="lbw">
      <div class="lbh"><div class="lbt">&#x1F3C6; Contributor Rankings</div></div>
      <table>
        <thead><tr>
          <th>Contributor</th><th>Commits</th><th>PRs</th><th>Repos</th><th>Peak Hour</th><th>Last Commit</th>
        </tr></thead>
        <tbody>
          {leaderboard_html(sorted_contribs)}
        </tbody>
      </table>
    </div>
  </div>

  <div>
    <div class="slbl">Contributor Profiles</div>
    <div class="cgrid">
      {contributor_cards_html(sorted_contribs)}
    </div>
  </div>

  <div>
    <div class="slbl">Repository Health</div>
    <div class="rgrid">
      {repo_cards_html()}
    </div>
  </div>

</div>

<footer class="pg">
  <div>TRADEZARA // DEV DASHBOARD <span>v2.1</span></div>
  <div>synced <span>{sync_date}</span> &middot; {total_repos} repos &middot; peak {peak_hour_global:02d}h UTC</div>
</footer>

<script>
const _H='{PASSWORD_HASH}';
async function s2(s){{const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('')}}
async function ca(){{
  const p=document.getElementById('apw').value;
  if(await s2(p)===_H){{
    document.getElementById('auth').style.display='none';
    document.body.classList.add('unl');
    sessionStorage.setItem('tz','1');
    initC();
  }}else{{
    const i=document.getElementById('apw');
    i.classList.add('err');
    document.getElementById('aerr').style.display='block';
    setTimeout(()=>i.classList.remove('err'),400);
    i.value='';
  }}
}}
if(sessionStorage.getItem('tz')==='1'){{
  document.getElementById('auth').style.display='none';
  document.body.classList.add('unl');
}}
Chart.defaults.color='#8b949e';
Chart.defaults.borderColor='#21262d';
Chart.defaults.font.family="'SF Mono','Fira Code',monospace";
Chart.defaults.font.size=10;
const C={json.dumps(CONTRIBUTOR_COLORS)};
function initC(){{
  new Chart(document.getElementById('actChart'),{{type:'line',data:{{labels:{json.dumps(week_labels)},datasets:{json.dumps(act_datasets)}}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:10,padding:8,font:{{size:9}}}}}}}},scales:{{x:{{grid:{{color:'#1e262d'}},ticks:{{maxRotation:0,font:{{size:9}}}}}},y:{{grid:{{color:'#1e262d'}},beginAtZero:true,ticks:{{font:{{size:9}}}}}}}},interaction:{{intersect:false,mode:'index'}},animation:{{duration:800}}}}}});
  new Chart(document.getElementById('repoChart'),{{type:'bar',data:{{labels:{json.dumps(repo_labels)},datasets:[{{label:'Commits',data:{json.dumps(repo_data)},backgroundColor:{json.dumps(repo_labels)}.map((_,i)=>C[i%C.length]+'88'),borderColor:{json.dumps(repo_labels)}.map((_,i)=>C[i%C.length]),borderWidth:1,borderRadius:3}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxRotation:35,font:{{size:9}}}}}},y:{{grid:{{color:'#1e262d'}},beginAtZero:true,ticks:{{font:{{size:9}}}}}}}},animation:{{duration:800}}}}}});
  new Chart(document.getElementById('radChart'),{{type:'radar',data:{{labels:["Commits","PRs","Repos","Recency"],datasets:{json.dumps(radar_datasets)}}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom',labels:{{boxWidth:8,padding:6,font:{{size:9}}}}}}}},scales:{{r:{{grid:{{color:'#1e262d'}},angleLines:{{color:'#1e262d'}},ticks:{{display:false}},pointLabels:{{color:'#8b949e',font:{{size:9}}}},min:0,max:100}}}},animation:{{duration:1000}}}}}});
  const hd={json.dumps(hour_totals)};const mH=Math.max(...hd);
  new Chart(document.getElementById('hourChart'),{{type:'bar',data:{{labels:["00h","01h","02h","03h","04h","05h","06h","07h","08h","09h","10h","11h","12h","13h","14h","15h","16h","17h","18h","19h","20h","21h","22h","23h"],datasets:[{{label:'Commits',data:hd,backgroundColor:hd.map(v=>{{const r=v/mH;return r>.7?'#00ff4188':r>.3?'#00ff4155':'#00ff4122'}}),borderColor:hd.map(v=>v===mH?'#00ff41':'transparent'),borderWidth:1,borderRadius:2}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:i=>i[0].label+' UTC',label:i=>`${{i.parsed.y}} commits`}}}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxRotation:0,font:{{size:8}},callback:(_,i)=>i%4===0?["00h","01h","02h","03h","04h","05h","06h","07h","08h","09h","10h","11h","12h","13h","14h","15h","16h","17h","18h","19h","20h","21h","22h","23h"][i]:''}}}},y:{{grid:{{color:'#1e262d'}},beginAtZero:true,ticks:{{font:{{size:9}}}}}}}},animation:{{duration:800}}}}}});
}}
if(document.body.classList.contains('unl'))initC();
</script>
</body>
</html>"""

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard generated: {sync_time} — {total_commits} commits, {total_contributors} contributors, {total_repos} repos")
