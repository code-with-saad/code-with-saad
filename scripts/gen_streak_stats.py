#!/usr/bin/env python3
"""Generate streak-stats.svg from GitHub's own public contributions calendar.

Replaces the previous approach of fetching a pre-rendered SVG from the
shared public streak-stats.demolab.com instance, which is rate-limited /
occasionally returns a "Failed to retrieve contributions" error body (still
HTTP 200, so a plain curl retry never catches it) and stalls the daily
auto-update. Computing the numbers ourselves removes that third-party
single point of failure.

Data source: https://github.com/users/<login>/contributions - the same
HTML fragment GitHub's own profile page uses to render the contribution
graph. It is public and requires no authentication or token, so there is
no scope/rate-limit risk from a PAT or GITHUB_TOKEN either.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

USERNAME = "code-with-saad"
CONTRIB_URL = "https://github.com/users/{login}/contributions"
USER_API_URL = "https://api.github.com/users/{login}"

DAY_CELL_RE = re.compile(
    r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="(contribution-day-component-\d+-\d+)"'
)
TOOLTIP_RE = re.compile(
    r'for="(contribution-day-component-\d+-\d+)"[^>]*>\s*'
    r'(?:No contributions|(\d+) contributions?) on'
)

STYLE = {
    "background": "#0d1117",
    "border_stroke": "#000000",
    "divider": "#10b981",
    "ring": "#10b981",
    "fire": "#5eead4",
    "label_accent": "#10b981",
    "num": "#ffffff",
    "side_label": "#94a3b8",
}


def http_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; streak-stats-generator/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {url} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e


def fetch_account_created(login):
    payload = json.loads(http_get(USER_API_URL.format(login=login)))
    return datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))


def parse_contribution_page(html):
    ids_to_date = {cell_id: date_str for date_str, cell_id in DAY_CELL_RE.findall(html)}
    ids_to_count = {}
    for m in TOOLTIP_RE.finditer(html):
        cell_id, count = m.group(1), m.group(2)
        ids_to_count[cell_id] = int(count) if count is not None else 0

    counts = {}
    for cell_id, date_str in ids_to_date.items():
        if cell_id in ids_to_count:
            counts[date.fromisoformat(date_str)] = ids_to_count[cell_id]
    return counts


def fetch_daily_counts():
    created_at = fetch_account_created(USERNAME)
    created_date = created_at.date()
    now = datetime.now(timezone.utc)

    counts = {}
    for year in range(created_at.year, now.year):
        html = http_get(f"{CONTRIB_URL.format(login=USERNAME)}?to={year}-12-31")
        counts.update(parse_contribution_page(html))

    html = http_get(CONTRIB_URL.format(login=USERNAME))
    counts.update(parse_contribution_page(html))

    # Drop padding days the year-boundary fetches include before the account
    # existed, so the "Total Contributions" range reflects account creation.
    counts = {d: c for d, c in counts.items() if d >= created_date}

    if not counts:
        raise RuntimeError("No contribution days parsed from GitHub's contributions page")
    return counts


def compute_streaks(counts):
    if not counts:
        return 0, 0, None, None, None, None, 0, None

    days_sorted = sorted(counts)
    first_day = days_sorted[0]
    last_day = days_sorted[-1]
    total = sum(counts.values())

    longest = 0
    longest_start = longest_end = None
    run_start = None
    run_len = 0
    for d in days_sorted:
        if counts[d] > 0:
            if run_len == 0:
                run_start = d
            run_len += 1
            if run_len > longest:
                longest = run_len
                longest_start = run_start
                longest_end = d
        else:
            run_len = 0

    today = last_day
    if counts.get(today, 0) > 0:
        anchor = today
    else:
        anchor = today - timedelta(days=1)
        if counts.get(anchor, 0) == 0:
            anchor = None

    current = 0
    current_start = current_end = None
    if anchor is not None:
        current_end = anchor
        d = anchor
        while counts.get(d, 0) > 0:
            current += 1
            current_start = d
            d -= timedelta(days=1)

    return total, current, current_start, current_end, longest_start, longest_end, longest, first_day


def fmt_day(d, with_year=False):
    month_day = f"{d.strftime('%b')} {d.day}"
    return f"{month_day}, {d.year}" if with_year else month_day


def fmt_range(start, end):
    if start is None or end is None:
        return "-"
    if start == end:
        return fmt_day(start)
    if start.year != end.year:
        return f"{fmt_day(start, True)} - {fmt_day(end, True)}"
    return f"{fmt_day(start)} - {fmt_day(end)}"


def render_svg(total, current, current_range, longest, longest_range, total_range):
    s = STYLE
    return f"""<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'
                style='isolation: isolate' viewBox='0 0 495 195' width='495px' height='195px' direction='ltr'>

        <defs>
            <clipPath id='outer_rectangle'>
                <rect width='495' height='195' rx='4.5'/>
            </clipPath>
            <mask id='mask_out_ring_behind_fire'>
                <rect width='495' height='195' fill='white'/>
                <ellipse id='mask-ellipse' cx='247.5' cy='32' rx='13' ry='18' fill='black'/>
            </mask>

        </defs>
        <g clip-path='url(#outer_rectangle)'>
            <g style='isolation: isolate'>
                <rect stroke='{s["border_stroke"]}' stroke-opacity='0' fill='{s["background"]}' rx='4.5' x='0.5' y='0.5' width='494' height='194'/>
            </g>
            <g style='isolation: isolate'>
                <line x1='165' y1='28' x2='165' y2='170' vector-effect='non-scaling-stroke' stroke-width='1' stroke='{s["divider"]}' stroke-linejoin='miter' stroke-linecap='square' stroke-miterlimit='3'/>
                <line x1='330' y1='28' x2='330' y2='170' vector-effect='non-scaling-stroke' stroke-width='1' stroke='{s["divider"]}' stroke-linejoin='miter' stroke-linecap='square' stroke-miterlimit='3'/>
            </g>
            <g style='isolation: isolate'>
                <!-- Total Contributions big number -->
                <g transform='translate(82.5, 48)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["num"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='700' font-size='28px' font-style='normal'>
                        {total}
                    </text>
                </g>

                <!-- Total Contributions label -->
                <g transform='translate(82.5, 84)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["side_label"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='400' font-size='14px' font-style='normal'>
                        Total Contributions
                    </text>
                </g>

                <!-- Total Contributions range -->
                <g transform='translate(82.5, 114)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["side_label"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='400' font-size='12px' font-style='normal'>
                        {total_range}
                    </text>
                </g>
            </g>
            <g style='isolation: isolate'>
                <!-- Current Streak label -->
                <g transform='translate(247.5, 108)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["label_accent"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='700' font-size='14px' font-style='normal'>
                        Current Streak
                    </text>
                </g>

                <!-- Current Streak range -->
                <g transform='translate(247.5, 145)'>
                    <text x='0' y='21' stroke-width='0' text-anchor='middle' fill='{s["side_label"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='400' font-size='12px' font-style='normal'>
                        {current_range}
                    </text>
                </g>

                <!-- Ring around number -->
                <g mask='url(#mask_out_ring_behind_fire)'>
                    <circle cx='247.5' cy='71' r='40' fill='none' stroke='{s["ring"]}' stroke-width='5'></circle>
                </g>
                <!-- Fire icon -->
                <g transform='translate(247.5, 19.5)' stroke-opacity='0'>
                    <path d='M -12 -0.5 L 15 -0.5 L 15 23.5 L -12 23.5 L -12 -0.5 Z' fill='none'/>
                    <path d='M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 C 4.51 16.85 2.36 19 -0.29 19 Z' fill='{s["fire"]}' stroke-opacity='0'/>
                </g>

                <!-- Current Streak big number -->
                <g transform='translate(247.5, 48)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["num"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='700' font-size='28px' font-style='normal'>
                        {current}
                    </text>
                </g>

            </g>
            <g style='isolation: isolate'>
                <!-- Longest Streak big number -->
                <g transform='translate(412.5, 48)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["num"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='700' font-size='28px' font-style='normal'>
                        {longest}
                    </text>
                </g>

                <!-- Longest Streak label -->
                <g transform='translate(412.5, 84)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["side_label"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='400' font-size='14px' font-style='normal'>
                        Longest Streak
                    </text>
                </g>

                <!-- Longest Streak range -->
                <g transform='translate(412.5, 114)'>
                    <text x='0' y='32' stroke-width='0' text-anchor='middle' fill='{s["side_label"]}' stroke='none' font-family='"Segoe UI", Ubuntu, sans-serif' font-weight='400' font-size='12px' font-style='normal'>
                        {longest_range}
                    </text>
                </g>
            </g>

        </g>
    </svg>
"""


def main():
    counts = fetch_daily_counts()
    (
        total,
        current,
        current_start,
        current_end,
        longest_start,
        longest_end,
        longest,
        first_day,
    ) = compute_streaks(counts)

    total_range = f"{fmt_day(first_day, True)} - Present" if first_day else "-"
    current_range = fmt_range(current_start, current_end)
    longest_range = fmt_range(longest_start, longest_end)

    svg = render_svg(total, current, current_range, longest, longest_range, total_range)

    out_path = os.path.join(os.path.dirname(__file__), "..", "streak-stats.svg")
    with open(out_path, "w", newline="\n") as f:
        f.write(svg)

    print(f"total={total} current={current} ({current_range}) longest={longest} ({longest_range})")


if __name__ == "__main__":
    main()
