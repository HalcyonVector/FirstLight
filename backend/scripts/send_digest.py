"""
Build and send the weekly digest -- top movers + breakouts (young & accelerating
repos) -- to whichever notification channels are configured. Scheduled via
.github/workflows/digest.yml, or run on demand:

    python scripts/send_digest.py

The email is a conventional light newsletter layout (inline CSS, table-based, so
it renders the same in Gmail / Outlook / Apple Mail) with a prefers-color-scheme
dark variant. Every repo links to GitHub and to its analysis page on the FirstLight site.
Discord/Slack get a tidy plaintext version.
"""

import asyncio
import html as _htmllib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.digest_service import fetch_digest, signal  # noqa: E402
from app.services.notify_service import any_channel_configured, notify  # noqa: E402

# -- Email palette: light newsletter; dark variant via prefers-color-scheme --
BODY = "#f4f5f7"
CARD = "#ffffff"
INK = "#111827"
MUTED = "#4b5563"
DIM = "#6b7280"
RULE = "#e5e7eb"
ACCENT = "#e8590c"
ACCENT_BG = "#fff4ec"
GAIN = "#15803d"
GAIN_BG = "#e7f6ec"
PILL = "#f1f3f5"
BLUE = "#2563eb"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
DEFAULT_SITE = "https://firstlight-oss.vercel.app"


def _site() -> str:
    urls = settings.frontend_urls
    return urls[0] if urls else DEFAULT_SITE


_signal = signal


def _age_days(m) -> Optional[int]:
    created = m["github_created_at"]
    if not created:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).days


# ------------------------- plaintext (Discord / Slack) -------------------------

def _lines(rows) -> list:
    if not rows:
        return ["  (none yet -- momentum needs a few days of data)"]
    out = []
    for i, r in enumerate(rows, 1):
        m = r._mapping
        sig = "backed by activity" if _signal(m) else "star-driven"
        cat = m["category"] or "-"
        out.append(
            f"{i}. {m['full_name']}  |  {cat}  |  momentum {float(m['momentum_score']):.0f}  |  "
            f"+{m['stars_gained_week'] or 0:,}/wk  |  +{m['stars_gained_today'] or 0:,} today  |  "
            f"{m['latest_stars']:,} stars  |  {sig}"
        )
        out.append(f"   https://github.com/{m['full_name']}")
    return out


def _big_story_line(breakouts, movers) -> Optional[str]:
    src = breakouts or movers
    if not src:
        return None
    m = src[0]._mapping
    kind = "breakout" if breakouts else "top mover"
    return (
        f"This week's {kind}: {m['full_name']} -- momentum {float(m['momentum_score']):.0f}, "
        f"+{m['stars_gained_week'] or 0:,} stars in 7 days."
    )


def _shipped_lines(shipped) -> list:
    return [
        f"- {r._mapping['full_name']} {r._mapping['tag']}  {r._mapping['url'] or ''}".rstrip()
        for r in shipped
    ]


def _text_body(breakouts, movers, shipped, date_range: str) -> str:
    parts = [f"FirstLight -- Weekly Digest ({date_range})", ""]
    story = _big_story_line(breakouts, movers)
    if story:
        parts += [f"* {story}", ""]
    parts += ["Breakouts (new & accelerating)", *_lines(breakouts), ""]
    parts += ["Top movers", *_lines(movers)]
    if shipped:
        parts += ["", "What shipped", *_shipped_lines(shipped)]
    parts += ["", f"Full dashboard: {_site()}/this-week"]
    return "\n".join(parts)


# ------------------------- HTML email -------------------------

def _esc(s) -> str:
    return _htmllib.escape(str(s)) if s is not None else ""


def _pill(label: str, color: str, bg: str) -> str:
    return (
        f'<span style="display:inline-block;font-family:{SANS};font-size:11px;font-weight:600;'
        f'color:{color};background:{bg};border-radius:999px;padding:2px 9px;'
        f'line-height:18px;white-space:nowrap;">{label}</span>'
    )


