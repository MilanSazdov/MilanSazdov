#!/usr/bin/env python3
"""Build the terminal-themed GitHub profile: assets/*.svg + README.md.

    pip install fonttools brotli
    python3 scripts/build.py                     # writes assets/ and README.md
    python3 scripts/build.py --static --out DIR  # animations frozen on the last frame (previews)

Every piece of profile content lives in the CONTENT section below. Edit it there,
re-run, commit. README.md is generated too, so don't edit it by hand.

Each SVG ships light + dark variants (README swaps them with <picture>) and embeds a
subset of JetBrains Mono (OFL-1.1, see scripts/fonts/OFL.txt), so the text renders
identically on every OS. Animations are pure CSS and honour prefers-reduced-motion.
"""

import argparse
import base64
import datetime
import functools
import io
import math
import pathlib
import re
from html import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "scripts" / "fonts"

# ───────────────────────────────────────────────────────────────── CONTENT ──

GH_USER = "MilanSazdov"
USER, HOST = "milan", "novi-sad"
LINKEDIN = "https://www.linkedin.com/in/milansazdov"

FIGLET = [  # figlet -f "ANSI Shadow" "milan sazdov"
    "███╗   ███╗██╗██╗      █████╗ ███╗   ██╗    ███████╗ █████╗ ███████╗██████╗  ██████╗ ██╗   ██╗",
    "████╗ ████║██║██║     ██╔══██╗████╗  ██║    ██╔════╝██╔══██╗╚══███╔╝██╔══██╗██╔═══██╗██║   ██║",
    "██╔████╔██║██║██║     ███████║██╔██╗ ██║    ███████╗███████║  ███╔╝ ██║  ██║██║   ██║██║   ██║",
    "██║╚██╔╝██║██║██║     ██╔══██║██║╚██╗██║    ╚════██║██╔══██║ ███╔╝  ██║  ██║██║   ██║╚██╗ ██╔╝",
    "██║ ╚═╝ ██║██║███████╗██║  ██║██║ ╚████║    ███████║██║  ██║███████╗██████╔╝╚██████╔╝ ╚████╔╝ ",
    "╚═╝     ╚═╝╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝    ╚══════╝╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝   ╚═══╝  ",
]

WHOAMI = [("Milan Sazdov", "hl"), (" — ", "d"), ("Backend Software Engineer", "t"), (" @ ", "d"),
          ("Ominimo", "ac"), (" · ", "d"), ("Software Engineering", "t"), (" @ ", "d"), ("FTN Novi Sad", "ac")]
PHILOSOPHY = '"make it work, make it right, make it fast."'

NEOFETCH = [
    ("Role", "Backend Software Engineer @ Ominimo"),
    ("Education", "BSc Software Eng. & IT · FTN Novi Sad"),
    ("GPA", "10.00 / 10.00"),
    ("Location", "Novi Sad, Serbia"),
    ("Languages", "Python · C/C++ · Java · SQL · TypeScript"),
    ("Backend", "PHP/Laravel · Spring Boot · FastAPI · Django"),
    ("Frontend", "React · Angular · TypeScript · Tailwind"),
    ("ML", "PyTorch · TensorFlow · JAX · XGBoost · LightGBM"),
    ("Infra", "Docker · Kubernetes · AWS · Linux · CI/CD"),
    ("Web3", "Solidity · Foundry · zero-knowledge proofs"),
    ("Focus", "systems for ML · ML infra · optimization"),
    ("Speaks", "Serbian (native) · English (proficient)"),
]

SECTIONS = {  # key: (command, right-hand comment)
    "timeline": ("cat ~/timeline.log", "# 01 · timeline"),
    "projects": ("ls -la ~/projects", "# 02 · projects"),
    "achievements": ("cat ~/achievements.log", "# 03 · achievements"),
    "honors": ("cat ~/honors.txt", "# 04 · honors"),
    "activity": ("git log --graph --since=1.year", "# 05 · activity"),
}

CHIPS = [  # (file key, label, trailing glyph, href)
    ("linkedin", "linkedin", "↗", LINKEDIN),
    ("projects", "ls ~/projects", "↗", f"https://github.com/{GH_USER}?tab=repositories"),
]

RCOL = 97  # right edge (in columns) for right-aligned text inside panels, cards and section headers

# (dates, title, organisation, location, details, stack)
TIMELINE = [
    ("2026.04 → now", "Backend Software Engineer", "Ominimo", "Belgrade / Novi Sad",
     ["backend services for an automotive insurance-tech platform",
      "secure high-volume REST APIs: driver, vehicle & policy data",
      "pricing algorithms & validation rule engines in production",
      "schema design & SQL query optimization for low-latency reads"],
     "PHP · Laravel · SQL"),
    ("2023.10 → now", "BSc Software Engineering & IT", "FTN, University of Novi Sad", "Novi Sad",
     ["GPA 10.00 / 10.00",
      "DSA · OS · OOP · databases · networks · discrete math · stats"],
     None),
    ("2019.09 → 2023.06", 'Gymnasium "Jovan Jovanović Zmaj"', "specialized CS program", "Novi Sad",
     ["GPA 5.00 / 5.00 · Vuk Karadžić Diploma · CS & math diplomas"],
     None),
]

