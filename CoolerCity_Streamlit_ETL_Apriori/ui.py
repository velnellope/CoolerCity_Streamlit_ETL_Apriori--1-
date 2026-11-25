"""Komponen tampilan bersama: tema, kartu KPI, header halaman, kotak insight, gaya grafik."""
import html

import plotly.graph_objects as go
import streamlit as st

INK = "#0B2D4F"
MUTED = "#5F7189"
TEAL = "#0098C8"  # biru Cooler City
MINT = "#7CCDEB"
SKY = "#00568E"  # navy pinguin
BERRY = "#E0679C"  # pink Icecream·Tea
AMBER = "#F5B800"  # kuning cone
VIOLET = "#7C6CF2"
PALETTE = [TEAL, SKY, BERRY, AMBER, MINT, "#F7A8C8", VIOLET, "#4FB3DA", "#94A3B8", "#FFD95A", "#2E7FB8", "#64748B"]
CHANNEL_COLORS = {"Offline (Outlet)": TEAL, "GoFood": "#15803D", "GrabFood": "#A3D93B", "ShopeeFood": "#F97316"}
STATUS = {
    "ok": ("Tercapai", "#169B57", "#E5F6EC"),
    "near": ("Hampir tercapai", "#C27C0E", "#FDF3E1"),
    "miss": ("Belum tercapai", "#D9365E", "#FDE8EE"),
    "none": ("Target belum diatur", "#5F7189", "#EEF1F5"),
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea, select {font-family:'Nunito', 'Segoe UI', Arial, sans-serif !important;}
.stApp {background: radial-gradient(900px 420px at 92% -8%, #FCE4EF 0%, rgba(252,228,239,0) 60%), radial-gradient(1100px 520px at 10% -12%, #DDF2FB 0%, rgba(221,242,251,0) 60%), #F5FAFD; color:#0B2D4F;}
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1440px;}
header[data-testid="stHeader"] {background: transparent;}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid #E8EDF3;}
[data-testid="stSidebarNav"] a {border-radius:12px; padding:.45rem .7rem; margin:.1rem 0;}
[data-testid="stSidebarNav"] a[aria-current="page"] {background:#E2F3FA;}
[data-testid="stSidebarNav"] a[aria-current="page"] span {color:#00568E !important; font-weight:700;}
[data-testid="stSidebarNavSeparator"] {margin:.6rem 0;}
h1, h2, h3 {color:#0B2D4F !important; letter-spacing:-.02em;}
h1 {font-weight:800 !important;}
[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #E8EDF3; border-radius:18px; padding:16px 18px; box-shadow:0 1px 2px rgba(20,33,61,.04), 0 8px 24px rgba(20,33,61,.04);}
[data-testid="stMetricLabel"] p {color:#5F7189 !important; font-weight:600;}
[data-testid="stMetricValue"] {color:#0B2D4F !important; font-weight:800;}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {border-radius:18px;}
div[data-testid="stExpander"] details {border-radius:14px; border:1px solid #E8EDF3; background:#FFFFFF;}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {border-radius:12px; font-weight:700;}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {background:#0098C8; border-color:#0098C8;}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {background:#00568E; border-color:#00568E;}
[data-testid="stDataFrame"] {border-radius:14px; overflow:hidden;}
.stTabs [data-baseweb="tab-list"] {gap:18px;}
.stTabs [data-baseweb="tab"] p {font-weight:700; font-size:.95rem;}

.cc-eyebrow {font-size:.74rem; letter-spacing:.16em; color:#E0679C; font-weight:800; text-transform:uppercase; margin-bottom:2px;}
.cc-title {font-size:2rem; font-weight:900; color:#0B2D4F; letter-spacing:-.03em; line-height:1.15; margin:0;}
.cc-sub {color:#5F7189; margin:6px 0 18px 0; font-size:.98rem;}
.cc-section {font-size:1.08rem; font-weight:800; color:#0B2D4F; margin:22px 0 4px 0;}
.cc-section-sub {color:#5F7189; font-size:.88rem; margin-bottom:10px;}

.kpi {background:#FFFFFF; border:1px solid #E8EDF3; border-radius:20px; padding:18px 18px 16px; height:100%; min-height:262px; margin-bottom:14px;
      box-shadow:0 1px 2px rgba(20,33,61,.04), 0 10px 28px rgba(20,33,61,.05); display:flex; flex-direction:column; gap:8px;}
.kpi-top {display:flex; justify-content:space-between; align-items:center; gap:8px;}
.kpi-name {display:flex; align-items:center; gap:10px; font-weight:700; color:#0B2D4F; font-size:.92rem; line-height:1.25;}
.kpi-icon {width:34px; height:34px; border-radius:11px; display:grid; place-items:center; font-size:1.05rem;}
.kpi-pill {font-size:.72rem; font-weight:800; padding:4px 10px; border-radius:999px; white-space:nowrap;}
.kpi-value {font-size:1.75rem; font-weight:800; color:#0B2D4F; letter-spacing:-.02em; line-height:1.1;}
.kpi-note {font-size:.8rem; color:#5F7189; min-height:1.1em;}
.kpi-bar {height:8px; background:#EEF1F5; border-radius:999px; overflow:hidden;}
.kpi-bar > div {height:100%; border-radius:999px;}
.kpi-foot {display:flex; justify-content:space-between; font-size:.8rem; color:#5F7189;}
.kpi-foot b {color:#0B2D4F;}
.kpi-def {font-size:.76rem; color:#8A97AA; border-top:1px dashed #E8EDF3; padding-top:8px; margin-top:2px;}

.summary {display:flex; gap:12px; flex-wrap:wrap; align-items:center; background:linear-gradient(120deg,#00568E 0%,#0098C8 100%); color:#FFFFFF; border-radius:20px; padding:18px 22px; margin:6px 0 16px;}
.summary .big {font-size:1.6rem; font-weight:800;}
.summary .chip {background:rgba(255,255,255,.1); border-radius:999px; padding:6px 12px; font-size:.85rem; font-weight:600;}

.insight {background:#FFFFFF; border:1px solid #E8EDF3; border-left:5px solid #0098C8; border-radius:16px; padding:14px 18px; margin:8px 0 4px;}
.insight-title {font-weight:800; font-size:.9rem; color:#00568E; margin-bottom:6px;}
.insight ul {margin:0; padding-left:1.1rem;} .insight li {margin:3px 0; color:#334155; font-size:.92rem;}
.howto {background:#F1F5F9; border-radius:14px; padding:12px 16px; font-size:.86rem; color:#475569; margin:6px 0 10px;}
.rule-card {background:#FFFFFF; border:1px solid #E8EDF3; border-radius:18px; padding:16px 18px; height:100%;
            box-shadow:0 8px 24px rgba(20,33,61,.04);}
.rule-items {font-weight:800; color:#0B2D4F; font-size:1.02rem; margin:6px 0;}
.rule-meta {font-size:.85rem; color:#5F7189;}
.tag {display:inline-block; font-size:.72rem; font-weight:800; padding:3px 9px; border-radius:999px;}
.auth-hero {background:linear-gradient(150deg,#FFFFFF 0%,#E6F5FC 55%,#FCE4EF 120%); border:1px solid #DCEEF7; color:#0B2D4F; border-radius:28px; padding:30px 32px; min-height:470px; box-shadow:0 14px 40px rgba(0,86,142,.08);}
.auth-hero h2 {color:#00568E !important; font-size:1.9rem; font-weight:900; margin:14px 0 8px;}
.auth-hero p, .auth-hero li {color:#40546D; font-size:.95rem;}
.auth-hero ul {padding-left:1.1rem;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def money(v, short=False):
    v = float(v)
    if short:
        for div, suf in ((1e9, " M"), (1e6, " jt"), (1e3, " rb")):
            if abs(v) >= div:
                return f"Rp{v / div:,.1f}{suf}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "Rp" + f"{v:,.0f}".replace(",", ".")


def num(v, dec=0):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v, dec=1):
    return num(v * 100, dec) + "%"


def page_header(eyebrow, title, subtitle):
    st.markdown(f'<div class="cc-eyebrow">{html.escape(eyebrow)}</div><div class="cc-title">{html.escape(title)}</div>'
                f'<div class="cc-sub">{subtitle}</div>', unsafe_allow_html=True)


def section(title, subtitle=""):
    st.markdown(f'<div class="cc-section">{html.escape(title)}</div>'
                + (f'<div class="cc-section-sub">{subtitle}</div>' if subtitle else ""), unsafe_allow_html=True)


def insight(points, title="Yang perlu diketahui"):
    items = "".join(f"<li>{p}</li>" for p in points if p)
    st.markdown(f'<div class="insight"><div class="insight-title">💡 {html.escape(title)}</div><ul>{items}</ul></div>',
                unsafe_allow_html=True)


def howto(text):
    st.markdown(f'<div class="howto">📖 <b>Cara membaca:</b> {text}</div>', unsafe_allow_html=True)


def kpi_card(name, icon, icon_bg, value_text, status, achievement=None, target_text=None, note="", definition=""):
    label, color, bg = STATUS[status]
    bar = ""
    if achievement is not None:
        width = max(3, min(achievement, 1.0) * 100)
        bar = f'<div class="kpi-bar"><div style="width:{width:.0f}%;background:{color}"></div></div>'
    foot = ""
    if target_text:
        ach = f"{pct(achievement, 0)} dari target" if achievement is not None else ""
        foot = f'<div class="kpi-foot"><span>Target: <b>{html.escape(target_text)}</b></span><span>{ach}</span></div>'
    return (f'<div class="kpi"><div class="kpi-top"><div class="kpi-name"><div class="kpi-icon" style="background:{icon_bg}">{icon}</div>'
            f'{html.escape(name)}</div><span class="kpi-pill" style="color:{color};background:{bg}">{label}</span></div>'
            f'<div class="kpi-value">{html.escape(value_text)}</div><div class="kpi-note">{note}</div>{bar}{foot}'
            f'<div class="kpi-def">{html.escape(definition)}</div></div>')


def card_grid(cards, cols=3):
    for i in range(0, len(cards), cols):
        row = st.columns(cols)
        for c, card in zip(row, cards[i:i + cols]):
            c.markdown(card, unsafe_allow_html=True)


def style_fig(fig, height=360, title=None, legend=True):
    fig.update_layout(separators=",.", height=height, margin=dict(l=6, r=8, t=56 if title else 18, b=8), paper_bgcolor="#FFFFFF",
                      plot_bgcolor="#FFFFFF", font=dict(family="Nunito, Segoe UI, Arial", color=MUTED, size=12),
                      title=dict(text=f"<b>{title}</b>" if title else None, font=dict(size=15, color=INK), x=0.01, y=0.97),
                      legend=dict(orientation="h", y=1.02 if not title else 1.1, x=0, title=None, bgcolor="rgba(0,0,0,0)"),
                      showlegend=legend, hoverlabel=dict(bgcolor="#FFFFFF", font_color=INK, bordercolor="#E8EDF3"))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#E8EDF3", title_font=dict(size=12))
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False, title_font=dict(size=12))
    return fig


def show(fig, height=360, title=None, legend=True):
    with st.container(border=True):
        st.plotly_chart(style_fig(fig, height, title, legend), width="stretch", config={"displaylogo": False})


def all_or(selected, options):
    """Pilihan kosong pada filter berarti 'semua'."""
    return list(selected) if selected else list(options)


def empty_fig():
    return go.Figure()
