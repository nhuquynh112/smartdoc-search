"""SmartDoc Pro V3 visual system: pure CSS, no external JavaScript/assets."""
from __future__ import annotations

import streamlit as st


def apply_theme(dark: bool) -> None:
    palette = (
        {"bg":"#080c17", "side":"#0c1425", "surface":"#121d32", "surface2":"#172741", "text":"#f1f5ff", "muted":"#a0b0ca", "subtle":"#7386a8", "border":"#293b58", "input":"#14233b", "glow":"rgba(63,91,235,.12)", "shadow":"0 18px 50px rgba(0,0,0,.20)", "contrast":"#101c30"}
        if dark else
        {"bg":"#f5f7fc", "side":"#ffffff", "surface":"#ffffff", "surface2":"#eef2fa", "text":"#17233d", "muted":"#5f718e", "subtle":"#8796b1", "border":"#dce3f1", "input":"#f7f9fd", "glow":"rgba(63,91,235,.065)", "shadow":"0 18px 48px rgba(37,61,108,.075)", "contrast":"#f3f6ff"}
    )
    variables = ";".join(f"--sd-{name}:{value}" for name, value in palette.items())
    st.markdown("<style>:root{" + variables + "}</style>", unsafe_allow_html=True)
    st.markdown("""
<style>
/* Layout & global colors */
.stApp, [data-testid="stAppViewContainer"] {background:var(--sd-bg);color:var(--sd-text);}
[data-testid="stAppViewContainer"]:before {content:"";position:fixed;inset:0;pointer-events:none;background:
 radial-gradient(ellipse at 84% 9%,var(--sd-glow),transparent 42%);}
[data-testid="stHeader"]{background:transparent !important;}
[data-testid="stSidebar"]{background:var(--sd-side) !important;border-right:1px solid var(--sd-border);}
[data-testid="stSidebar"] > div:first-child{padding-top:1.25rem;}
[data-testid="stAppViewBlockContainer"]{max-width:1450px;padding-top:1.0rem;padding-bottom:3rem;}
[data-testid="stDeployButton"]{display:none !important;}
#MainMenu{visibility:hidden;}
[data-testid="stWidgetLabel"] p,[data-testid="stCaptionContainer"] p{color:var(--sd-muted) !important;}
[data-testid="stMetricLabel"],[data-testid="stMetricValue"],h1,h2,h3,h4,p,span,label{color:inherit;}
[data-testid="stVerticalBlockBorderWrapper"] > div{border-color:var(--sd-border) !important;}
[data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="textarea"] > div {
 background:var(--sd-input) !important;border-color:var(--sd-border) !important;
 border-radius:14px !important;color:var(--sd-text) !important;min-height:45px;}
[data-baseweb="input"] input,[data-baseweb="textarea"] textarea,[data-baseweb="select"] input {color:var(--sd-text) !important;}
[data-testid="stFileUploader"] section{background:var(--sd-surface) !important;border:1px dashed #6c84c0 !important;border-radius:19px !important;}
[data-testid="stTabs"] button{color:var(--sd-muted) !important;}
[data-testid="stTabs"] button[aria-selected="true"]{color:#39c9f6 !important;}
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"]{
 background:linear-gradient(110deg,#574be9 0%,#3968fa 48%,#079ed0 100%) !important;
 color:#fff !important;border:0 !important;min-height:43px;border-radius:13px !important;font-weight:750;
 box-shadow:0 7px 22px rgba(70,81,239,.23);transition:transform .18s ease,box-shadow .18s ease,filter .18s ease;}
.stButton > button[kind="primary"] p,button[data-testid="stBaseButton-primary"] p{color:#fff !important;}
.stButton > button[kind="primary"]:hover{transform:translateY(-2px);filter:brightness(1.08);box-shadow:0 11px 27px rgba(70,81,239,.33);}
.stButton > button[kind="secondary"],button[data-testid="stBaseButton-secondary"]{
 background:var(--sd-surface) !important;color:var(--sd-text) !important;border:1px solid var(--sd-border) !important;
 border-radius:13px !important;min-height:42px;transition:transform .18s ease,border-color .18s ease;}
.stButton > button[kind="secondary"] p{color:var(--sd-text) !important;}
.stButton > button[kind="secondary"]:hover{transform:translateY(-1px);border-color:#5884df !important;}
hr{border-color:var(--sd-border) !important;}
/* Sidebar */
.sd-brand{display:flex;align-items:center;gap:12px;margin:8px 0 23px;}
.sd-logo{width:46px;height:46px;display:grid;place-items:center;border-radius:15px;color:white;font-size:23px;
 background:linear-gradient(130deg,#604cf2 2%,#0ba3d6 99%);box-shadow:0 10px 28px rgba(78,87,245,.30);}
.sd-brand-name{color:var(--sd-text);font-size:21px;letter-spacing:-.85px;font-weight:850;line-height:1.15;}
.sd-brand-name em{font-style:normal;color:#38c9fa;}
.sd-brand-desc{letter-spacing:1.6px;text-transform:uppercase;color:var(--sd-subtle);font-size:10px;font-weight:750;margin-top:4px;}
.sd-side-caption{margin:12px 0 7px;color:var(--sd-subtle);font-size:10px;letter-spacing:1.5px;font-weight:800;}
.sd-side-status{border:1px solid var(--sd-border);background:var(--sd-surface);padding:12px 13px;border-radius:14px;
 color:var(--sd-muted);font-size:11px;line-height:1.65;}
.sd-led{display:inline-block;vertical-align:middle;width:8px;height:8px;background:#31d69e;border-radius:50%;
 margin-right:7px;box-shadow:0 0 0 4px rgba(49,214,158,.1);animation:sd-led 2.5s ease-in-out infinite;}
[data-testid="stSidebar"] [data-testid="stButton"]{margin-bottom:-4px;}
/* Hero */
.sd-overline{font-size:10px;letter-spacing:2.25px;text-transform:uppercase;color:#65d6ff;font-weight:800;margin-bottom:10px;}
.sd-hero{position:relative;overflow:hidden;isolation:isolate;display:flex;align-items:center;min-height:288px;
 background:linear-gradient(115deg,#172052,#15377f 50%,#067a9a 115%);border:1px solid #4553c6;
 border-radius:27px;box-shadow:0 27px 75px rgba(26,55,155,.20);padding:34px 39px;margin:10px 0 20px;}
.sd-hero:before{content:"";position:absolute;z-index:-1;width:430px;height:430px;border-radius:50%;right:-125px;top:-120px;
 border:1px solid rgba(255,255,255,.16);box-shadow:0 0 0 55px rgba(255,255,255,.025),0 0 0 114px rgba(255,255,255,.025);
 animation:sd-float 9s ease-in-out infinite;}
.sd-hero:after{content:"";position:absolute;z-index:-1;width:190px;height:190px;border-radius:50%;right:135px;bottom:-108px;
 background:radial-gradient(circle,rgba(68,226,252,.45),rgba(68,226,252,0) 70%);filter:blur(14px);animation:sd-float 6s ease-in-out infinite reverse;}
.sd-hero-copy{max-width:730px;position:relative;z-index:1;}
.sd-pill{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(143,245,216,.35);
 color:#adffe2 !important;border-radius:99px;font-size:10px;font-weight:800;letter-spacing:.55px;
 padding:8px 12px;background:rgba(8,108,119,.26);}
.sd-hero h1{color:#fff !important;font-weight:850;font-size:clamp(33px,3.8vw,56px);line-height:1.12;
 letter-spacing:-2px;margin:15px 0 13px;}
.sd-hero h1 .accent{background:linear-gradient(90deg,#9bddff,#bca6ff,#8affdc);-webkit-background-clip:text;background-clip:text;color:transparent;}
.sd-hero p{font-size:13px;color:#cee0ff !important;line-height:1.72;max-width:550px;margin:0;}
.sd-orb{position:absolute;top:33px;right:51px;background:rgba(255,255,255,.085);backdrop-filter:blur(6px);
 color:#dff9ff !important;padding:10px 15px;border:1px solid rgba(255,255,255,.14);border-radius:14px;
 font-size:11px;letter-spacing:.4px;animation:sd-float 5s ease-in-out infinite;}
/* Heading & editorial */
.sd-topline{display:flex;align-items:center;justify-content:space-between;gap:16px;
 margin:9px 0 8px;color:var(--sd-muted);font-size:12px;}
.sd-kicker{color:#549dff;font-weight:850;letter-spacing:2.25px;font-size:10px;text-transform:uppercase;margin:13px 0 8px;}
.sd-title{font-size:clamp(30px,3vw,43px);font-weight:850;letter-spacing:-1.5px;line-height:1.2;color:var(--sd-text);}
.sd-subtitle{font-size:13px;color:var(--sd-muted);line-height:1.7;margin:8px 0 22px;}
.sd-section-title{font-size:18px;letter-spacing:-.4px;font-weight:840;color:var(--sd-text);margin:16px 0 11px;}
.sd-micro{color:var(--sd-subtle);font-size:11px;}
/* Data cards */
.sd-stat{position:relative;overflow:hidden;min-height:142px;padding:22px 22px 20px;background:var(--sd-surface);
 border:1px solid var(--sd-border);border-radius:20px;box-shadow:var(--sd-shadow);
 transition:transform .24s ease, border-color .24s ease, box-shadow .24s ease;}
.sd-stat:before{content:"";position:absolute;left:0;top:25px;bottom:25px;width:3px;background:var(--stat-color,#5d7dff);border-radius:0 4px 4px 0;}
.sd-stat:hover{transform:translateY(-5px);border-color:#5573d4;box-shadow:0 20px 52px rgba(38,64,137,.17);}
.sd-stat-top{display:flex;justify-content:space-between;align-items:center;gap:5px;}
.sd-stat-label{color:var(--sd-muted);font-size:12px;font-weight:750;}
.sd-stat-icon{width:38px;height:38px;border-radius:13px;background:var(--sd-surface2);display:grid;place-items:center;font-size:18px;}
.sd-stat-value{color:var(--sd-text);font-size:clamp(25px,2.3vw,33px);font-weight:850;letter-spacing:-1px;margin-top:14px;}
.sd-stat-note{font-size:11px;color:var(--sd-subtle);margin-top:5px;}
/* panels and search */
.sd-panel{border:1px solid var(--sd-border);border-radius:21px;background:var(--sd-surface);
 box-shadow:var(--sd-shadow);padding:20px 22px;margin:7px 0 13px;}
.sd-feature{border:1px solid var(--sd-border);border-radius:22px;background:var(--sd-surface);
 padding:19px 21px;margin:7px 0;min-height:142px;box-shadow:var(--sd-shadow);transition:transform .2s,border-color .2s;}
.sd-feature:hover{transform:translateY(-3px);border-color:#5d85da;}
.sd-feature-icon{font-size:25px;margin-bottom:10px;}
.sd-feature-title{font-weight:850;font-size:15px;color:var(--sd-text);margin:0 0 5px;}
.sd-feature-desc{color:var(--sd-muted);font-size:11px;line-height:1.55;}
.sd-progress{height:7px;background:var(--sd-surface2);border-radius:99px;overflow:hidden;margin:6px 0 13px;}
.sd-progress > span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#625af4,#18b4e7);animation:sd-expand .9s ease-out both;}
.sd-bar-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--sd-muted);font-size:12px;}
.sd-bar-meta strong{color:var(--sd-text);font-weight:800;}
.sd-empty{border:1px dashed var(--sd-border);background:var(--sd-surface);border-radius:22px;
 padding:40px 22px;text-align:center;color:var(--sd-muted);line-height:1.7;}
.sd-empty .emoji{font-size:35px;display:block;margin-bottom:8px;}
.sd-indicator{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:99px;
 border:1px solid var(--sd-border);background:var(--sd-surface2);font-size:11px;color:var(--sd-muted);font-weight:750;}
.sd-status{display:inline-flex;padding:6px 10px;border-radius:30px;background:rgba(16,185,129,.15);
 color:#38d9a2 !important;font-size:11px;font-weight:800;}
.sd-status-wait{background:rgba(240,178,66,.15);color:#f2b44e !important;}
.sd-hint{border-left:3px solid #2da3e5;border-radius:8px;padding:12px 14px;background:var(--sd-surface2);
 color:var(--sd-muted);font-size:12px;line-height:1.7;margin:12px 0;}
/* cards and snippets */
.sd-doc{border:1px solid var(--sd-border);background:var(--sd-surface);border-radius:18px;
 padding:16px 18px;box-shadow:var(--sd-shadow);transition:border-color .2s,transform .2s;margin:3px 0 8px;}
.sd-doc:hover{border-color:#5f8bf1;transform:translateY(-2px);}
.sd-doc-title{font-size:15px;font-weight:830;line-height:1.5;color:var(--sd-text);margin:9px 0 8px;}
.sd-doc-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:var(--sd-muted);font-size:11px;line-height:1.6;}
.sd-tag{padding:3px 9px;border:1px solid var(--sd-border);background:var(--sd-surface2);
 border-radius:99px;color:var(--sd-muted);font-size:10px;font-weight:770;}
.sd-grid-doc{min-height:130px;}
.sd-article{border:1px solid var(--sd-border);border-radius:17px;padding:19px 21px;max-height:450px;overflow:auto;
 background:var(--sd-surface);font-size:14px;line-height:1.86;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--sd-text);}
.sd-article mark{background:rgba(250,204,21,.35);color:inherit;border-radius:3px;padding:1px 2px;}
.sd-footer{text-align:center;font-size:11px;color:var(--sd-subtle);padding:25px 0 0;}
.sd-row-gap{height:9px;}
@keyframes sd-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
@keyframes sd-expand{from{width:0}to{}}
@keyframes sd-led{0%,100%{opacity:1}50%{opacity:.5}}
@media (max-width:900px){
 [data-testid="stAppViewBlockContainer"]{padding:1rem .8rem 2rem;}
 .sd-hero{padding:25px;min-height:254px;}
 .sd-hero h1{font-size:clamp(29px,6vw,44px);letter-spacing:-1.3px;}
 .sd-orb{display:none;}
 .sd-stat{min-height:120px;padding:16px;}
}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none !important;transition:none !important;}}
</style>
""", unsafe_allow_html=True)
