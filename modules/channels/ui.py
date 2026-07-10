"""
EVA Channels — dependency-free iconized dashboard (``GET /``).

Renders a dark-theme table of channel items using only inline SVG icons drawn
with ``currentColor`` — no CDN, no external packages, no JS framework. An SVG
``<defs>`` sprite declares every glyph once and each cell references it with
``<use>``:

  platform : reddit (antenna/robot head), substack (stacked layers)
  status   : draft=pencil, approved=check, posted=arrow-up-right, failed=warning
  actions  : publish=send, approve=check, edit=pencil

This is built iconized from day one so it already satisfies the UI iconization
pass; a later shared sprite system can drop in without reworking the markup.
"""

from __future__ import annotations

import html

# ---------------------------------------------------------------------------
# Inline SVG sprite — every icon defined once, referenced via <use href="#..">.
# All paths use stroke/fill currentColor so colour is driven by CSS.
# ---------------------------------------------------------------------------

ICON_SPRITE = """
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <!-- platform: reddit (antenna head) -->
    <symbol id="ic-reddit" viewBox="0 0 24 24">
      <circle cx="12" cy="14" r="7" fill="none" stroke="currentColor" stroke-width="1.6"/>
      <circle cx="9" cy="13.5" r="1.1" fill="currentColor"/>
      <circle cx="15" cy="13.5" r="1.1" fill="currentColor"/>
      <path d="M9 17c1.8 1.2 4.2 1.2 6 0" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
      <path d="M12 7l1-3 3 .7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="16.3" cy="4.6" r="1.2" fill="currentColor"/>
    </symbol>
    <!-- platform: substack (stacked layers) -->
    <symbol id="ic-substack" viewBox="0 0 24 24">
      <rect x="5" y="4" width="14" height="2.4" fill="currentColor"/>
      <rect x="5" y="9" width="14" height="2.4" fill="currentColor"/>
      <path d="M5 14h14v6l-7-3.2L5 20z" fill="currentColor"/>
    </symbol>
    <!-- status: draft (pencil) -->
    <symbol id="ic-pencil" viewBox="0 0 24 24">
      <path d="M4 20h4L18.5 9.5a2 2 0 0 0-2.8-2.8L5 17.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
      <path d="M14 8l2.8 2.8" fill="none" stroke="currentColor" stroke-width="1.6"/>
    </symbol>
    <!-- status: approved / action approve (check) -->
    <symbol id="ic-check" viewBox="0 0 24 24">
      <path d="M5 13l4 4L19 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </symbol>
    <!-- status: posted (arrow up-right) -->
    <symbol id="ic-arrow-up-right" viewBox="0 0 24 24">
      <path d="M7 17L17 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <path d="M8 7h9v9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </symbol>
    <!-- status: failed (warning triangle) -->
    <symbol id="ic-warning" viewBox="0 0 24 24">
      <path d="M12 4l9 16H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
      <path d="M12 10v4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      <circle cx="12" cy="17" r="1.1" fill="currentColor"/>
    </symbol>
    <!-- action: publish (send / paper plane) -->
    <symbol id="ic-send" viewBox="0 0 24 24">
      <path d="M4 12l16-7-7 16-2.5-6.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
    </symbol>
  </defs>
</svg>
"""

# Platform -> icon id + label.
_PLATFORM_ICON = {"reddit": "ic-reddit", "substack": "ic-substack"}
# Status -> icon id (draft=pencil, approved=check, posted=arrow, failed=warning).
_STATUS_ICON = {
    "draft": "ic-pencil",
    "approved": "ic-check",
    "posted": "ic-arrow-up-right",
    "failed": "ic-warning",
}


def _icon(icon_id: str, cls: str = "") -> str:
    cls_attr = f' class="{cls}"' if cls else ""
    return f'<svg class="ic {cls}" aria-hidden="true"><use href="#{icon_id}"/></svg>'


def _status_badge(status: str) -> str:
    icon_id = _STATUS_ICON.get(status, "ic-pencil")
    return (
        f'<span class="badge badge-{html.escape(status)}">'
        f'{_icon(icon_id)}{html.escape(status)}</span>'
    )


def _platform_cell(platform: str) -> str:
    icon_id = _PLATFORM_ICON.get(platform, "ic-substack")
    return (
        f'<span class="plat plat-{html.escape(platform)}">'
        f'{_icon(icon_id)}{html.escape(platform)}</span>'
    )


