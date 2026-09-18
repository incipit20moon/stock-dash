from __future__ import annotations

import html
import streamlit as st


NAV_ITEMS = [
    ("홈", "⌂"),
    ("시장 현황", "▥"),
    ("종목 분석", "◫"),
    ("공시 분석", "▤"),
    ("테마 & 섹터", "◇"),
    ("포트폴리오", "▣"),
    ("관심 종목", "☆"),
    ("AI 인사이트", "✦"),
    ("데이터 연결 관리", "⚙"),
]


def apply_theme():
    st.markdown(
        """
<style>
:root {
  --bg:#F4F7FB; --surface:#FFFFFF; --surface-soft:#F8FAFD;
  --line:#E5EAF1; --text:#111827; --muted:#6B7280;
  --navy:#0B1736; --navy-2:#111F45; --blue:#2563EB;
  --blue-soft:#EEF4FF; --green:#16A34A; --red:#DC2626;
}
html, body, [class*="css"] {
  font-family:Pretendard,"Noto Sans KR","Apple SD Gothic Neo",sans-serif;
}
.stApp { background:var(--bg); color:var(--text); }
.block-container { max-width:1440px; padding:1.5rem 2.2rem 4rem; }
header[data-testid="stHeader"] { background:rgba(244,247,251,.92); backdrop-filter:blur(14px); }
section[data-testid="stSidebar"] {
  background:linear-gradient(180deg,var(--navy) 0%,#0E1B3D 100%);
  border-right:0;
}
section[data-testid="stSidebar"] > div { padding:.9rem .8rem 1.2rem; }
[data-testid="stSidebar"] .stRadio > label { display:none; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap:5px; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
  color:#B9C5DE; border-radius:11px; padding:.65rem .75rem;
  transition:background .15s ease,color .15s ease;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
  background:rgba(255,255,255,.07); color:#FFFFFF;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
  background:rgba(37,99,235,.22); color:#FFFFFF; font-weight:750;
  box-shadow:inset 3px 0 var(--blue);
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#B9C5DE; }
h1,h2,h3,h4 { color:var(--text); letter-spacing:-.035em; }
h1 { font-weight:800; } h2,h3 { font-weight:760; }
p,li { line-height:1.62; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
[data-testid="stMetric"] {
  background:var(--surface); border:1px solid var(--line); border-radius:14px;
  padding:15px 17px; box-shadow:0 8px 26px rgba(15,23,42,.035);
}
[data-testid="stMetricLabel"] { color:var(--muted); }
[data-testid="stMetricValue"] { color:var(--text); font-weight:780; }
[data-testid="stVerticalBlockBorderWrapper"] {
  border-color:var(--line) !important; border-radius:15px !important;
  background:var(--surface); box-shadow:0 8px 26px rgba(15,23,42,.035);
}
.stButton > button,.stFormSubmitButton > button {
  border-radius:10px; min-height:2.65rem; font-weight:700;
}
.stButton > button[kind="primary"],.stFormSubmitButton > button[kind="primary"] {
  background:var(--blue); border-color:var(--blue);
}
.stTextInput input,.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div { border-radius:10px !important; }
.stTabs [data-baseweb="tab-list"] { gap:6px; overflow-x:auto; }
.stTabs [data-baseweb="tab"] { border-radius:9px; padding:9px 12px; white-space:nowrap; }
.stDataFrame { border:1px solid var(--line); border-radius:13px; overflow:hidden; }
.planx-brand { display:flex; align-items:center; gap:11px; margin:3px 6px 27px; }
.planx-brand-mark {
  width:38px;height:38px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;background:linear-gradient(145deg,#3B82F6,#1D4ED8);
  color:#fff;font-size:20px;font-weight:850;box-shadow:0 7px 18px rgba(37,99,235,.28);
}
.planx-brand-title { color:#fff; font-size:19px; line-height:1.1; font-weight:820; letter-spacing:-.035em; }
.planx-brand-sub { color:#7F91B7; font-size:10px; margin-top:4px; letter-spacing:.05em; }
.planx-hero {
  background:linear-gradient(135deg,#FFFFFF 0%,#F9FBFF 55%,#EEF4FF 100%);
  border:1px solid #E2E8F0; border-radius:20px; padding:25px 28px;
  margin-bottom:17px; box-shadow:0 12px 34px rgba(15,23,42,.045);
}
.planx-eyebrow { color:var(--blue); font-size:11px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; margin-bottom:7px; }
.planx-hero h1 { margin:0; font-size:32px; line-height:1.2; }
.planx-hero p { margin:8px 0 0; color:var(--muted); font-size:14px; max-width:760px; }
.planx-card {
  background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:18px 19px; min-height:116px;
  box-shadow:0 7px 22px rgba(15,23,42,.03);
}
.planx-card-title { font-size:12px; color:var(--muted); margin-bottom:8px; font-weight:700; }
.planx-card-value { font-size:23px; color:var(--text); font-weight:820; letter-spacing:-.035em; }
.planx-card-note { margin-top:7px; font-size:11px; color:#94A3B8; }
.planx-empty { background:#fff; border:1px dashed #CBD5E1; border-radius:14px; padding:21px; color:var(--muted); }
.planx-source {
  display:inline-flex; align-items:center; gap:5px; color:#64748B; background:#F8FAFC;
  border:1px solid #E2E8F0; padding:4px 8px; border-radius:999px; font-size:10px;
}
.planx-status-ok { color:#15803D; background:#F0FDF4; border-color:#BBF7D0; }
.planx-status-wait { color:#A16207; background:#FFFBEB; border-color:#FDE68A; }
.planx-status-bad { color:#B91C1C; background:#FEF2F2; border-color:#FECACA; }
hr { border-color:var(--line) !important; }
@media(max-width:900px) {
  .block-container { padding-left:1rem; padding-right:1rem; }
  .planx-hero { padding:21px 19px; } .planx-hero h1 { font-size:27px; }
}
@media(max-width:640px) {
  .block-container { padding-top:1.1rem; }
  .planx-card { min-height:100px; padding:14px; }
  .planx-card-value { font-size:22px; }
}
</style>
""",
        unsafe_allow_html=True,
    )