# (award, name, href, stack, description, highlight) — each becomes its own clickable card
PROJECTS = [
    ("1st place", "matf-suma", "https://github.com/LazarSazdov/MATF-SUMA", "Python · LightGBM · XGBoost",
     "1st in quals · 6th in finals — Ominimo × SUMA Data Science Hackathon",
     "reverse-engineers insurance pricing: LightGBM + XGBoost → Ridge stack"),
    ("2nd place", "auto-code-walker", "https://github.com/LazarSazdov/JB-plugin", "Java 21 · IntelliJ SDK",
     "JetBrains Hackathon — AI-guided code tours inside IntelliJ IDEA",
     "PSI symbol analysis · async OpenAI pipeline + LRU cache: ~75% faster"),
    (None, "nasp-key-value-engine", "https://github.com/MilanSazdov/NASP-key-value-engine", "C++17 · C",
     "LSM-tree NoSQL storage engine, built from scratch",
     "WAL → Memtable → SSTable · compaction · Bloom · HyperLogLog · Merkle"),
    (None, "shielder-zkml", "https://github.com/MarkoMile/zkml-dataset-proof", "Python · cryptography",
     "zero-knowledge provenance for ML datasets — verify data, never expose it",
     "Merkle-tree commitments · digital signatures · decoupled verification"),
    (None, "ride-hailing-platform", "https://github.com/kzi-nastava/mrs-team27-Lucky3",
     "Java · Angular · Android",
     "real-time ride-hailing: driver/passenger matching + live geo-tracking",
     "Spring Boot + JWT · Angular web · native Android · WebSockets"),
    (None, "graph-structure-visualizer", "https://github.com/vedranbajic4/graph-structure-visualizer",
     "Python · D3.js",
     "plugin-based graph platform: JSON / XML / RDF → live D3.js views",
     "entry-point plugin discovery · 12 design patterns · 14-command CLI"),
    (None, "night-twin", "https://github.com/MilanSazdov/Night-Twin", "FastAPI · React · OpenAI",
     "AI nightlife recommender that finds the night twin of your ideal night",
     "GPT intent parsing · embeddings + structured matching · guardrails"),
]
PROJECTS_HIDDEN = [
    (None, "search-engine-pdf", "https://github.com/MilanSazdov/search-engine-pdf", "Python · NetworkX",
     "PDF search engine: trie index, graph ranking, boolean & phrase queries",
     "autocomplete · pagination · top-10 export with highlights · caching"),
    (None, "checkers-ai", "https://github.com/MilanSazdov/checkers-ai", "Python · Pygame",
     "checkers AI: minimax + alpha-beta pruning, adaptive depth up to 5",
     "material / safety / mobility heuristics · transposition cache · <5 s"),
]

# (rank, event, organiser, optional sub-line); 1st/2nd get a filled / outlined pill
ACHIEVEMENTS = [
    ("1st", "DeFi Everywhere Hackathon 2025", "Ethereum NS", None),
    ("1st", "Proggy-Buggy Towel Contest 2025 · professional", "DataArt", None),
    ("1st", "Ominimo × SUMA Data Science Hackathon · quals", "MATF, Univ. of Belgrade", None),
    ("2nd", "JetBrains Hackathon · Auto Code Walker", "JetBrains", None),
    ("finals", 'Midnight Code Cup 2025 · World Finals, team "Lucky 3"', "Recraft × JetBrains",
     "500+ teams from 50+ countries · one of two Serbian teams in the finals"),
    ("4th", "Bubble Cup 17 · Premier League finals", "Microsoft Development Center Serbia", None),
    ("6th", "Ominimo × SUMA Data Science Hackathon · finals", "MATF, Univ. of Belgrade", None),
    ("onsite", "Reputeo & Yandex AI Hackathon 2025", "AI Nation, Belgrade", None),
]

HONORS = [
    ("Studenica Foundation Scholarship", "highly selective, merit-based"),
    ('"Evro za znanje" Scholarship', "extremely selective"),
    ("Vuk Karadžić Diploma", "highest national secondary-school honor"),
    ('"Zlatna stolica" · Golden Seat', "KK Partizan × EuroLeague, for academic excellence"),
    ("Petnica Science Center · Web3 Camp", "10-day intensive: Web3 dev, architecture & security"),
    ("Zero-Knowledge Proofs course", "Mathematical Academy"),
    ("Center for Young Talents, Novi Sad", "certificates of excellence: C, math, web"),
    ("Math & programming competitions", "municipal → national rounds, 2019–2023"),
]

SNAKE = {  # Platane/snk colours: (snake, five dot levels from empty to busiest)
    "dark": ("#58a6ff", "#161b22,#0c2d6b,#1158c7,#388bfd,#79c0ff"),
    "light": ("#0969da", "#ebedf0,#c8e1ff,#79b8ff,#2188ff,#0550ae"),
}

# ────────────────────────────────────────────────────────────────── THEMES ──