def _actions_cell(item: dict) -> str:
    status = item["status"]
    buttons = []
    if status == "draft":
        buttons.append(f'<button class="btn" title="approve">{_icon("ic-check")}approve</button>')
        buttons.append(f'<button class="btn" title="edit">{_icon("ic-pencil")}edit</button>')
    elif status == "approved":
        buttons.append(f'<button class="btn btn-go" title="publish">{_icon("ic-send")}publish</button>')
    elif status == "failed":
        buttons.append(f'<button class="btn btn-go" title="publish">{_icon("ic-send")}retry</button>')
    else:  # posted
        buttons.append('<span class="muted">—</span>')
    return "".join(buttons)


def _post_url_cell(item: dict) -> str:
    url = item.get("post_url", "")
    if not url:
        return '<span class="muted">—</span>'
    safe = html.escape(url)
    return f'<a class="link" href="{safe}" target="_blank" rel="noopener">{_icon("ic-arrow-up-right")}{safe}</a>'


def _row(item: dict) -> str:
    return (
        "<tr>"
        f'<td>{_platform_cell(item["platform"])}</td>'
        f'<td class="title">{html.escape(item.get("title", ""))}</td>'
        f'<td>{_status_badge(item.get("status", "draft"))}</td>'
        f'<td class="muted">{html.escape(item.get("posted_at", "") or "—")}</td>'
        f'<td>{_post_url_cell(item)}</td>'
        f'<td class="actions">{_actions_cell(item)}</td>'
        "</tr>"
    )


_STYLE = """
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--muted:#8b949e;
--reddit:#ff4500;--substack:#ff6719;--draft:#8b949e;--approved:#3fb950;
--posted:#58a6ff;--failed:#f85149;--go:#238636;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:20px 28px;border-bottom:1px solid var(--line);display:flex;
align-items:center;gap:12px}
header h1{font-size:17px;margin:0;font-weight:600}
header .ver{color:var(--muted);font-size:12px}
main{padding:24px 28px;max-width:1100px;margin:0 auto}
.ic{width:16px;height:16px;vertical-align:-3px;margin-right:6px}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);
font-size:13px;vertical-align:middle}
th{color:var(--muted);font-weight:600;text-transform:uppercase;
letter-spacing:.04em;font-size:11px}
tr:last-child td{border-bottom:none}
td.title{font-weight:500;max-width:280px}
.muted{color:var(--muted)}
.plat{display:inline-flex;align-items:center;font-weight:600}
.plat-reddit{color:var(--reddit)} .plat-substack{color:var(--substack)}
.badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:20px;
font-size:12px;font-weight:600;border:1px solid currentColor}
.badge-draft{color:var(--draft)} .badge-approved{color:var(--approved)}
.badge-posted{color:var(--posted)} .badge-failed{color:var(--failed)}
.link{color:var(--posted);text-decoration:none;display:inline-flex;align-items:center}
.link:hover{text-decoration:underline}
.actions{white-space:nowrap}
.btn{background:transparent;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:4px 9px;margin-right:6px;font-size:12px;cursor:pointer;
display:inline-flex;align-items:center}
.btn:hover{border-color:var(--muted)}
.btn-go{border-color:var(--go);color:#7ee787}
.empty{padding:40px;text-align:center;color:var(--muted)}
footer{padding:16px 28px;color:var(--muted);font-size:12px;text-align:center}
"""


def render_dashboard(items: list[dict], version: str = "1.0.0") -> str:
    if items:
        rows = "".join(_row(it) for it in items)
        body = (
            "<table><thead><tr>"
            "<th>Platform</th><th>Title</th><th>Status</th>"
            "<th>Posted at</th><th>Post URL</th><th>Actions</th>"
            "</tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    else:
        body = '<div class="empty">No channel items yet. Create one via the API or CLI.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EVA Channels</title><style>{_STYLE}</style></head>
<body>{ICON_SPRITE}
<header>
  {_icon("ic-send", "hdr")}
  <h1>EVA Channels</h1>
  <span class="ver">multi-platform publish · v{html.escape(version)}</span>
</header>
<main>{body}</main>
<footer>Reddit + Substack transports · approval-gated · append-only ledger</footer>
</body></html>"""