def brand():
    st.markdown(
        """
<div class="planx-brand">
  <div class="planx-brand-mark">↗</div><div><div class="planx-brand-title">StockDash</div><div class="planx-brand-sub">INVESTMENT DASHBOARD</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, eyebrow: str = "PLANX INVESTMENT OS"):
    st.markdown(
        f"""
<div class="planx-hero">
  <div class="planx-eyebrow">{html.escape(eyebrow)}</div>
  <h1>{html.escape(title)}</h1>
  <p>{html.escape(subtitle)}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def card(title: str, value: str, note: str = "", status: str = ""):
    status_html = f'<div class="planx-card-note">{html.escape(status)}</div>' if status else ""
    st.markdown(
        f"""
<div class="planx-card">
  <div class="planx-card-title">{html.escape(title)}</div>
  <div class="planx-card-value">{html.escape(value)}</div>
  <div class="planx-card-note">{html.escape(note)}</div>
  {status_html}
</div>
""",
        unsafe_allow_html=True,
    )


def empty_state(title: str, message: str):
    st.markdown(
        f"""
<div class="planx-empty">
  <strong style="color:#334155">{html.escape(title)}</strong><br>
  <span>{html.escape(message)}</span>
</div>
""",
        unsafe_allow_html=True,
    )


def source_badge(label: str, state: str = "wait"):
    cls = {"ok": "planx-status-ok", "bad": "planx-status-bad"}.get(state, "planx-status-wait")
    st.markdown(
        f'<span class="planx-source {cls}">{html.escape(label)}</span>',
        unsafe_allow_html=True,
    )
