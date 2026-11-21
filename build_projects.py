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

Style: PROJECTS_STYLE=chameleon (site palette, glowing contour) | phosphor (retro CRT terminal).
"""

from __future__ import annotations

import hashlib
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
STYLE = os.getenv("PROJECTS_STYLE", "chameleon")
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
    return {"n": len(ordered), "live": len(live), "plats": plats, "cats": cats,
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
               text_col: str, muted: str) -> None:
    p.append(f'<text x="{x:.0f}" y="104" font-size="9.5" fill="{muted}" letter-spacing="1">{title}</text>')
    _stack(p, x, 109, half, [(c, col) for _l, c, col in segs], delay)
    cx = x
    for label, c, col in segs:
        p.append(f'<circle cx="{cx + 4:.0f}" cy="135" r="3.5" fill="{col}"/>')
        text = f"{label} {c}"
        p.append(f'<text x="{cx + 12:.0f}" y="138" font-size="10" fill="{text_col}">{_esc(text)}</text>')
        cx += 24 + len(text) * 5.6


def build_svg(st: Dict[str, object], style: str) -> str:
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
