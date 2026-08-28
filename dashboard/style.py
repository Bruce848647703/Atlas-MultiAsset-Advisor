"""Jane Street-style theme: LIGHT, minimal, academic. White background,
near-black text, signature red accent, geometric sans-serif, uppercase
letter-spaced section labels, thin rules, hexagon motif. Injected via
``st.markdown(CSS, unsafe_allow_html=True)``."""

CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
:root {
  --js-bg:        #ffffff;
  --js-panel:     #ffffff;
  --js-panel-2:   #f5f5f7;
  --js-border:    #e4e5e9;
  --js-text:      #1a1a1a;
  --js-muted:     #6e7278;
  --js-red:       #d0001d;   /* Jane Street signature red */
  --js-red-dim:   #a30016;
  --js-green:     #16a34a;
  --js-down:      #d0001d;
  --js-mono: "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace;
  --js-sans: "Inter", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* ---------- base ---------- */
html, body, [class*="css"], .stMarkdown, .stText { font-family: var(--js-sans); }
.stApp { background: var(--js-bg); color: var(--js-text); }
.block-container { padding-top: 2.4rem; max-width: 1280px; }

p, li, span, label { color: var(--js-text); }
[data-testid="stCaption"], .stCaption, small { color: var(--js-muted); }

/* ---------- headers: Jane Street uppercase letter-spaced labels ---------- */
h1, h2, h3 { font-family: var(--js-sans); color: var(--js-text); letter-spacing: -0.015em; }
h1 { font-weight: 700; font-size: 2.05rem; }
h3 { font-weight: 600; }
.stSubheader {
  font-size: .82rem; font-weight: 600; letter-spacing: .13em; text-transform: uppercase;
  color: var(--js-text); padding-bottom: .45rem; margin-bottom: .9rem;
  border-bottom: 1px solid var(--js-border); position: relative;
}
/* red tick before each section label (JS signature) */
.stSubheader::before {
  content: ""; display: inline-block; width: 10px; height: 10px;
  background: var(--js-red); margin-right: .55rem; vertical-align: 0;
  clip-path: polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%); /* hexagon */
}

/* ---------- metric cards ---------- */
[data-testid="stMetric"] {
  background: var(--js-panel); border: 1px solid var(--js-border);
  border-radius: 6px; padding: 15px 18px; transition: border-color .15s ease;
}
[data-testid="stMetric"]:hover { border-color: var(--js-red); }
[data-testid="stMetricLabel"] {
  color: var(--js-muted); font-size: .72rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: .08em;
}
[data-testid="stMetricValue"] {
  font-family: var(--js-mono); font-size: 1.5rem; font-weight: 600;
  color: var(--js-text); font-variant-numeric: tabular-nums;
}
[data-testid="stMetricDelta"] { font-family: var(--js-mono); font-size: .82rem; }
[data-testid="stMetricDelta"] svg { display: none; }

/* ---------- tables ---------- */
[data-testid="stDataFrame"] { border: 1px solid var(--js-border); border-radius: 6px; overflow: hidden; }
.stDataFrame [data-testid="stTable"] td, .stDataFrame th {
  font-family: var(--js-mono); font-size: .82rem; font-variant-numeric: tabular-nums;
}
[data-testid="stTable"] th {
  color: var(--js-muted); font-weight: 600; text-transform: uppercase;
  font-size: .68rem; letter-spacing: .06em; font-family: var(--js-sans);
}

/* ---------- buttons ---------- */
.stButton > button, .stDownloadButton > button {
  background: var(--js-panel); color: var(--js-text);
  border: 1px solid var(--js-border); border-radius: 4px;
  font-weight: 500; font-size: .85rem; letter-spacing: .02em; transition: all .15s ease;
}
.stButton > button:hover { border-color: var(--js-red); color: var(--js-red); }
.stButton > button[kind="primary"], button[data-testid="baseButton-primary"] {
  background: var(--js-red); color: #fff; border-color: var(--js-red); font-weight: 600;
}
.stButton > button[kind="primary"]:hover { background: var(--js-red-dim); color: #fff; }

/* ---------- inputs ---------- */
.stTextInput input, .stNumberInput input, .stSelectbox select, .stTextArea textarea,
[data-baseweb="select"] > div, [data-baseweb="input"] {
  background: var(--js-panel); border: 1px solid var(--js-border);
  border-radius: 4px; color: var(--js-text);
}
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"]:focus-within {
  border-color: var(--js-red);
}
label, .stSlider label { color: var(--js-muted); font-size: .8rem; font-weight: 500; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: var(--js-panel-2); border-right: 1px solid var(--js-border); }
[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }

/* ---------- expander ---------- */
[data-testid="stExpander"] { background: var(--js-panel); border: 1px solid var(--js-border); border-radius: 6px; }
[data-testid="stExpander"] summary { color: var(--js-text); font-weight: 500; }
[data-testid="stExpander"] summary:hover { color: var(--js-red); }

/* ---------- divider ---------- */
hr { border: none; border-top: 1px solid var(--js-border); margin: 1.7rem 0; opacity: 1; }

/* ---------- alerts ---------- */
[data-testid="stAlert"] { border-radius: 6px; border: 1px solid var(--js-border); }

/* ---------- thin red top rule (JS signature) ---------- */
.stApp::before {
  content: ""; display: block; height: 3px; width: 100%;
  background: var(--js-red); position: fixed; top: 0; left: 0; z-index: 999;
}

/* scrollbars */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--js-bg); }
::-webkit-scrollbar-thumb { background: #d6d7db; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--js-red); }
</style>
"""