THEMES = {
    "dark": dict(
        bg="#0a0f1c", bar="#111a2c", border="#22314f", bar_text="#6f7f9e", shadow="#1f6feb", shadow_op=0.22,
        text="#c8d6ee", dim="#5d6d8e", user="#58a6ff", path="#38bdf8", arrow="#58a6ff", cmd="#e6edf3",
        cmdword="#7dd3fc", str="#79c0ff", hl="#e6f1ff", accent="#7dd3fc", cursor="#58a6ff",
        rule="#2a3a5c", key="#58a6ff",
        art=("#b6dcff", "#4493f8", "#1f4fd1"), art_shadow="#1d3766", shine="#ffffff", shine_op=0.55,
        donut=("#1f4a9a", "#3f86f0", "#a8d4ff"),
        chip_bg="#0d1626", chip_border="#1f4f9e", chip_text="#a9cfff",
        soft="#8ea2c4", pill="#1f6feb", pill_text="#ffffff",
    ),
    "light": dict(
        bg="#f8fafc", bar="#e9eef5", border="#d3dce8", bar_text="#7b8798", shadow="#0f2a5c", shadow_op=0.16,
        text="#1f2a3d", dim="#8592a8", user="#1d4ed8", path="#0369a1", arrow="#2563eb", cmd="#0f172a",
        cmdword="#0284c7", str="#1d4ed8", hl="#0b1b3a", accent="#1d4ed8", cursor="#2563eb",
        rule="#c9d4e4", key="#1d4ed8",
        art=("#60a5fa", "#2563eb", "#1e3a8a"), art_shadow="#bcd3f5", shine="#ffffff", shine_op=0.75,
        donut=("#93b9ee", "#3b7be8", "#0b3a9c"),
        chip_bg="#f1f6ff", chip_border="#9ec2f7", chip_text="#1d4ed8",
        soft="#56657d", pill="#2563eb", pill_text="#ffffff",
    ),
}
PALETTE = [  # neofetch colour strip
    ["#0b1d3a", "#10295a", "#163a80", "#1f4fa8", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd"],
    ["#082f49", "#0c4a6e", "#075985", "#0369a1", "#0284c7", "#0ea5e9", "#38bdf8", "#7dd3fc"],
]

# ─────────────────────────────────────────────────────────────── RENDERING ──

FS = 14            # terminal font size
CW = FS * 0.6      # JetBrains Mono advance = 600/1000 em
W = 900            # every wide SVG shares this width so columns line up down the page
M = 16             # outer margin around terminal windows (room for the shadow)
BAR = 34           # title-bar height
PADX = 26          # inner horizontal padding
X0 = M + PADX      # first text column inside a window
LH = 22            # line height
BOLD = {"u", "p", "a", "k", "hl", "b", "key", "chip"}
STATIC = False

_FONT_BYTES = {}


def f1(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def font_face(chars, weight):
    name = {400: "JetBrainsMonoNL-Regular.ttf", 700: "JetBrainsMonoNL-Bold.ttf"}[weight]
    if name not in _FONT_BYTES:
        _FONT_BYTES[name] = (FONT_DIR / name).read_bytes()
    font = TTFont(io.BytesIO(_FONT_BYTES[name]))
    opts = subset.Options()
    opts.layout_features = []
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # keep copyright + licence records
    try:
        import brotli  # noqa: F401
        opts.flavor, mime = "woff2", "font/woff2"
    except ImportError:
        opts.flavor, mime = "woff", "font/woff"
    sub = subset.Subsetter(opts)
    sub.populate(unicodes={ord(c) for c in chars} | {0x20})
    sub.subset(font)
    font.flavor = opts.flavor
    buf = io.BytesIO()
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return (f"@font-face{{font-family:JBM;font-weight:{weight};"
            f"src:url(data:{mime};base64,{data}) format('{opts.flavor}')}}")


class SVG:
    def __init__(self, w, h, theme, title, desc=""):
        self.w, self.h, self.theme = w, h, theme
        self.t = THEMES[theme]
        self.title, self.desc = title, desc
        self.body, self.defs, self.css = [], [], []
        self.regular, self.bold = set(), set()
        self.uid = 0

    def add(self, s):
        self.body.append(s)

    def next_id(self, prefix):
        self.uid += 1
        return f"{prefix}{self.uid}"

    def text(self, x, y, segs, cls=""):
        """Monospace segments [(text, classes)], each placed on its exact column."""
        out, col = [], 0
        for s, c in segs:
            (self.bold if BOLD & set(c.split()) else self.regular).update(s)
            body = s.strip(" ")
            if body:
                lead = len(s) - len(s.lstrip(" "))
                out.append(f'<tspan x="{f1(x + (col + lead) * CW)}" class="{c}">{escape(body, False)}</tspan>')
            col += len(s)
        attr = f' class="{cls}"' if cls else ""
        return f'<text y="{f1(y)}"{attr}>{"".join(out)}</text>'

    # animation helpers: every effect degrades to its final state in --static mode
    def appear(self, t):
        if STATIC:
            return ""
        c = self.next_id("ap")
        self.css.append(f".{c}{{opacity:0;animation:ap .01s linear {t:.2f}s forwards}}")
        return c

    def render(self):
        t = self.t
        css = [
            font_face(self.regular | {"x"}, 400),
            font_face(self.bold | {"x"}, 700) if self.bold else "",
            "text{font-family:JBM,'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,"
            f"'DejaVu Sans Mono',monospace;font-size:{FS}px;white-space:pre;fill:{t['text']}}}",
            f".t{{fill:{t['text']}}}.d{{fill:{t['dim']}}}.u{{fill:{t['user']}}}.p{{fill:{t['path']}}}"
            f".a{{fill:{t['arrow']}}}.c{{fill:{t['cmd']}}}.k{{fill:{t['cmdword']}}}.s{{fill:{t['str']}}}"
            f".hl{{fill:{t['hl']}}}.ac{{fill:{t['accent']}}}.key{{fill:{t['key']}}}.so{{fill:{t['soft']}}}"
            ".u,.p,.a,.k,.hl,.b,.key,.chip{font-weight:700}",
            f".tt{{fill:{t['bar_text']};font-size:12px}}",
            "@keyframes ap{to{opacity:1}}@keyframes hd{to{opacity:0}}"
            "@keyframes blink{50%{opacity:0}}",
            ".blink{animation:blink 1.06s steps(1,end) infinite}",
            *self.css,
            "@media (prefers-reduced-motion:reduce){*{animation-duration:0s!important;"
            "animation-delay:0s!important}.blink,.shine{animation:none!important}"
            ".shine{opacity:0}.frame{animation:none!important}.frame0{opacity:1!important}}",
        ]
        if STATIC:
            css.append(".blink{animation:none}")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{f1(self.h)}" '
            f'viewBox="0 0 {self.w} {f1(self.h)}" xml:space="preserve" role="img" aria-labelledby="ttl dsc">'
            f'<title id="ttl">{escape(self.title)}</title><desc id="dsc">{escape(self.desc)}</desc>'
            f'<style>{"".join(css)}</style><defs>{"".join(self.defs)}</defs>'
            + "".join(self.body) + "</svg>\n"
        )


def prompt_segs(cmd_segs=()):
    return [(USER, "u"), ("@", "d"), (HOST, "u"), (" ~ ", "p"), ("❯ ", "a"), *cmd_segs]


PROMPT_LEN = len(USER) + 1 + len(HOST) + 5


def window(svg, h, title):
    t, x, y, w, r = svg.t, M, M, svg.w - 2 * M, 10
    svg.defs.append(
        f'<filter id="shadow" x="-5%" y="-5%" width="110%" height="120%">'
        f'<feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="{t["shadow"]}" '
        f'flood-opacity="{t["shadow_op"]}"/></filter>')
    # the shadow gets its own layer: filters composite in linearRGB, which would shift the bg colour by a
    # hair and make the (unfiltered) typing covers visible as faint boxes
    svg.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{t["bg"]}" filter="url(#shadow)"/>')
    svg.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{t["bg"]}"/>')
    svg.add(f'<path d="M{x} {y + BAR}V{y + r}a{r} {r} 0 0 1 {r}-{r}H{x + w - r}a{r} {r} 0 0 1 {r} {r}'
            f'V{y + BAR}Z" fill="{t["bar"]}"/>')
    svg.add(f'<path d="M{x} {y + BAR - .5}H{x + w}" stroke="{t["border"]}"/>')
    svg.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="{r - .5}" fill="none" '
            f'stroke="{t["border"]}"/>')
    for i, (fill, edge) in enumerate([("#ff5f57", "#e0443e"), ("#febc2e", "#dea123"), ("#28c840", "#1aab29")]):
        svg.add(f'<circle cx="{x + 20 + i * 20}" cy="{y + BAR / 2}" r="6" fill="{fill}" stroke="{edge}" '
                f'stroke-width=".6"/>')
    svg.regular.update(title)
    svg.add(f'<text x="{x + w / 2}" y="{y + BAR / 2 + 4.2}" text-anchor="middle" class="tt">'
            f'{escape(title)}</text>')


def typed_line(svg, top, cmd_segs, t, dt=0.042, cursor=True):
    """Prompt appears at t, then the command is typed char by char. Returns the time Enter is hit."""
    base = top + 16
    n = sum(len(s) for s, _ in cmd_segs)
    start = t + 0.28
    end = start + n * dt
    g_cls = svg.appear(t)
    out = [f'<g class="{g_cls}">' if g_cls else "<g>", svg.text(X0, base, prompt_segs(cmd_segs))]
    if not STATIC:
        cx = X0 + PROMPT_LEN * CW
        tid, cid = svg.next_id("ty"), svg.next_id("cu")
        svg.css.append(f"@keyframes {tid}{{to{{transform:translateX({f1(n * CW)}px)}}}}"
                       f".{tid}{{animation:{tid} {n * dt:.2f}s steps({n},end) {start:.2f}s forwards}}"
                       f".{cid}{{animation:hd .01s linear {end + 0.12:.2f}s forwards}}")
        out.append(f'<g class="{tid}"><rect x="{f1(cx - .5)}" y="{top}" width="{f1((n + 2) * CW)}" height="{LH}" '
                   f'fill="{svg.t["bg"]}"/>')
        if cursor:
            out.append(f'<rect class="{cid}" x="{f1(cx)}" y="{top + 3}" width="{f1(CW)}" height="17" '
                       f'fill="{svg.t["cursor"]}"/>')
        out.append("</g>")
    out.append("</g>")
    svg.add("".join(out))
    return end + 0.15


def output_line(svg, top, segs, t, x=X0):
    c = svg.appear(t)
    svg.add(f'<g class="{c}">' + svg.text(x, top + 16, segs) + "</g>" if c else svg.text(x, top + 16, segs))


# ── ANSI Shadow → crisp geometry (no font fallback can break the banner) ──

def figlet_geometry(rows, x0, y0, cw, ch):
    """Return (block path per row, shadow path per row) for the ANSI Shadow art."""
    d, sw = cw * 0.2, cw * 0.13
    blocks, shadows = [], []
    for r, line in enumerate(rows):
        top, bp, sp = y0 + r * ch, [], []
        cy = top + ch / 2
        c = 0
        while c < len(line):
            if line[c] == "█":
                start = c
                while c < len(line) and line[c] == "█":
                    c += 1
                bp.append(f"M{f1(x0 + start * cw)} {f1(top)}h{f1((c - start) * cw)}v{f1(ch + .6)}"
                          f"h{f1(-(c - start) * cw)}z")
                continue
            ch_ = line[c]
            L, R = x0 + c * cw, x0 + (c + 1) * cw
            cx, T, B = (L + R) / 2, top, top + ch
            seg = {
                "═": [(L, cy - d, R, cy - d), (L, cy + d, R, cy + d)],
                "║": [(cx - d, T, cx - d, B), (cx + d, T, cx + d, B)],
            }.get(ch_)
            if seg:
                sp += [f"M{f1(a_)} {f1(b_)}L{f1(c_)} {f1(d_)}" for a_, b_, c_, d_ in seg]
            elif ch_ == "╗":
                sp += [f"M{f1(L)} {f1(cy - d)}H{f1(cx + d)}V{f1(B)}", f"M{f1(L)} {f1(cy + d)}H{f1(cx - d)}V{f1(B)}"]
            elif ch_ == "╔":
                sp += [f"M{f1(R)} {f1(cy - d)}H{f1(cx - d)}V{f1(B)}", f"M{f1(R)} {f1(cy + d)}H{f1(cx + d)}V{f1(B)}"]
            elif ch_ == "╝":
                sp += [f"M{f1(L)} {f1(cy + d)}H{f1(cx + d)}V{f1(T)}", f"M{f1(L)} {f1(cy - d)}H{f1(cx - d)}V{f1(T)}"]
            elif ch_ == "╚":
                sp += [f"M{f1(R)} {f1(cy + d)}H{f1(cx - d)}V{f1(T)}", f"M{f1(R)} {f1(cy - d)}H{f1(cx + d)}V{f1(T)}"]
            c += 1
        blocks.append("".join(bp))
        shadows.append("".join(sp))
    return blocks, shadows, sw


# ── the spinning donut (a1k0n's donut.c), pre-rendered frame by frame ──

DONUT_CHARS = ".,-~:;=!*#$@"


@functools.lru_cache(maxsize=None)
def donut_frames(cols, rows, aspect, n_frames, a0=1.0, b0=0.55):
    """Frames of the torus spinning about two axes; one full turn per loop, so it repeats seamlessly."""
    def torus(A, B):
        cA, sA, cB, sB = math.cos(A), math.sin(A), math.cos(B), math.sin(B)
        for i in range(90):
            ct, st = math.cos(i * 0.07), math.sin(i * 0.07)
            for j in range(315):
                cp, sp = math.cos(j * 0.02), math.sin(j * 0.02)
                ox, oy = 2 + ct, st
                ooz = 1 / (5 + cA * ox * sp + oy * sA)
                x = ox * (cB * cp + sA * sB * sp) - oy * cA * sB
                y = ox * (sB * cp - sA * cB * sp) + oy * cA * cB
                lum = cp * ct * sB - cA * ct * sp - sA * st + cB * (cA * st - ct * sA * sp)
                yield x * ooz, y * ooz * aspect, ooz, lum

    angles = [(a0 + 2 * math.pi * f / n_frames, b0 + 2 * math.pi * f / n_frames) for f in range(n_frames)]
    # pass 1: each frame's silhouette box, so the donut spins in place instead of wobbling
    boxes = []
    for A, B in angles:
        xs, ys = zip(*((px, py) for px, py, _, _ in torus(A, B)))
        boxes.append((min(xs), max(xs), min(ys), max(ys)))
    k1 = 0.94 * min(cols / max(x1 - x0 for x0, x1, _, _ in boxes), rows / max(y1 - y0 for _, _, y0, y1 in boxes))
    # pass 2: z-buffered plot; the unlit side still shows as '.', like the original donut.c
    frames = []
    for (A, B), (x0, x1, y0, y1) in zip(angles, boxes):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        grid = [[" "] * cols for _ in range(rows)]
        zbuf = [[0.0] * cols for _ in range(rows)]
        for px, py, ooz, lum in torus(A, B):
            xp, yp = int(cols / 2 + k1 * (px - cx)), int(rows / 2 - k1 * (py - cy))
            if 0 <= xp < cols and 0 <= yp < rows and ooz > zbuf[yp][xp]:
                zbuf[yp][xp] = ooz
                grid[yp][xp] = DONUT_CHARS[min(11, max(0, int(lum * 8)))]
        frames.append(["".join(r) for r in grid])
    return frames


def donut_svg_frame(frame, x0, y0, lh):
    out = []
    for r, line in enumerate(frame):
        runs, c = [], 0
        while c < len(line):
            if line[c] == " ":
                c += 1
                continue
            q = DONUT_CHARS.index(line[c]) // 4
            start = c
            while c < len(line) and (line[c] == " " or DONUT_CHARS.index(line[c]) // 4 == q):
                c += 1
            seg = line[start:c].rstrip()
            y = "" if runs else f' y="{f1(y0 + r * lh)}"'  # later runs stay on the same baseline
            runs.append(f'<tspan x="{f1(x0 + start * CW)}"{y} class="q{q}">{escape(seg, False)}</tspan>')
        out.append("".join(runs))
    return "".join(out)


# ───────────────────────────────────────────────────────────────── ASSETS ──

def build_hero(theme, now):
    art_top_pad, AH = 6, 16
    rows_h = LH * 2 + art_top_pad + AH * len(FIGLET) + 12 + LH * 5
    h = M + BAR + 18 + rows_h + 20 + M
    svg = SVG(W, h, theme, f"{USER}@{HOST} — terminal",
              "Animated terminal: figlet banner 'MILAN SAZDOV', whoami, and echo $PHILOSOPHY.")
    t = svg.t
    window(svg, h - 2 * M, f"{USER} — -zsh — {len(FIGLET[0])}×{len(FIGLET) + 8}")
    top = M + BAR + 18

    svg.add(svg.text(X0, top + 16, [(f"Last login: {now:%a %b %e %H:%M:%S} on ttys001", "d")]))
    top += LH
    enter = typed_line(svg, top, [("figlet", "k"), (" -f ", "c"), ('"ANSI Shadow"', "s"), (" milan sazdov", "c")],
                       t=0.45)
    top += LH + art_top_pad

    # banner
    art_w = len(FIGLET[0]) * CW
    blocks, shadows, sw = figlet_geometry(FIGLET, X0, top, CW, AH)
    g0, g1, g2 = t["art"]
    svg.defs.append(
        f'<linearGradient id="artg" gradientUnits="userSpaceOnUse" x1="{X0}" y1="{top}" x2="{f1(X0 + art_w)}" '
        f'y2="{top + AH * 6}"><stop offset="0" stop-color="{g0}"/><stop offset=".5" stop-color="{g1}"/>'
        f'<stop offset="1" stop-color="{g2}"/></linearGradient>'
        f'<linearGradient id="shineg" x1="0" y1="0" x2="1" y2="0" gradientTransform="rotate(12 .5 .5)">'
        f'<stop offset="0" stop-color="{t["shine"]}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{t["shine"]}" stop-opacity="{t["shine_op"]}"/>'
        f'<stop offset="1" stop-color="{t["shine"]}" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="artclip"><path d="{"".join(blocks)}"/></clipPath>')
    for i, (bp, sp) in enumerate(zip(blocks, shadows)):
        c = svg.appear(enter + 0.06 + i * 0.055)
        svg.add(f'<g{" class=" + chr(34) + c + chr(34) if c else ""}>'
                f'<path d="{sp}" fill="none" stroke="{t["art_shadow"]}" stroke-width="{f1(sw)}"/>'
                f'<path d="{bp}" fill="url(#artg)"/></g>')
    art_done = enter + 0.06 + len(FIGLET) * 0.055
    if not STATIC:
        band, dist = 140, art_w + 2 * 140
        svg.css.append(f"@keyframes shine{{0%{{transform:translateX(0)}}24%,100%{{transform:translateX({f1(dist)}px)}}}}"
                       f".shine{{animation:shine 7s cubic-bezier(.45,0,.25,1) {art_done + 0.5:.2f}s infinite}}")
        svg.add(f'<g clip-path="url(#artclip)"><rect class="shine" x="{f1(X0 - band)}" y="{top - 4}" '
                f'width="{band}" height="{AH * 6 + 8}" fill="url(#shineg)"/></g>')
    top += AH * len(FIGLET) + 12

    enter = typed_line(svg, top, [("whoami", "k")], t=art_done + 0.25, dt=0.06)
    top += LH
    output_line(svg, top, WHOAMI, enter + 0.05)
    top += LH
    enter = typed_line(svg, top, [("echo", "k"), (" ", "c"), ("$PHILOSOPHY", "ac")], t=enter + 0.35, dt=0.045)
    top += LH
    output_line(svg, top, [(PHILOSOPHY, "s b")], enter + 0.05)
    top += LH
    c = svg.appear(enter + 0.3)
    svg.add((f'<g class="{c}">' if c else "<g>") + svg.text(X0, top + 16, prompt_segs()) +
            f'<rect class="blink" x="{f1(X0 + PROMPT_LEN * CW)}" y="{top + 3}" width="{f1(CW)}" height="17" '
            f'fill="{t["cursor"]}"/></g>')
    return svg


def build_neofetch(theme):
    lh, n_rows, dcols = 19, 2 + len(NEOFETCH) + 3, 36
    h = M + BAR + 18 + LH + 8 + n_rows * lh + 22 + M
    svg = SVG(W, h, theme, f"{USER}@{HOST} — neofetch",
              "neofetch: a spinning ASCII donut next to role, education, GPA, languages and tooling.")
    t = svg.t
    window(svg, h - 2 * M, f"{USER} — neofetch — {len(FIGLET[0])}×{n_rows + 2}")
    top = M + BAR + 18
    svg.add(svg.text(X0, top + 16, prompt_segs([("neofetch", "k")])))
    top += LH + 8

    # donut
    q0, q1, q2 = t["donut"]
    svg.css.append(f".q0{{fill:{q0}}}.q1{{fill:{q1}}}.q2{{fill:{q2}}}")
    frames = donut_frames(dcols, n_rows, CW / lh, 1 if STATIC else 60)
    svg.regular.update(DONUT_CHARS)
    period = 0.1 * len(frames)
    if not STATIC:
        svg.css.append(f".frame{{opacity:0;animation:fr {period:.1f}s steps(1,end) infinite}}"
                       f"@keyframes fr{{0%{{opacity:1}}{100 / len(frames) - .001:.3f}%,100%{{opacity:0}}}}")  # never 2 at once
    for i, fr in enumerate(frames):
        cls = "frame0" if STATIC else f"frame frame{i}"
        style = f' style="animation-delay:{i * 0.1:.1f}s"' if not STATIC else ""
        svg.add(f'<text class="{cls}"{style}>{donut_svg_frame(fr, X0, top + 14, lh)}</text>')

    # info column
    ix = X0 + (dcols + 4) * CW
    svg.add(svg.text(ix, top + 14, [(USER, "u"), ("@", "d"), (HOST, "u")]))
    svg.add(svg.text(ix, top + 14 + lh, [("─" * (len(USER) + 1 + len(HOST)), "d")]))
    room = len(FIGLET[0]) - dcols - 4
    for i, (k, v) in enumerate(NEOFETCH):
        assert len(k) + 2 + len(v) <= room, f"neofetch line too long: {k}: {v}"
        svg.add(svg.text(ix, top + 14 + (i + 2) * lh, [(k, "key"), (": ", "d"), (v, "t")]))
    py = top + (len(NEOFETCH) + 3) * lh
    for r, row in enumerate(PALETTE):
        for c, col in enumerate(row):
            svg.add(f'<rect x="{f1(ix + c * 3 * CW)}" y="{f1(py + r * (lh - 2) + 2)}" width="{f1(3 * CW)}" '
                    f'height="{lh - 4}" fill="{col}"/>')
    return svg


def col_x(col):
    return X0 + col * CW


def right(svg, y, segs, end=RCOL):
    """Segments set so the last character ends exactly on column `end`."""
    return svg.text(col_x(end - sum(len(t) for t, _ in segs)), y, segs)


def dots(left_cols, right_len):
    return [(" " + "·" * (RCOL - left_cols - right_len - 2) + " ", "d")]


def panel(svg, y, h):
    """Output panel: same surface, border and shadow as the terminal windows, minus the title bar."""
    t, x, w, r = svg.t, M, svg.w - 2 * M, 10
    svg.defs.append(
        f'<filter id="shadow" x="-5%" y="-10%" width="110%" height="130%">'
        f'<feDropShadow dx="0" dy="4" stdDeviation="4.5" flood-color="{t["shadow"]}" '
        f'flood-opacity="{t["shadow_op"] * .8:.2f}"/></filter>')
    svg.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{t["bg"]}" filter="url(#shadow)"/>')
    svg.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{t["bg"]}"/>')
    svg.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="{r - .5}" fill="none" '
            f'stroke="{t["border"]}"/>')


def pill(svg, x, base, label, kind, width=None):
    """Small badge: 'fill' (1st), 'line' (2nd) or 'muted' (everything else)."""
    t, fs = svg.t, 11.5
    w = width or len(label) * fs * 0.6 + 14
    fill, stroke, color = {"fill": (t["pill"], t["pill"], t["pill_text"]),
                           "line": ("none", t["accent"], t["accent"]),
                           "muted": ("none", t["border"], t["soft"])}[kind]
    svg.bold.update(label)
    svg.add(f'<rect x="{f1(x + .5)}" y="{f1(base - 13.5)}" width="{f1(w - 1)}" height="18" rx="9" fill="{fill}" '
            f'stroke="{stroke}"/><text x="{f1(x + w / 2)}" y="{f1(base - .5)}" text-anchor="middle" '
            f'style="font-size:{fs}px;font-weight:700;fill:{color}">{escape(label)}</text>')
    return w


def section_header(svg, key, y=0):
    cmd, comment = SECTIONS[key]
    word, _, rest = cmd.partition(" ")
    # zsh-syntax-highlighting style: command word, quoted strings and plain args get their own colours
    segs = [(word, "k")] + [(part, "s" if part.startswith('"') else "c")
                            for part in re.split(r'("[^"]*")', " " + rest) if part]
    svg.add(f'<path d="M{M} {y + 10.5}H{W - M}" stroke="{svg.t["rule"]}" stroke-dasharray="1 5" '
            f'stroke-linecap="round" stroke-width="1.5"/>')
    assert PROMPT_LEN + len(cmd) + 2 + len(comment) <= RCOL, f"header too long: {cmd}"
    svg.add(svg.text(X0, y + 38, prompt_segs(segs)))
    svg.add(right(svg, y + 38, [(comment, "d")]))


BLOCK_ALT = {
    "timeline": "Timeline: Backend Software Engineer at Ominimo (2026–now); BSc Software Engineering & IT at "
                "FTN, University of Novi Sad, GPA 10.00 (2023–now); Gymnasium Jovan Jovanović Zmaj, GPA 5.00.",
    "achievements": "Achievements: 1st DeFi Everywhere Hackathon 2025, 1st Proggy-Buggy Towel Contest 2025, "
                    "1st Ominimo × SUMA quals, 2nd JetBrains Hackathon, Midnight Code Cup 2025 World Finals, "
                    "4th Bubble Cup 17, 6th Ominimo × SUMA finals.",
    "honors": "Honors: Studenica Foundation Scholarship, Evro za znanje Scholarship, Vuk Karadžić Diploma, "
              "Zlatna stolica, Petnica Web3 Camp, Zero-Knowledge Proofs course.",
}
HEAD_H = 50   # section header height
GAP = 6       # header → panel


def build_section(theme, key):
    svg = SVG(W, HEAD_H, theme, f"$ {SECTIONS[key][0]}", f"Section header: {SECTIONS[key][1].lstrip('# ')}")
    section_header(svg, key)
    return svg


def build_block(theme, key, rows, desc):
    """Section header + output panel in one image. `rows` = [(draw(svg, baseline) | None, height)]."""
    body = sum(hh for _, hh in rows)
    py = HEAD_H + GAP
    h = py + 18 + body + 14 + 12
    svg = SVG(W, h, theme, f"$ {SECTIONS[key][0]}", desc)
    section_header(svg, key)
    panel(svg, py, h - py - 12)
    top = py + 18
    for draw, hh in rows:
        if draw:
            draw(svg, top + 16)
        top += hh
    return svg


def build_timeline(theme):
    rows = []
    for i, (dates, title, org, place, details, stack) in enumerate(TIMELINE):
        if i:
            rows.append((None, 12))
        rows.append((lambda svg, y, d=dates, ti=title, o=org, pl=place: (
            svg.add(svg.text(X0, y, [(d, "p"), (" " * (19 - len(d)), "d"), (ti, "hl"), (" · ", "d"), (o, "ac")])),
            svg.add(right(svg, y, [(pl, "so")]))), 22))
        for j, line in enumerate(details):
            branch = "└─ " if j == len(details) - 1 else "├─ "
            rows.append((lambda svg, y, br=branch, ln=line: svg.add(
                svg.text(col_x(19), y, [(br, "d"), (ln, "t")])), 22))
        if stack:
            rows.append((lambda svg, y, st=stack: svg.add(svg.text(col_x(22), y, [(st, "k")])), 22))
    return build_block(theme, "timeline", rows, BLOCK_ALT["timeline"])


def build_achievements(theme):
    pw = 7 * CW
    rows = []
    for rank, event, org, sub in ACHIEVEMENTS:
        kind = {"1st": "fill", "2nd": "line"}.get(rank, "muted")

        def draw(svg, y, rk=rank, kd=kind, ev=event, og=org):
            pill(svg, X0, y, rk, kd, width=pw)
            svg.add(svg.text(col_x(9), y, [(ev, "hl" if kd == "fill" else "t"),
                                           *dots(9 + len(ev), len(og))]))
            svg.add(right(svg, y, [(og, "so")]))
        rows.append((draw, 25))
        if sub:
            rows.append((lambda svg, y, sb=sub: svg.add(svg.text(col_x(9), y - 2, [("└─ ", "d"), (sb, "so")])), 23))
    return build_block(theme, "achievements", rows, BLOCK_ALT["achievements"])


def build_honors(theme):
    rows = [(lambda svg, y, nm=name, nt=note: (
        svg.add(svg.text(X0, y, [("◆ ", "a"), (nm, "t"), *dots(2 + len(nm), len(nt))])),
        svg.add(right(svg, y, [(nt, "so")]))), 23) for name, note in HONORS]
    return build_block(theme, "honors", rows, BLOCK_ALT["honors"])


def build_card(theme, project):
    award, name, _, stack, desc, hi = project
    h = 92
    svg = SVG(W, h, theme, name, f"{name}: {desc}")
    t = svg.t
    svg.add(f'<rect x="{M + .5}" y="1.5" width="{W - 2 * M - 1}" height="{h - 3}" rx="10" fill="{t["bg"]}" '
            f'stroke="{t["border"]}"/>')
    svg.add(svg.text(X0, 32, [("~/projects/", "d"), (name, "u"), (" ↗", "d")]))
    if award:
        pill(svg, col_x(11 + len(name) + 3), 32, award, "fill" if award.startswith("1") else "line")
    svg.add(right(svg, 32, [(stack, "k")]))
    svg.add(svg.text(X0, 54, [(desc, "t")]))
    svg.add(svg.text(X0, 75, [("└─ ", "d"), (hi, "so")]))
    for line in (desc, "└─ " + hi):
        assert len(line) <= RCOL, f"card line too long: {line}"
    return svg


def build_footer(theme):
    lines = [
        ("logout", "d"), ("Saving session...", "d"), ("...copying shared history...", "d"),
        ("...saving history...truncating history files...", "d"), ("...completed.", "d"), ("", "d"),
        ("[Process completed]", "t"),
    ]
    lh = 21
    h = 22 + lh * (len(lines) + 1) + 18
    svg = SVG(W, h, theme, "$ exit", "Session footer: exit, logout, [Process completed].")
    svg.add(f'<path d="M{M} 10.5H{W - M}" stroke="{svg.t["rule"]}" stroke-dasharray="1 5" stroke-linecap="round" '
            f'stroke-width="1.5"/>')
    svg.add(svg.text(X0, 38, prompt_segs([("exit", "k")])))
    svg.add(right(svg, 38, [("# thanks for stopping by", "d")]))
    for i, (s, c) in enumerate(lines):
        svg.add(svg.text(X0, 38 + (i + 1) * lh, [(s, c)]))
    return svg


def build_chip(theme, label, glyph):
    fs, cw = 13, 13 * 0.6
    text = f"❯ {label} {glyph}"
    w, h = round(len(text) * cw + 30), 34
    svg = SVG(w, h, theme, label)
    t = svg.t
    svg.bold.update(text)
    svg.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="8" fill="{t["chip_bg"]}" '
            f'stroke="{t["chip_border"]}"/>')
    svg.add(f'<text y="22" style="font-size:{fs}px" class="chip">'
            f'<tspan x="15" class="a">❯</tspan>'
            f'<tspan x="{f1(15 + 2 * cw)}" fill="{t["chip_text"]}">{escape(label)}</tspan>'
            f'<tspan x="{f1(15 + (3 + len(label)) * cw)}" class="d">{glyph}</tspan></text>')
    return svg


# ───────────────────────────────────────────────────────────────── README ──

def attr(s):
    return escape(s, quote=False).replace('"', "&quot;")


def picture(key, alt, width="100%", dark=None, light=None):
    """Theme-aware image for things that are NOT links: GitHub swaps the source with the viewer's theme."""
    dark, light = dark or f"assets/{key}-dark.svg", light or f"assets/{key}-light.svg"
    size = f' width="{width}"' if width else ""
    return (f'<picture>\n'
            f'  <source media="(prefers-color-scheme: dark)" srcset="{dark}">\n'
            f'  <source media="(prefers-color-scheme: light)" srcset="{light}">\n'
            f'  <img alt="{attr(alt)}" src="{dark}"{size}>\n'
            f'</picture>')


def linked(key, alt, href, width=None):
    """Theme-aware image that IS a link. GitHub breaks <a><picture>, so emit one plain <a><img> per theme;
    github.com hides any README link whose href ends in #gh-dark-mode-only / #gh-light-mode-only to match."""
    size = f' width="{width}"' if width else ""
    return "".join(f'<a href="{attr(href)}#gh-{th}-mode-only"><img alt="{attr(alt)}" '
                   f'src="assets/{key}-{th}.svg"{size}></a>' for th in THEMES)


def cards(items):
    return "\n".join(linked(f"card-{name}", f"{name} — {desc}", href, width="100%")
                     for _, name, href, _, desc, _ in items)


def build_readme():
    snake = f"https://raw.githubusercontent.com/{GH_USER}/{GH_USER}/output/snake"
    chips = "\n".join(linked("chip-" + key, label, href) for key, label, _, href in CHIPS)
    hero_alt = (f"{USER}@{HOST}: figlet 'MILAN SAZDOV' — Backend Software Engineer @ Ominimo · "
                f"Software Engineering @ FTN Novi Sad")
    neofetch_alt = ("neofetch — Backend Software Engineer @ Ominimo · BSc Software Eng. & IT, FTN Novi Sad · "
                    "GPA 10.00/10.00 · Python, C/C++, Java, SQL, TypeScript")
    block = {k: picture(k, alt) for k, alt in BLOCK_ALT.items()}
    header = {k: picture("section-" + k, "$ " + SECTIONS[k][0]) for k in ("projects", "activity")}
    snake_pic = picture("", "contribution graph being eaten by a blue snake",
                        dark=snake + "-dark.svg", light=snake + "-light.svg")
    views = (f"https://komarev.com/ghpvc/?username={GH_USER}&amp;label=visitors&amp;color=1f6feb"
             f"&amp;style=flat-square")

    return f"""<!-- Generated by scripts/build.py — edit the content there and re-run. -->

<div align="center">

{picture("hero", hero_alt)}

{chips}

</div>

{picture("neofetch", neofetch_alt)}

{block["timeline"]}

{header["projects"]}
{cards(PROJECTS)}

<details>
<summary><code>ls -la ~/projects/.archive</code> &nbsp;·&nbsp; {len(PROJECTS_HIDDEN)} earlier projects</summary>
<br>

{cards(PROJECTS_HIDDEN)}

</details>

{block["achievements"]}

{block["honors"]}

{header["activity"]}
{snake_pic}

{picture("footer", "$ exit — logout — [Process completed]")}

<p align="center">
  <img alt="profile views" src="{views}">
</p>
"""


# ─────────────────────────────────────────────────────────────────── MAIN ──

def main():
    global STATIC
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--static", action="store_true", help="freeze animations on their final frame")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT, help="output root (default: repo root)")
    args = ap.parse_args()
    STATIC = args.static
    assets = args.out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()

    jobs = {"hero": lambda th: build_hero(th, now), "neofetch": build_neofetch, "footer": build_footer,
            "timeline": build_timeline, "achievements": build_achievements, "honors": build_honors}
    jobs.update({f"section-{k}": (lambda th, k=k: build_section(th, k)) for k in ("projects", "activity")})
    jobs.update({f"card-{p[1]}": (lambda th, p=p: build_card(th, p)) for p in PROJECTS + PROJECTS_HIDDEN})
    jobs.update({f"chip-{k}": (lambda th, l=l, g=g: build_chip(th, l, g)) for k, l, g, _ in CHIPS})
    for stale in assets.glob("*.svg"):  # drop assets from removed sections / projects
        stale.unlink()
    for name, fn in jobs.items():
        for theme in THEMES:
            path = assets / f"{name}-{theme}.svg"
            path.write_text(fn(theme).render(), encoding="utf-8")
            print(f"  {path.relative_to(args.out)}  {path.stat().st_size / 1024:6.1f} KB")
    (args.out / "README.md").write_text(build_readme(), encoding="utf-8")
    print("  README.md")


if __name__ == "__main__":
    main()
