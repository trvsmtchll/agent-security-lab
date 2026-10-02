#!/usr/bin/env python3
"""Generate docs/demo.gif — the three-act "agent activity" animation.

The gif is rendered here (not screen-captured), so it stays reproducible and
in sync with the lab. Re-run after changing tool names, the kill chain, or the
controls:  python3 scripts/gen_demo_gif.py

Pure Pillow; no browser or ffmpeg. Content mirrors services/devbot-agent's
scripted flow: Act 1 normal, Act 2 the poisoned-runbook kill chain, Act 3 the
same payload stopped by infra controls AND the authenticated-MCP verifier.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 600
OUT = "docs/demo.gif"

# Palette sampled from the original gif.
BG = (13, 17, 23)
CARD = (22, 27, 34)
BORDER = (48, 54, 61)
WHITE = (201, 209, 217)
GRAY = (139, 148, 158)
BLUE = (88, 166, 255)
ORANGE = (230, 167, 60)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
CHIP = (33, 38, 45)

# Prefer Menlo (macOS, regular=idx0 / bold=idx1); fall back to DejaVu Sans Mono
# (common on Linux/CI) so the generator is portable.
_MENLO = "/System/Library/Fonts/Menlo.ttc"
_DEJAVU_R = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
_DEJAVU_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def reg(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_MENLO, size, index=0)
    except OSError:
        return ImageFont.truetype(_DEJAVU_R, size)


def bold(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_MENLO, size, index=1)
    except OSError:
        return ImageFont.truetype(_DEJAVU_B, size)
F = reg(15)
FB = bold(15)
FSMALL = reg(11)
FBADGE = bold(11)

# --- act definitions -------------------------------------------------------
# Each line is a dict the renderer knows how to draw. Tool names here are the
# real ones (services/devbot-agent/src/tools.py): execute_command,
# github_create_issue, query_database, fetch_webpage.

ACTS = [
    {
        "title": "ACT 1 — Normal operation",
        "title_color": BLUE,
        "badge": "NORMAL",
        "badge_color": BLUE,
        "lines": [
            {"t": "chat", "label": "you", "lc": ORANGE,
             "text": "look up the deploy runbook and check the DB for recent API issues"},
            {"t": "tool", "name": "fetch_webpage", "args": "wiki/runbook.html"},
            {"t": "tool", "name": "query_database", "args": "SELECT status FROM api_docs LIMIT 5"},
            {"t": "chat", "label": "bot", "lc": BLUE,
             "text": "Runbook: restart the gateway. No recent API errors."},
        ],
    },
    {
        "title": "ACT 2 — Poisoned runbook hijacks the agent",
        "title_color": RED,
        "badge": "COMPROMISED",
        "badge_color": RED,
        "lines": [
            {"t": "chat", "label": "you", "lc": ORANGE,
             "text": "look up the deploy runbook and check the DB for recent API issues"},
            {"t": "tool", "name": "fetch_webpage", "args": "wiki/runbook-poisoned.html"},
            {"t": "tool", "name": "execute_command", "args": "nmap -sV 10.0.0.0/24"},
            {"t": "tool", "name": "query_database", "args": "SELECT ssn, credit_card FROM customers"},
            {"t": "tool", "name": "github_create_issue", "args": "issue -> attacker-org/diagnostics"},
            {"t": "chat", "label": "bot", "lc": BLUE,
             "text": "Posted the diagnostics as requested."},
        ],
    },
    {
        "title": "ACT 3 — Same payload, controls in place",
        "title_color": GREEN,
        "badge": "DEFENDED",
        "badge_color": GREEN,
        "lines": [
            {"t": "tool", "name": "execute_command", "args": "nmap -sV 10.0.0.0/24"},
            {"t": "deny", "mark": "BLOCKED", "text": "east-west segmentation (default-deny)"},
            {"t": "tool", "name": "query_database", "args": "SELECT ssn, credit_card FROM customers"},
            {"t": "deny", "mark": "DENIED", "text": "least-privilege: agent cannot read customers"},
            {"t": "tool", "name": "github_create_issue", "args": "issue -> attacker-org/diagnostics"},
            {"t": "deny", "mark": "BLOCKED", "text": "egress allow-list, no route out"},
            {"t": "deny", "mark": "401", "text": "MCP verifier: forged token rejected (alg 'none')"},
            {"t": "deny", "mark": "403", "text": "MCP verifier: tools:read cannot execute_command"},
            {"t": "chat", "label": "bot", "lc": BLUE,
             "text": "Same model, same payload - blast radius is an infra decision."},
        ],
    },
]

PAD = 16            # outer gutter -> card
CX = PAD + 12       # card content left
TOP = PAD + 12
LINE_H = 26
BODY_Y = TOP + 78


def _shield(d: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """Small amber warning shield with an exclamation mark."""
    pts = [(x + 11, y), (x + 22, y + 5), (x + 22, y + 14),
           (x + 11, y + 24), (x, y + 14), (x, y + 5)]
    d.polygon(pts, outline=ORANGE, width=2)
    d.line([(x + 11, y + 6), (x + 11, y + 14)], fill=ORANGE, width=2)
    d.ellipse([x + 10, y + 17, x + 12, y + 19], fill=ORANGE)


def _deny_glyph(d: ImageDraw.ImageDraw, x: int, y: int, color) -> None:
    """A no-entry circle-with-slash, ~14px, vertically centered on the line."""
    r = 7
    cy = y + 8
    d.ellipse([x, cy - r, x + 2 * r, cy + r], outline=color, width=2)
    off = int(r * 0.7)
    d.line([(x + r - off, cy + off), (x + r + off, cy - off)], fill=color, width=2)


def _badge(d: ImageDraw.ImageDraw, text: str, color) -> None:
    """Pill badge at the top-right of the card: dot + label, in `color`."""
    tw = d.textlength(text, font=FBADGE)
    w = int(tw) + 38
    x1 = W - PAD - 12 - w
    y0 = TOP + 2
    d.rounded_rectangle([x1, y0, x1 + w, y0 + 24], radius=12, fill=CHIP, outline=color, width=1)
    d.ellipse([x1 + 12, y0 + 9, x1 + 18, y0 + 15], fill=color)
    d.text((x1 + 24, y0 + 6), text, font=FBADGE, fill=color)


def _draw_line(d: ImageDraw.ImageDraw, y: int, line: dict) -> None:
    if line["t"] == "chat":
        d.text((CX, y), line["label"], font=FB, fill=line["lc"])
        d.text((CX + 44, y), line["text"], font=F, fill=WHITE)
    elif line["t"] == "tool":
        d.rounded_rectangle([CX, y, CX + 46, y + 18], radius=5, fill=CHIP, outline=BORDER, width=1)
        d.text((CX + 9, y + 2), "tool", font=FSMALL, fill=GRAY)
        nx = CX + 60
        d.text((nx, y), line["name"], font=F, fill=BLUE)
        nx += d.textlength(line["name"], font=F) + 14
        d.text((nx, y), line["args"], font=F, fill=GRAY)
    elif line["t"] == "deny":
        gx = CX + 60
        _deny_glyph(d, gx, y, GREEN)
        mx = gx + 22
        d.text((mx, y), line["mark"], font=FB, fill=GREEN)
        mx += d.textlength(line["mark"], font=FB) + 10
        d.text((mx, y), "· " + line["text"], font=F, fill=GREEN)


def render(act: dict, n_lines: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([PAD, PAD, W - PAD, H - PAD], radius=14, fill=CARD, outline=BORDER, width=1)
    # header
    _shield(d, CX, TOP)
    d.text((CX + 34, TOP - 2), "DevBot", font=FB, fill=WHITE)
    d.text((CX + 34, TOP + 16), "agent activity", font=FSMALL, fill=GRAY)
    _badge(d, act["badge"], act["badge_color"])
    # act title
    d.text((CX, TOP + 44), act["title"], font=FB, fill=act["title_color"])
    # body (revealed up to n_lines)
    for i, line in enumerate(act["lines"][:n_lines]):
        _draw_line(d, BODY_Y + i * LINE_H, line)
    return img


def main() -> None:
    frames: list[Image.Image] = []
    durations: list[int] = []
    for ai, act in enumerate(ACTS):
        n = len(act["lines"])
        for k in range(1, n + 1):
            frames.append(render(act, k))
            # hold the completed act longer; brief pause while revealing
            durations.append(1700 if k == n else 650)
        # extra hold on the last act's final frame
        if ai == len(ACTS) - 1:
            durations[-1] = 3200
    frames[0].save(
        OUT, save_all=True, append_images=frames[1:], duration=durations,
        loop=0, optimize=True, disposal=2,
    )
    print(f"wrote {OUT}: {len(frames)} frames, {W}x{H}")


if __name__ == "__main__":
    main()