def _repo_card(i: int, m, is_breakout: bool) -> str:
    raw_name = m["full_name"]
    name = _esc(raw_name)
    gh_url = f"https://github.com/{raw_name}"
    site_url = f"{_site()}/repos/{m['id']}"
    mom = float(m["momentum_score"])

    badges = [_pill(f"Momentum {mom:.0f}", ACCENT, ACCENT_BG)]
    if _signal(m):
        badges.append(_pill("Backed by activity", GAIN, GAIN_BG))
    else:
        badges.append(_pill("Star-driven", DIM, PILL))
    if m["category"]:
        badges.append(_pill(_esc(m["category"]), MUTED, PILL))
    if is_breakout:
        age = _age_days(m)
        if age is not None:
            badges.append(_pill(f"{age}d old", BLUE, "#e8f0fe"))
    badges_html = "&nbsp;".join(badges)

    week = m["stars_gained_week"] or 0
    today = m["stars_gained_today"] or 0
    stars = m["latest_stars"] or 0
    lang = _esc(m["language"]) if m["language"] else None
    desc = _esc((m["description"] or "").strip())
    if len(desc) > 140:
        desc = desc[:137] + "&#8230;"

    meta = [
        f'<strong style="color:{GAIN};">+{week:,}</strong> stars this week',
        f"+{today:,} today",
        f"{stars:,} total",
    ]
    if lang:
        meta.append(lang)
    meta_html = " &nbsp;&bull;&nbsp; ".join(meta)

    desc_row = (
        f'<div class="gti-muted" style="font-family:{SANS};font-size:14px;line-height:20px;color:{MUTED};margin:4px 0 0;">{desc}</div>'
        if desc else ""
    )

    return f"""
    <tr>
      <td class="gti-rule" style="padding:18px 28px;border-top:1px solid {RULE};">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td width="30" valign="top" class="gti-dim" style="font-family:{SANS};font-size:15px;font-weight:700;color:{DIM};padding-top:1px;">{i}</td>
          <td valign="top">
            <a href="{gh_url}" class="gti-ink" style="font-family:{SANS};font-size:17px;font-weight:700;color:{INK};text-decoration:none;">{name}</a>
            {desc_row}
            <div style="margin:10px 0 9px;line-height:26px;">{badges_html}</div>
            <div class="gti-muted" style="font-family:{SANS};font-size:13px;line-height:20px;color:{MUTED};">{meta_html}</div>
            <div style="font-family:{SANS};font-size:13px;margin-top:9px;">
              <a href="{gh_url}" style="color:{BLUE};text-decoration:none;font-weight:600;">View on GitHub &rarr;</a>
              &nbsp;&nbsp;
              <a href="{site_url}" style="color:{ACCENT};text-decoration:none;font-weight:600;">Full analysis &rarr;</a>
            </div>
          </td>
        </tr></table>
      </td>
    </tr>"""


def _section(title: str, subtitle: str, rows, is_breakout: bool) -> str:
    if rows:
        cards = "".join(_repo_card(i, r._mapping, is_breakout) for i, r in enumerate(rows, 1))
    else:
        cards = (
            f'<tr><td class="gti-muted gti-rule" style="font-family:{SANS};font-size:14px;color:{MUTED};'
            f'padding:18px 28px;border-top:1px solid {RULE};">'
            f"Nothing here yet &mdash; momentum needs a few days of daily snapshots to build.</td></tr>"
        )
    return f"""
    <tr><td style="padding:30px 28px 14px;">
      <div class="gti-ink" style="font-family:{SANS};font-size:20px;font-weight:800;color:{INK};">{title}</div>
      <div class="gti-dim" style="font-family:{SANS};font-size:13px;color:{DIM};margin-top:2px;">{subtitle}</div>
    </td></tr>
    {cards}"""


def _shipped_section(shipped) -> str:
    if not shipped:
        return ""
    items = []
    for r in shipped:
        m = r._mapping
        url = m["url"] or f"https://github.com/{m['full_name']}/releases"
        snippet = _esc((m["snippet"] or "")[:140])
        snippet_html = (
            f'<div class="gti-muted" style="font-family:{SANS};font-size:13px;line-height:19px;color:{MUTED};margin-top:2px;">{snippet}</div>'
            if snippet else ""
        )
        items.append(f"""
    <tr><td class="gti-rule" style="padding:12px 28px;border-top:1px solid {RULE};">
      <a href="{url}" class="gti-ink" style="font-family:{SANS};font-size:15px;font-weight:700;color:{INK};text-decoration:none;">{_esc(m["full_name"])}</a>
      &nbsp;{_pill(_esc(m["tag"]), BLUE, "#e8f0fe")}
      {snippet_html}
    </td></tr>""")
    return f"""
    <tr><td style="padding:30px 28px 14px;">
      <div class="gti-ink" style="font-family:{SANS};font-size:20px;font-weight:800;color:{INK};">What shipped</div>
      <div class="gti-dim" style="font-family:{SANS};font-size:13px;color:{DIM};margin-top:2px;">Releases this week from the repos we track</div>
    </td></tr>
    {"".join(items)}"""


