# build_projects.py
# -*- coding: utf-8 -*-
"""Self-hosted "Project Portfolio" panel + collapsed project tables for the profile README.

The project list lives in the README between <!-- PROJECTS:START --> and <!-- PROJECTS:END -->
as ordinary table rows. This script (stdlib only, idempotent):

  * parses every row in that block (name, repo URL, highlights, demo link),
  * regroups them into collapsed categories (CATS / CAT_OF below),
  * derives the numbers (projects, live demos, platforms, newest) -> badges/projects_panel.svg
    (animated LED panel in the same family as the Repo Health panel),
  * rewrites the block.

To add a project: paste a new row anywhere inside the block and run the script (the daily
repo_board workflow does it too). A row it has not seen before counts as the newest one.

Style: PROJECTS_STYLE=chameleon (site palette, glowing contour) | phosphor (retro CRT terminal)
       | radar (sweeping radar, one blip per project) | splitflap (airport departure board)
       | synthwave (neon sunset grid) | blueprint (engineering drawing).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from build_repo_board import (  # same palette, LED digits and bar helper as the Repo Health panel
    FONT, GRID, PAD, STATUS_CSS, SURFACE, SW, SH, TEXT_MUTED, TEXT_PRIMARY, TEXT_SOFT,
    _esc, _stack, seven_seg,
)

README = Path(os.getenv("PROJECTS_README", "README.md"))
OUT_DIR = Path(os.getenv("PROJECTS_OUT", "badges"))
STYLE = os.getenv("PROJECTS_STYLE", "radar")
ASSET_BASE = "badges"

# key -> (heading, short label, colour in the panel bar)
CATS = {
    "ai": ("🧠 AI & Cloudflare systems", "AI", "#bb9af7"),
    "apps": ("📊 Live data apps & dashboards", "Apps", "#7aa2f7"),
    "bi": ("📈 Analytics, BI & SQL", "BI", "#e0af68"),
    "mlops": ("🐳 MLOps & pipelines", "MLOps", "#73daca"),
}
CAT_OF = {
    "agent-memory": "ai", "civics-sql-rag": "ai", "mcp-data-quality-agent": "ai",
    "interview-coach": "ai", "mlops_ollama_env": "ai",
    "route-optimization-vrp": "apps", "crypto-dashboard": "apps", "layoffs-tracker": "apps",
    "so-survey-analytics": "apps", "weather-pipeline": "apps", "job-market-pulse": "apps",
    "uber-driver-analytics": "apps", "olist-e-commerce-analytics": "apps",
    "tableau-business-cases": "bi", "hr-bi-analytics-project": "bi", "business-sql-analytics": "bi",
    "nyc-311-duckdb-motherduck-analysis": "bi", "remote-job-tracker": "bi", "Snowflake-A-Z": "bi",
    "cv-logistics-mlops": "mlops", "mlops_project": "mlops", "data-pipeline-etl-project": "mlops",
}
DEFAULT_CAT = "apps"

# demo host -> (label, colour)
PLATFORMS = {
    "streamlit.app": ("Streamlit", "#f7768e"),
    "huggingface.co": ("HF Spaces", "#e0af68"),
    "github.io": ("Pages", "#7aa2f7"),
    "tableau.com": ("Tableau", "#73daca"),
}

ROW = re.compile(r"^\| (?P<icon>\S+) \[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)\) \| (?P<hl>.*?) \| (?P<demo>.*?) \|\s*$")
HEAD = "| Project | Highlights | Demo |"


class Row:
    def __init__(self, m: "re.Match[str]", line: str) -> None:
        self.line = line.rstrip()
        self.name = m["name"]
        self.url = m["url"]
        self.slug = m["url"].rstrip("/").rsplit("/", 1)[-1]
        links = re.findall(r"\]\((https?://[^)\s]+)\)", m["demo"])
        self.demo: Optional[str] = links[-1] if links else None
        self.platform: Optional[str] = None
        for host, (label, _c) in PLATFORMS.items():
            if self.demo and host in self.demo:
                self.platform = label

    @property
    def cat(self) -> str:
        return CAT_OF.get(self.slug, DEFAULT_CAT)


# ----------------------------------------------------------------- parse / render markdown ---
def parse_rows(block: str) -> List[Row]:
    rows = []
    for line in block.split("\n"):
        m = ROW.match(line)
        if m:
            rows.append(Row(m, line))
    return rows


def saved_order(block: str) -> List[str]:
    m = re.search(r"<!-- order: ([^>]*?) -->", block)
    return [s for s in m.group(1).split(",") if s] if m else []


def global_order(rows: List[Row], saved: List[str]) -> List[Row]:
    """Newest first. Rows the script has not seen before are new -> they go in front."""
    by = {r.slug: r for r in rows}
    fresh = [r for r in rows if r.slug not in saved]
    return fresh + [by[s] for s in saved if s in by]


def build_block(ordered: List[Row], img_html: str) -> str:
    parts = [img_html, ""]
    for key, (heading, _short, _c) in CATS.items():
        rows = [r for r in ordered if r.cat == key]
        if not rows:
            continue
        parts += [f"<details>\n<summary><b>{heading}</b> <em>({len(rows)})</em></summary>", "",
                  HEAD, "|---------|-----------|------|"] + [r.line for r in rows] + ["", "</details>", ""]
    parts.append(f"<!-- order: {','.join(r.slug for r in ordered)} -->")
    return "\n".join(parts)


# ----------------------------------------------------------------- SVG ---
def stats(ordered: List[Row]) -> Dict[str, object]:
    live = [r for r in ordered if r.demo]
    plats: Dict[str, int] = {}
    for r in live:
        if r.platform:
            plats[r.platform] = plats.get(r.platform, 0) + 1
    cats = {k: sum(r.cat == k for r in ordered) for k in CATS}
    items = [{"cat": r.cat, "live": bool(r.demo), "plat": r.platform, "newest": i == 0}
             for i, r in enumerate(ordered)]
    return {"n": len(ordered), "live": len(live), "plats": plats, "cats": cats, "items": items,
            "newest": re.sub(r"\s+", " ", ordered[0].name).strip() if ordered else "—"}


CHAMELEON_CSS = STATUS_CSS  # contour + LED digits + shine: identical animation to the Repo Health panel

PHOSPHOR_G, PHOSPHOR_A = "#39ff88", "#ffb000"
PHOSPHOR_CSS = (
    "@keyframes up{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}"
    "@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
    "@keyframes breathe{0%,100%{opacity:.35}50%{opacity:1}}"
    "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
    "@keyframes scan{0%{transform:translateY(-30px)}100%{transform:translateY(" + str(SH + 10) + "px)}}"
    "@keyframes flick{0%,90%,100%{opacity:1}92%{opacity:.78}94%{opacity:1}96%{opacity:.88}}"
    ".t{animation:up .7s ease-out both}"
    ".b{transform-box:fill-box;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}"
    ".br{fill:none;stroke:" + PHOSPHOR_G + ";stroke-linecap:square}"
    ".brg{animation:breathe 3s ease-in-out infinite}"
    ".cur{animation:blink 1.1s steps(1) infinite}"
    ".scan{animation:scan 5.5s linear infinite}"
    ".fl{animation:flick 7s linear infinite}"
    ".seg{fill:" + PHOSPHOR_A + "}"
    ".off{opacity:.09}"
)
PHOSPHOR_PLAT = {"Streamlit": "#39ff88", "HF Spaces": "#ffb000", "Pages": "#7dffd0", "Tableau": "#ffd36b"}
PHOSPHOR_CAT = {"ai": "#39ff88", "apps": "#7dffd0", "bi": "#ffb000", "mlops": "#c8ff6b"}


def _bar_block(p: List[str], x: float, half: float, title: str, segs: List[tuple], delay: float,
               text_col: str, muted: str, gap: float = 24.0, cw: float = 5.6) -> None:
    p.append(f'<text x="{x:.0f}" y="104" font-size="9.5" fill="{muted}" letter-spacing="1">{title}</text>')
    _stack(p, x, 109, half, [(c, col) for _l, c, col in segs], delay)
    cx = x
    for label, c, col in segs:
        p.append(f'<circle cx="{cx + 4:.0f}" cy="135" r="3.5" fill="{col}"/>')
        text = f"{label} {c}"
        p.append(f'<text x="{cx + 12:.0f}" y="138" font-size="10" fill="{text_col}">{_esc(text)}</text>')
        cx += gap + len(text) * cw


def build_svg_classic(st: Dict[str, object], style: str) -> str:
    phos = style == "phosphor"
    surface = "#0a1410" if phos else SURFACE
    muted = "#4f8a66" if phos else TEXT_MUTED
    soft = "#9fdcb4" if phos else TEXT_SOFT
    primary = "#b8ffd2" if phos else TEXT_PRIMARY
    font = "ui-monospace,SFMono-Regular,Consolas,'Courier New',monospace" if phos else FONT
    n_ai = st["cats"]["ai"]  # type: ignore[index]
    tiles = [(str(st["n"]), "projects"), (str(st["live"]), "live demos"),
             (str(n_ai), "AI & cloud systems"), (str(len(st["plats"])), "demo platforms")]  # type: ignore[arg-type]

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW + 2 * PAD}" height="{SH + 2 * PAD}" '
         f'viewBox="0 0 {SW + 2 * PAD} {SH + 2 * PAD}" font-family="{font}">'
         f'<style>{PHOSPHOR_CSS if phos else CHAMELEON_CSS}</style>',
         '<defs><filter id="glow" x="-15%" y="-80%" width="130%" height="260%"><feGaussianBlur stdDeviation="6"/></filter>'
         '<filter id="segglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.5" result="b"/>'
         '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
         '<filter id="halo" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="10"/></filter>'
         '<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
         '<stop offset="0.5" stop-color="#fff" stop-opacity="0.09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
         f'<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{PHOSPHOR_G}" stop-opacity="0"/>'
         f'<stop offset="1" stop-color="{PHOSPHOR_G}" stop-opacity="0.13"/></linearGradient>'
         '<pattern id="lines" width="4" height="3" patternUnits="userSpaceOnUse">'
         f'<rect width="4" height="1" fill="{PHOSPHOR_G}" opacity="0.05"/></pattern>'
         f'<clipPath id="panel"><rect width="{SW}" height="{SH}" rx="{3 if phos else 8}"/></clipPath></defs>',
         f'<g transform="translate({PAD} {PAD})">',
         f'<rect width="{SW}" height="{SH}" fill="{surface}" rx="{3 if phos else 8}"/>']

    edge = f'x="1" y="1" width="{SW - 2}" height="{SH - 2}" rx="8"'
    if phos:
        # CRT corner brackets (glow copy + sharp copy) instead of a full contour
        L, a, b = 26, 6, SW - 6
        c = SH - 6
        d = (f"M{a},{a + L} V{a} H{a + L} M{b - L},{a} H{b} V{a + L} "
             f"M{b},{c - L} V{c} H{b - L} M{a + L},{c} H{a} V{c - L}")
        p.append(f'<path class="br brg" d="{d}" stroke-width="7" filter="url(#glow)"/>')
        p.append(f'<path class="br" d="{d}" stroke-width="1.8"/>')
        p.append(f'<rect class="cur" x="18" y="14" width="7" height="13" fill="{PHOSPHOR_G}"/>')
    else:
        p.append(f'<rect class="glow" {edge} stroke-width="16" filter="url(#halo)"/>')
        p.append(f'<rect class="glow" {edge} stroke-width="9" filter="url(#glow)"/>')
        p.append(f'<rect class="edge" {edge} stroke-width="1.6"/>')
        p.append('<circle class="live" cx="22" cy="21" r="4" fill="#9ece6a"/>')
    p.append(f'<text x="34" y="25" font-size="11" font-weight="600" fill="{primary}" letter-spacing="1.2">'
             f'PROJECT PORTFOLIO</text>')
    p.append(f'<text x="{SW - 16}" y="25" font-size="10" fill="{muted}" text-anchor="end">'
             f'newest: {_esc(str(st["newest"]))}</text>')

    tw = (SW - 32) / len(tiles)
    for i, (num, label) in enumerate(tiles):
        x = 16 + i * tw
        digits = seven_seg(x, 38, num, False)
        if phos:
            digits = f'<g class="fl" style="animation-delay:{i * 1.3:.1f}s">{digits}</g>'
        p.append(f'<g class="t" style="animation-delay:{i * 0.12:.2f}s">{digits}'
                 f'<text x="{x:.0f}" y="82" font-size="10.5" fill="{muted}">{_esc(label)}</text></g>')

    half = (SW - 48) / 2
    cat_segs = [(CATS[k][1], v, (PHOSPHOR_CAT[k] if phos else CATS[k][2]))
                for k, v in st["cats"].items() if v]  # type: ignore[union-attr]
    plat_segs = [(lab, st["plats"][lab], (PHOSPHOR_PLAT[lab] if phos else col))  # type: ignore[index]
                 for _h, (lab, col) in PLATFORMS.items() if lab in st["plats"]]  # type: ignore[operator]
    _bar_block(p, 16, half, "BY CATEGORY", cat_segs, 0.5, soft, muted)
    _bar_block(p, 32 + half, half, "LIVE DEMOS ON", plat_segs, 0.7, soft, muted)

    if phos:
        p.append(f'<g clip-path="url(#panel)"><rect width="{SW}" height="{SH}" fill="url(#lines)"/>'
                 f'<rect class="scan" x="0" y="0" width="{SW}" height="30" fill="url(#beam)"/></g>')
    else:
        p.append(f'<g clip-path="url(#panel)"><rect class="shine" x="0" y="-10" width="150" height="{SH + 20}" '
                 f'fill="url(#sheen)"/></g>')
    p.append("</g></svg>")
    return "".join(p)


# ----------------------------------------------------------------- extra themes ---
# Every theme returns a complete SVG for the same SW x SH panel (+PAD for glow). Only <svg> + CSS
# animations, no fonts shipped, no scripts - renders inside the README's <img>.
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Courier New',monospace"
SHORT = {"ai": "AI & Cloudflare", "apps": "Live data apps", "bi": "Analytics, BI & SQL", "mlops": "MLOps & pipelines"}
BASE_CSS = (
    "@keyframes up{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}"
    "@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
    "@keyframes breathe{0%,100%{opacity:.3}50%{opacity:.95}}"
    ".t{animation:up .7s ease-out both}"
    ".b{transform-box:fill-box;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}"
    ".off{opacity:.09}"
)
SEGGLOW = ('<filter id="segglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.5" result="b"/>'
           '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
GLOW6 = '<filter id="glow" x="-15%" y="-80%" width="130%" height="260%"><feGaussianBlur stdDeviation="6"/></filter>'
HALO10 = '<filter id="halo" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="10"/></filter>'


def _open(font: str, css: str, defs: str, bg: str, rx: int) -> List[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW + 2 * PAD}" height="{SH + 2 * PAD}" '
            f'viewBox="0 0 {SW + 2 * PAD} {SH + 2 * PAD}" font-family="{font}"><style>{css}</style>'
            f'<defs>{defs}<clipPath id="panel"><rect width="{SW}" height="{SH}" rx="{rx}"/></clipPath></defs>',
            f'<g transform="translate({PAD} {PAD})">',
            f'<rect width="{SW}" height="{SH}" fill="{bg}" rx="{rx}"/>']


def _tile_list(st: Dict[str, object]) -> List[tuple]:
    return [(str(st["n"]), "projects"), (str(st["live"]), "live demos"),
            (str(st["cats"]["ai"]), "AI & cloud systems"),  # type: ignore[index]
            (str(len(st["plats"])), "demo platforms")]  # type: ignore[arg-type]


def _cat_segs(st: Dict[str, object], colors: Dict[str, str]) -> List[tuple]:
    return [(CATS[k][1], v, colors[k]) for k, v in st["cats"].items() if v]  # type: ignore[union-attr]


def _plat_segs(st: Dict[str, object], colors: List[str]) -> List[tuple]:
    out, i = [], 0
    for _h, (lab, _c) in PLATFORMS.items():
        if lab in st["plats"]:  # type: ignore[operator]
            out.append((lab, st["plats"][lab], colors[i % len(colors)]))  # type: ignore[index]
            i += 1
    return out


def _title(p: List[str], x: float, st: Dict[str, object], color: str, muted: str, extra: str = "") -> None:
    p.append(f'<text x="{x:.0f}" y="25" font-size="11" font-weight="600" fill="{color}" letter-spacing="1.4">'
             f'PROJECT PORTFOLIO</text>')
    p.append(f'<text x="{SW - 16}" y="25" font-size="10" fill="{muted}" text-anchor="end">'
             f'{extra}newest: {_esc(str(st["newest"]))}</text>')


def _pt(cx: float, cy: float, r: float, deg: float) -> tuple:
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


# ---- 1. RADAR: one blip per project, a sweep lights them up as it passes ----------------------
RADAR_T = 7.0
QUAD = {"ai": 270.0, "apps": 0.0, "bi": 90.0, "mlops": 180.0}  # quadrant start angle (clockwise from +x)
SHORT_TAG = {"ai": "AI", "apps": "APPS", "bi": "BI", "mlops": "MLOPS"}


def build_radar(st: Dict[str, object]) -> str:
    cx, cy, R = 84.0, 76.0, 62.0
    teal, muted, soft, primary = "#5ef0ff", "#58798d", "#a4c4d6", "#d9f6ff"
    css = (BASE_CSS
           + "@keyframes spin{to{transform:rotate(360deg)}}"
           "@keyframes ping{0%,6%{opacity:1}100%{opacity:.22}}"
           "@keyframes pingl{0%,6%{opacity:1}100%{opacity:.6}}"
           ".sweep{transform-box:fill-box;transform-origin:50% 50%;animation:spin " + str(RADAR_T) + "s linear infinite}"
           ".bl{opacity:.22;animation:ping " + str(RADAR_T) + "s linear infinite}"
           ".bl.lv{opacity:.6;animation-name:pingl}"
           "@keyframes rip{0%{transform:scale(.5);opacity:.75}55%,100%{transform:scale(2.4);opacity:0}}"
           "@keyframes rglow{0%,100%{opacity:.16}50%{opacity:.55}}"
           "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.15}}"
           ".rp{fill:none;opacity:0;transform-box:fill-box;transform-origin:50% 50%;animation:rip " + str(RADAR_T) + "s ease-out infinite}"
           ".lock{fill:none;transform-box:fill-box;transform-origin:50% 50%;animation:spin 5s linear infinite}"
           ".rg{fill:none;stroke:" + teal + ";animation:rglow 4s ease-in-out infinite}"
           ".cur{animation:blink 1.2s steps(1) infinite}"
           ".seg{fill:" + teal + "}")
    p = _open(FONT, css, SEGGLOW + GLOW6 + HALO10, "#0b141c", 8)
    edge = f'x="1" y="1" width="{SW - 2}" height="{SH - 2}" rx="8"'
    p.append(f'<rect class="rg" {edge} stroke-width="14" filter="url(#halo)"/>'
             f'<rect class="rg" {edge} stroke-width="7" filter="url(#glow)" style="animation-delay:-1s"/>'
             f'<rect {edge} fill="none" stroke="{teal}" stroke-width="1.1" opacity=".55"/>')
    ring = "#1b3342"
    for rr in (R, R * 2 / 3, R / 3):
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{rr:.1f}" fill="none" stroke="{ring}" stroke-width=".9"/>')
    p.append(f'<line x1="{cx - R}" y1="{cy}" x2="{cx + R}" y2="{cy}" stroke="{ring}" stroke-width=".9"/>'
             f'<line x1="{cx}" y1="{cy - R}" x2="{cx}" y2="{cy + R}" stroke="{ring}" stroke-width=".9"/>')
    for deg in range(0, 360, 30):
        x1, y1 = _pt(cx, cy, R, deg)
        x2, y2 = _pt(cx, cy, R + 4, deg)
        p.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{teal}" opacity=".35"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{teal}" stroke-width="1" opacity=".5"/>')
    # sweep: three trailing wedges (fading trail) + a bright leading edge; the invisible circle fixes the rotation centre
    sweep = ['<g class="sweep" style="animation-delay:0s"><circle cx="%s" cy="%s" r="%s" fill="none" stroke="none"/>' % (cx, cy, R)]
    for w, op in ((70, 0.06), (40, 0.08), (16, 0.12)):
        x0, y0 = _pt(cx, cy, R, -w)
        x1, y1 = _pt(cx, cy, R, 0)
        sweep.append(f'<path d="M{cx},{cy} L{x0:.1f},{y0:.1f} A{R},{R} 0 0 1 {x1:.1f},{y1:.1f} Z" fill="{teal}" opacity="{op}"/>')
    sweep.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + R}" y2="{cy}" stroke="{teal}" stroke-width="4" opacity=".55" '
                 f'filter="url(#glow)"/>'
                 f'<line x1="{cx}" y1="{cy}" x2="{cx + R}" y2="{cy}" stroke="#d9fbff" stroke-width="1.3"/></g>')
    p.append("".join(sweep))
    # sector labels in the four corners of the dial
    for key, (lx, ly, anc) in {"ai": (cx + 50, cy - 50, "start"), "apps": (cx + 50, cy + 56, "start"),
                               "bi": (cx - 42, cy + 56, "end"), "mlops": (cx - 42, cy - 50, "end")}.items():
        p.append(f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="8" font-weight="600" letter-spacing=".8" '
                 f'fill="{CATS[key][2]}" text-anchor="{anc}" opacity=".85">{SHORT_TAG[key]}</text>')
    # one blip per project, placed in its category's quadrant; lit when the sweep reaches its angle
    items = st["items"]  # type: ignore[assignment]
    for key, start in QUAD.items():
        grp = [it for it in items if it["cat"] == key]  # type: ignore[index]
        col = CATS[key][2]
        for i, it in enumerate(grp):
            deg = start + (i + 0.5) / len(grp) * 90.0
            rad = R * (0.34 + 0.56 * (((i * 7) + len(key) * 3) % 10) / 10.0)
            x, y = _pt(cx, cy, rad, deg)
            delay = deg / 360.0 * RADAR_T
            if it["live"]:  # type: ignore[index]
                p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{col}" opacity=".18"/>'
                         f'<circle class="rp" cx="{x:.1f}" cy="{y:.1f}" r="5" stroke="{col}" stroke-width="1" '
                         f'style="animation-delay:{delay:.2f}s"/>'
                         f'<circle class="bl lv" cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{col}" '
                         f'filter="url(#segglow)" style="animation-delay:{delay:.2f}s"/>')
            else:
                p.append(f'<circle class="bl" cx="{x:.1f}" cy="{y:.1f}" r="2.1" fill="{col}" '
                         f'style="animation-delay:{delay:.2f}s"/>')
            if it["newest"]:  # type: ignore[index]  # lock-on reticle around the newest project
                p.append(f'<circle class="lock" cx="{x:.1f}" cy="{y:.1f}" r="9" stroke="#d9fbff" stroke-width="1.1" '
                         f'stroke-dasharray="5 6.5"/>'
                         f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.4" fill="#ffffff"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="2" fill="{teal}"/>')

    x0 = 170.0
    wr = SW - x0 - 16
    _title(p, x0, st, primary, muted, f'<tspan fill="{teal}">◎ </tspan>')
    p.append(f'<text class="cur" x="{x0 + 150:.0f}" y="25" font-size="8.5" fill="{teal}" letter-spacing="1.2">● SCANNING</text>')
    tw = wr / 4
    for i, (num, label) in enumerate(_tile_list(st)):
        x = x0 + i * tw
        p.append(f'<g class="t" style="animation-delay:{i * 0.12:.2f}s">{seven_seg(x, 38, num, False)}'
                 f'<text x="{x:.0f}" y="82" font-size="10.5" fill="{muted}">{_esc(label)}</text></g>')
    half = (wr - 16) / 2
    cols = {k: CATS[k][2] for k in CATS}
    _bar_block(p, x0, half, "BY CATEGORY", _cat_segs(st, cols), 0.5, soft, muted, 18, 5.0)
    _bar_block(p, x0 + half + 16, half, "LIVE DEMOS ON", _plat_segs(st, [c for _l, (_n, c) in PLATFORMS.items()]),
               0.7, soft, muted, 18, 5.0)
    p.append("</g></svg>")
    return "".join(p)


# ---- 2. SPLIT-FLAP: airport departure board, digits flip through 0..n on load and every 16 s ------
FLAP_S, FLAP_LOOP = 0.07, 16.0


def _flap_css() -> str:
    s = FLAP_S / FLAP_LOOP * 100.0
    out = []
    for k in range(10):
        a, b = k * s, (k + 1) * s
        out.append("@keyframes sk%d{0%%,%.3f%%{opacity:0}%.3f%%,%.3f%%{opacity:1}%.3f%%,100%%{opacity:0}}"
                   % (k, a, a + 0.001, b, b + 0.001))
        out.append("@keyframes sf%d{0%%,%.3f%%{opacity:0}%.3f%%,100%%{opacity:1}}" % (k, a, a + 0.001))
    return "".join(out)


def build_splitflap(st: Dict[str, object]) -> str:
    amber, cream, muted, soft, green = "#ffb000", "#f3e3c0", "#8c7a55", "#d8c79c", "#7dff9c"
    css = (BASE_CSS + _flap_css()
           + ".fd{animation-duration:" + str(FLAP_LOOP) + "s;animation-iteration-count:infinite;"
           "animation-fill-mode:both;animation-timing-function:linear;opacity:0}")
    p = _open(MONO, css, "", "#12100c", 6)
    p.append(f'<rect x=".5" y=".5" width="{SW - 1}" height="{SH - 1}" rx="6" fill="none" stroke="#3a3326"/>')
    p.append(f'<text x="16" y="22" font-size="11" font-weight="700" fill="{amber}" letter-spacing="2">PROJECT PORTFOLIO</text>')
    p.append(f'<text x="{SW - 16}" y="22" font-size="10" fill="{muted}" text-anchor="end">newest: {_esc(str(st["newest"]))}</text>')
    cw, ch, gap, y0 = 30.0, 44.0, 4.0, 30.0
    tw = (SW - 32) / 4
    cell = 0
    for i, (num, label) in enumerate(_tile_list(st)):
        gx = 16 + i * tw
        for j, c in enumerate(num.zfill(2)):
            x = gx + j * (cw + gap)
            d = int(c)
            p.append(f'<rect x="{x}" y="{y0}" width="{cw}" height="{ch / 2}" rx="3" fill="#2a2620"/>'
                     f'<rect x="{x}" y="{y0 + ch / 2}" width="{cw}" height="{ch / 2}" rx="3" fill="#1d1a15"/>')
            delay = cell * 0.14
            for k in range(d + 1):
                name = f"sf{d}" if k == d else f"sk{k}"
                p.append(f'<text class="fd" x="{x + cw / 2}" y="{y0 + ch * 0.72:.1f}" font-size="34" font-weight="700" '
                         f'text-anchor="middle" fill="{cream}" style="animation-name:{name};animation-delay:{delay:.2f}s">{k}</text>')
            p.append(f'<rect x="{x}" y="{y0 + ch / 2 - 0.7}" width="{cw}" height="1.4" fill="#090806"/>'
                     f'<circle cx="{x + 1.6}" cy="{y0 + ch / 2}" r="1.4" fill="#090806"/>'
                     f'<circle cx="{x + cw - 1.6}" cy="{y0 + ch / 2}" r="1.4" fill="#090806"/>')
            cell += 1
        p.append(f'<text x="{gx:.0f}" y="90" font-size="10" fill="{muted}" letter-spacing=".6">{_esc(label.upper())}</text>')
    # departure rows: categories on the left, demo platforms on the right
    items = st["items"]  # type: ignore[assignment]
    cat_cols = {"ai": amber, "apps": cream, "bi": "#ff7b3a", "mlops": green}
    nmax = max(st["cats"].values()) or 1  # type: ignore[union-attr]
    for r, (k, n) in enumerate(st["cats"].items()):  # type: ignore[union-attr]
        y = 106 + r * 12
        live = sum(1 for it in items if it["cat"] == k and it["live"])  # type: ignore[index]
        p.append(f'<text x="16" y="{y}" font-size="9.5" fill="{soft}">{_esc(SHORT[k])}</text>'
                 f'<rect x="150" y="{y - 6}" width="{n / nmax * 130:.0f}" height="5" rx="1" fill="{cat_cols[k]}"/>'
                 f'<text x="292" y="{y}" font-size="9.5" fill="{cream}" text-anchor="end">{n:02d}</text>'
                 f'<text x="366" y="{y}" font-size="9" fill="{green if live else muted}" text-anchor="end">'
                 f'{"LIVE %d/%d" % (live, n) if live else "REPO ONLY"}</text>')
    plats = list(st["plats"].items())  # type: ignore[union-attr]
    pmax = max([c for _l, c in plats] or [1])
    for r, (lab, c) in enumerate(plats):
        y = 106 + r * 12
        p.append(f'<text x="386" y="{y}" font-size="9.5" fill="{soft}">{_esc(lab.upper())}</text>'
                 f'<rect x="490" y="{y - 6}" width="{c / pmax * 130:.0f}" height="5" rx="1" fill="{list(cat_cols.values())[r % 4]}"/>'
                 f'<text x="660" y="{y}" font-size="9.5" fill="{cream}" text-anchor="end">{c:02d}</text>'
                 f'<text x="728" y="{y}" font-size="9" fill="{green}" text-anchor="end">ON AIR</text>')
    p.append("</g></svg>")
    return "".join(p)


# ---- 3. SYNTHWAVE: neon sunset, scrolling perspective grid, hot-pink LED digits -----------------
def build_synthwave(st: Dict[str, object]) -> str:
    pink, cyan, violet, gold = "#ff4fd8", "#3df5ff", "#a77bff", "#ffd23f"
    primary, soft, muted = "#f6d6ff", "#d9b8ff", "#9a7cc4"
    css = (BASE_CSS + "@keyframes gm{to{transform:translateY(12px)}}"
           ".gm{animation:gm 1.6s linear infinite}"
           ".glow{fill:none;animation:breathe 3.2s ease-in-out infinite}.edge{fill:none}"
           ".seg{fill:" + pink + "}")
    stripes = "".join(f'<rect x="590" y="{y}" width="140" height="{h}" fill="#000"/>'
                      for y, h in ((66, 2), (73, 3), (80, 4), (88, 5)))
    defs = (SEGGLOW + GLOW6 + HALO10
            + '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#170a35"/>'
              '<stop offset=".7" stop-color="#2d0d52"/><stop offset="1" stop-color="#0c0720"/></linearGradient>'
              f'<linearGradient id="neon" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{pink}"/>'
              f'<stop offset=".5" stop-color="{violet}"/><stop offset="1" stop-color="{cyan}"/></linearGradient>'
              f'<linearGradient id="sun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{gold}"/>'
              f'<stop offset="1" stop-color="{pink}"/></linearGradient>'
              f'<mask id="sunm" maskUnits="userSpaceOnUse" x="590" y="20" width="140" height="100">'
              f'<rect x="590" y="20" width="140" height="100" fill="#fff"/>{stripes}</mask>'
              '<clipPath id="above"><rect width="%d" height="94"/></clipPath>'
              '<clipPath id="below"><rect y="94" width="%d" height="%d"/></clipPath>' % (SW, SW, SH - 94))
    p = _open(FONT, css, defs, "url(#sky)", 8)
    p.append('<g clip-path="url(#above)"><g mask="url(#sunm)">'
             '<circle cx="660" cy="66" r="36" fill="url(#sun)" opacity=".9"/></g></g>')
    grid = [f'<g clip-path="url(#below)" opacity=".3"><g class="gm">']
    for k in range(-1, 5):
        grid.append(f'<line x1="0" y1="{94 + 12 * k}" x2="{SW}" y2="{94 + 12 * k}" stroke="{pink}" stroke-width=".8"/>')
    grid.append("</g>")
    for i in range(-14, 15):
        grid.append(f'<line x1="{SW / 2 + i * 14:.0f}" y1="94" x2="{SW / 2 + i * 62:.0f}" y2="{SH}" stroke="{pink}" stroke-width=".8"/>')
    grid.append("</g>")
    p.append("".join(grid))
    p.append(f'<line x1="0" y1="94" x2="{SW}" y2="94" stroke="{pink}" stroke-width=".8" opacity=".6"/>')
    edge = f'x="1" y="1" width="{SW - 2}" height="{SH - 2}" rx="8" stroke="url(#neon)"'
    p.append(f'<rect class="glow" {edge} stroke-width="16" filter="url(#halo)"/>')
    p.append(f'<rect class="glow" {edge} stroke-width="9" filter="url(#glow)"/>')
    p.append(f'<rect class="edge" {edge} stroke-width="1.6"/>')
    _title(p, 16, st, primary, soft)
    tw = (576 - 16) / 4
    for i, (num, label) in enumerate(_tile_list(st)):
        x = 16 + i * tw
        p.append(f'<g class="t" style="animation-delay:{i * 0.12:.2f}s">{seven_seg(x, 38, num, False)}'
                 f'<text x="{x:.0f}" y="82" font-size="10.5" fill="{muted}">{_esc(label)}</text></g>')
    half = (560 - 16) / 2
    cc = {"ai": pink, "apps": cyan, "bi": gold, "mlops": violet}
    _bar_block(p, 16, half, "BY CATEGORY", _cat_segs(st, cc), 0.5, primary, muted)
    _bar_block(p, 16 + half + 16, half, "LIVE DEMOS ON", _plat_segs(st, [pink, cyan, gold, violet]), 0.7, primary, muted)
    p.append("</g></svg>")
    return "".join(p)


# ---- 4. BLUEPRINT: engineering drawing - grid paper, dimension lines, hatched bars, lines draw in ---
def _hatch_bar(p: List[str], x: float, w: float, segs: List[tuple], delay: float) -> None:
    total = sum(c for _l, c, _p, _col in segs) or 1
    p.append(f'<g class="b" style="animation-delay:{delay}s">')
    cx = x
    for _l, c, pid, col in segs:
        sw = c / total * w
        p.append(f'<rect x="{cx:.1f}" y="109" width="{sw:.1f}" height="9" fill="url(#{pid})" stroke="{col}" stroke-width=".9"/>')
        cx += sw
    p.append("</g>")


def _hatch_legend(p: List[str], x: float, segs: List[tuple], soft: str) -> None:
    cx = x
    for label, c, pid, col in segs:
        text = f"{label} {c}"
        p.append(f'<rect x="{cx:.0f}" y="127" width="12" height="9" fill="url(#{pid})" stroke="{col}" stroke-width=".9"/>'
                 f'<text x="{cx + 17:.0f}" y="135" font-size="10" fill="{soft}">{_esc(text)}</text>')
        cx += 17 + len(text) * 5.4 + 14


def build_blueprint(st: Dict[str, object]) -> str:
    ink, soft, muted, paper = "#e6f5ff", "#b9dcf2", "#7fb2d9", "#0c2b4d"
    hatch_cols = ["#7fd8ff", "#ffffff", "#ffe27a", "#8dffb0"]
    css = (BASE_CSS + "@keyframes dash{to{stroke-dashoffset:0}}"
           ".dr{fill:none;stroke-dasharray:1;stroke-dashoffset:1;animation:dash 2.2s ease-out forwards}"
           ".seg{fill:" + ink + "}")
    pats = ""
    for i, (rot, kind) in enumerate(((45, "l"), (-45, "l"), (0, "l"), (0, "d"))):
        col = hatch_cols[i]
        body = (f'<line x1="0" y1="0" x2="0" y2="4" stroke="{col}" stroke-width="1.1"/>' if kind == "l"
                else f'<circle cx="2" cy="2" r=".9" fill="{col}"/>')
        pats += (f'<pattern id="h{i}" width="4" height="4" patternUnits="userSpaceOnUse" '
                 f'patternTransform="rotate({rot})">{body}</pattern>')
    defs = (SEGGLOW + pats
            + '<pattern id="gm" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M8 0H0V8" fill="none" '
              'stroke="#5aa3d6" stroke-width=".4" opacity=".28"/></pattern>'
              '<pattern id="gM" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" '
              'stroke="#5aa3d6" stroke-width=".7" opacity=".4"/></pattern>')
    p = _open(FONT, css, defs, paper, 4)
    p.append(f'<rect width="{SW}" height="{SH}" rx="4" fill="url(#gm)"/><rect width="{SW}" height="{SH}" rx="4" fill="url(#gM)"/>')
    p.append(f'<rect x="2.5" y="2.5" width="{SW - 5}" height="{SH - 5}" fill="none" stroke="{muted}" stroke-width=".6" opacity=".6"/>')
    p.append(f'<rect class="dr" pathLength="1" x="7" y="7" width="{SW - 14}" height="{SH - 14}" stroke="{ink}" '
             f'stroke-width="1.3" style="animation-delay:0s"/>')
    for (mx, my) in ((7, 7), (SW - 7, 7), (7, SH - 7), (SW - 7, SH - 7)):  # drafting registration marks
        p.append(f'<circle cx="{mx}" cy="{my}" r="4.5" fill="{paper}" stroke="{ink}" stroke-width=".8"/>'
                 f'<path d="M{mx - 7},{my} H{mx + 7} M{mx},{my - 7} V{my + 7}" stroke="{ink}" stroke-width=".6"/>')
    p.append(f'<text x="22" y="27" font-size="11" font-weight="600" fill="{ink}" letter-spacing="1.4">PROJECT PORTFOLIO</text>')
    p.append(f'<text x="{SW - 22}" y="27" font-size="10" fill="{muted}" text-anchor="end">'
             f'REV {st["n"]} · newest: {_esc(str(st["newest"]))}</text>')
    tw = (SW - 44) / 4
    for i, (num, label) in enumerate(_tile_list(st)):
        x = 22 + i * tw
        x2 = x + tw - 30
        mid = (x + x2) / 2
        tw_txt = len(label) * 5.6 + 10
        p.append(f'<g class="t" style="animation-delay:{i * 0.12:.2f}s">{seven_seg(x, 38, num, False)}</g>')
        p.append(f'<path class="dr" pathLength="1" d="M{x:.1f},88 H{x2:.1f} M{x:.1f},83 V93 M{x2:.1f},83 V93" '
                 f'stroke="{soft}" stroke-width=".9" style="animation-delay:{0.4 + i * 0.25:.2f}s"/>')
        p.append(f'<rect x="{mid - tw_txt / 2:.1f}" y="82" width="{tw_txt:.1f}" height="13" fill="{paper}"/>'
                 f'<text x="{mid:.1f}" y="91.5" font-size="10" fill="{soft}" text-anchor="middle">{_esc(label)}</text>')
    half = (SW - 44 - 16) / 2
    cat_p = {k: (f"h{i}", hatch_cols[i]) for i, k in enumerate(CATS)}
    cs = [(CATS[k][1], v, cat_p[k][0], cat_p[k][1]) for k, v in st["cats"].items() if v]  # type: ignore[union-attr]
    ps = []
    for i, (_h, (lab, _c)) in enumerate(PLATFORMS.items()):
        if lab in st["plats"]:  # type: ignore[operator]
            ps.append((lab, st["plats"][lab], f"h{i % 4}", hatch_cols[i % 4]))  # type: ignore[index]
    p.append(f'<text x="22" y="104" font-size="9.5" fill="{muted}" letter-spacing="1">BY CATEGORY</text>')
    _hatch_bar(p, 22, half, cs, 0.5)
    _hatch_legend(p, 22, cs, soft)
    x2 = 22 + half + 16
    p.append(f'<text x="{x2:.0f}" y="104" font-size="9.5" fill="{muted}" letter-spacing="1">LIVE DEMOS ON</text>')
    _hatch_bar(p, x2, half, ps, 0.7)
    _hatch_legend(p, x2, ps, soft)
    p.append("</g></svg>")
    return "".join(p)


STYLES = {"radar": build_radar, "splitflap": build_splitflap, "synthwave": build_synthwave, "blueprint": build_blueprint}


def build_svg(st: Dict[str, object], style: str) -> str:
    fn = STYLES.get(style)
    return fn(st) if fn else build_svg_classic(st, style)


# ----------------------------------------------------------------- main ---
def main() -> None:
    text = README.read_text(encoding="utf-8")
    if "<!-- PROJECTS:START -->" not in text:  # first run: wrap the existing hand-written table
        a = text.index(HEAD)
        lines = text[a:].split("\n")
        n = next(i for i, ln in enumerate(lines) if not ln.startswith("|"))
        old = "\n".join(lines[:n])
        text = text[:a] + f"<!-- PROJECTS:START -->\n{old}\n<!-- PROJECTS:END -->" + text[a + len(old):]
    pat = re.compile(r"(<!-- PROJECTS:START -->)(.*?)(<!-- PROJECTS:END -->)", re.S)
    m = pat.search(text)
    if not m:
        raise SystemExit("README is missing the <!-- PROJECTS:START/END --> markers")
    block = m.group(2)
    rows = parse_rows(block)
    if len(rows) < 5:
        raise SystemExit(f"parsed only {len(rows)} project rows - refusing to rewrite the README")
    ordered = global_order(rows, saved_order(block))
    st = stats(ordered)
    svg = build_svg(st, STYLE)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "projects_panel.svg").write_text(svg, encoding="utf-8")
    v = hashlib.md5(svg.encode()).hexdigest()[:8]
    img = (f'<p align="center"><img src="{ASSET_BASE}/projects_panel.svg?v={v}" width="{SW + 2 * PAD}" '
           f'alt="Project portfolio: projects, live demos, categories and platforms"/></p>')
    new = pat.sub(lambda mm: f"{mm.group(1)}\n{build_block(ordered, img)}\n{mm.group(3)}", text, count=1)
    print(f"[projects] style={STYLE} · {st['n']} projects · {st['live']} live · {len(st['plats'])} platforms · "  # type: ignore[arg-type]
          f"cats={st['cats']} · newest={st['newest']}")
    if new != text:
        README.write_text(new, encoding="utf-8", newline="\n")
        print("[projects] README updated")
    else:
        print("[projects] no change")


if __name__ == "__main__":
    main()