def _html_body(breakouts, movers, shipped, date_range: str) -> str:
    site = _site()
    story = _big_story_line(breakouts, movers)
    story_block = (
        f"""
    <tr><td style="padding:24px 28px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td bgcolor="{ACCENT_BG}" class="gti-story gti-ink" style="background:{ACCENT_BG};border-left:4px solid {ACCENT};border-radius:6px;padding:14px 16px;font-family:{SANS};font-size:15px;line-height:22px;color:{INK};">
          <div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{ACCENT};margin-bottom:3px;">Big story</div>
          {_esc(story)}
        </td>
      </tr></table>
    </td></tr>"""
        if story else ""
    )
    preheader = _esc(story or "This week's fastest-rising GitHub repositories")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>FirstLight - Weekly Digest</title>
<style>
@media (prefers-color-scheme: dark) {{
  body, .gti-bg {{ background:#0f1115 !important; }}
  .gti-card {{ background:#181b21 !important; border-color:#2a2f38 !important; }}
  .gti-ink {{ color:#f3f4f6 !important; }}
  .gti-muted {{ color:#b6bcc6 !important; }}
  .gti-dim {{ color:#8b93a1 !important; }}
  .gti-rule {{ border-color:#2a2f38 !important; }}
  .gti-story {{ background:#2a1d14 !important; }}
}}
</style></head>
<body class="gti-bg" style="margin:0;padding:0;background:{BODY};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="gti-bg" bgcolor="{BODY}" style="background:{BODY};">
    <tr><td bgcolor="{ACCENT}" align="center" style="background:{ACCENT};padding:20px 12px;">
      <table role="presentation" width="720" cellpadding="0" cellspacing="0" style="width:720px;max-width:100%;"><tr><td style="padding:0 8px;">
        <a href="{site}" style="font-family:{SANS};font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#ffffff;text-decoration:none;">&#9733;&nbsp; FirstLight</a>
      </td></tr></table>
    </td></tr>
    <tr><td align="center" style="padding:28px 12px;">
      <table role="presentation" width="720" cellpadding="0" cellspacing="0" class="gti-card" bgcolor="{CARD}" style="width:720px;max-width:100%;background:{CARD};border:1px solid {RULE};border-radius:12px;overflow:hidden;">

        <tr><td style="padding:28px 28px 0;">
          <div class="gti-ink" style="font-family:{SANS};font-size:28px;line-height:34px;font-weight:800;color:{INK};">Your weekly digest</div>
          <div class="gti-dim" style="font-family:{SANS};font-size:14px;color:{DIM};margin-top:4px;">{date_range}</div>
        </td></tr>

        {story_block}
        {_section("Breakouts", "New repos that are accelerating fast", breakouts, True)}
        {_section("Top movers", "Ranked by momentum", movers, False)}
        {_shipped_section(shipped)}

        <tr><td align="center" class="gti-rule" style="padding:28px 28px 8px;border-top:1px solid {RULE};">
          <a href="{site}/this-week" style="display:inline-block;background:{ACCENT};color:#ffffff;font-family:{SANS};font-size:15px;font-weight:700;text-decoration:none;padding:12px 26px;border-radius:8px;">Open the live dashboard</a>
        </td></tr>

        <tr><td class="gti-dim" style="padding:18px 28px 26px;font-family:{SANS};font-size:12px;line-height:18px;color:{DIM};text-align:center;">
          Momentum is a 0&ndash;100 velocity score (stars, forks, contributors, commits), not a raw star count.
          &ldquo;Backed by activity&rdquo; means the growth is matched by real commits or contributors.
        </td></tr>
      </table>
      <div class="gti-dim" style="font-family:{SANS};font-size:12px;color:{DIM};margin-top:14px;line-height:18px;">
        You&rsquo;re receiving this because you subscribed to the FirstLight weekly digest.<br>
        <a href="{site}" style="color:{DIM};">FirstLight</a>
      </div>
    </td></tr>
  </table>
</body></html>"""


async def main() -> None:
    if not any_channel_configured():
        print("No notification channel configured; skipping digest.")
        return

    now = datetime.now(timezone.utc)
    date_range = f"{(now - timedelta(days=7)):%b %d} - {now:%b %d, %Y}"

    async with AsyncSessionLocal() as session:
        breakouts, movers, shipped = await fetch_digest(session)

    text_body = _text_body(breakouts, movers, shipped, date_range)
    html_body = _html_body(breakouts, movers, shipped, date_range)

    await notify("FirstLight -- Weekly Digest", text_body, html_body)
    print(f"Digest sent: {len(breakouts)} breakouts, {len(movers)} movers, {len(shipped)} releases")


if __name__ == "__main__":
    asyncio.run(main())
