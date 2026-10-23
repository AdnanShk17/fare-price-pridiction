"""HTML/CSS building blocks for the FareCompass interface (no Streamlit import).

Everything that comes from outside the app (place names, addresses) is HTML-escaped
here, because these strings are rendered with unsafe_allow_html.
"""
from __future__ import annotations

import re
from html import escape
from typing import Iterable, List, Optional, Sequence

from branding import APP_NAME, APP_TAGLINE, CITY, COLORS


def esc(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def inr(amount) -> str:
    return f"₹{round(float(amount)):,}"


def _shorten(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
def css() -> str:
    """One-line <style> block. Comments and blank lines are stripped because a blank line can end an
    HTML block in Streamlit's markdown renderer and leak raw CSS onto the page."""
    root = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in COLORS.items())
    body = re.sub(r"/\*.*?\*/", "", _CSS, flags=re.S)
    body = re.sub(r"\s+", " ", body).strip()
    return ("<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');"
            ":root{" + root + "}" + body + "</style>")


_CSS = """
html, body, .stApp, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
.stApp { background: var(--bg); color: var(--ink); }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 0.6rem !important; padding-bottom: 1.5rem; max-width: 1320px; }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 18px; }

/* cards (st.container(border=True)) */
div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--card); border-radius: 16px; border-color: var(--line);
    box-shadow: 0 2px 10px rgba(15,23,42,0.05); }

/* buttons */
.stButton > button { border-radius: 10px; font-weight: 600; border: 1px solid var(--line); transition: all .15s ease; }
.stButton > button:hover { border-color: var(--navy); transform: translateY(-1px); }
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] { background: var(--amber); color: var(--navy);
    border: 0; font-weight: 700; }
.stButton > button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover { background: var(--amber-dark); color: var(--navy); }

/* navbar */
.fc-nav { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
    background: linear-gradient(135deg, var(--navy), var(--navy-2)); color: #fff; padding: 14px 22px; border-radius: 16px;
    margin-bottom: 14px; box-shadow: 0 6px 20px rgba(11,27,51,0.25); }
.fc-brand { display: flex; align-items: center; gap: 12px; }
.fc-logo { width: 42px; height: 42px; border-radius: 12px; background: var(--amber); display: flex; align-items: center;
    justify-content: center; font-size: 24px; }
.fc-brand-name { font-size: 22px; font-weight: 800; letter-spacing: -0.3px; line-height: 1.1; }
.fc-brand-name span { color: var(--amber); }
.fc-brand-tag { font-size: 12px; opacity: .75; margin-top: 2px; }
.fc-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.fc-chip { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18); padding: 6px 12px; border-radius: 999px;
    font-size: 13px; font-weight: 500; white-space: nowrap; }

/* section titles */
.fc-h { font-size: 18px; font-weight: 800; color: var(--ink); margin: 2px 0 2px 0; letter-spacing: -0.2px; }
.fc-sub { font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.fc-label { font-size: 11px; font-weight: 700; letter-spacing: .8px; color: var(--muted); text-transform: uppercase; margin: 10px 0 4px 0; }

/* step banner */
.fc-step { display: flex; align-items: center; gap: 10px; padding: 11px 14px; border-radius: 12px; font-size: 14px; font-weight: 600;
    background: #FFF7E0; border: 1px solid #FFE08A; color: #7A5600; margin: 6px 0 8px 0; }
.fc-step.ok { background: #E8F8EE; border-color: #A7E3BC; color: #146C36; }
.fc-step-n { background: var(--amber); color: var(--navy); border-radius: 999px; min-width: 24px; height: 24px; display: inline-flex;
    align-items: center; justify-content: center; font-size: 12px; font-weight: 800; }

/* location chips */
.fc-loc { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; background: #F8FAFC; border: 1px solid var(--line);
    border-radius: 10px; margin: 4px 0; }
.fc-dot { width: 10px; height: 10px; border-radius: 999px; margin-top: 5px; flex: 0 0 10px; }
.fc-loc-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; }
.fc-loc-text { font-size: 13px; color: var(--ink); line-height: 1.35; }

/* tiles */
.fc-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 6px 0 4px 0; }
.fc-tile { display: flex; gap: 12px; align-items: center; background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 14px; box-shadow: 0 1px 6px rgba(15,23,42,0.04); }
.fc-tile-icon { font-size: 26px; width: 44px; height: 44px; border-radius: 12px; background: #F1F5F9; display: flex; align-items: center;
    justify-content: center; flex: 0 0 44px; }
.fc-tile-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; }
.fc-tile-value { font-size: 18px; font-weight: 800; color: var(--ink); line-height: 1.2; }
.fc-tile-sub { font-size: 12px; color: var(--muted); }

/* ride options */
.fc-rides { display: grid; grid-template-columns: repeat(auto-fit, minmax(205px, 1fr)); gap: 14px; margin: 8px 0 6px 0; }
.fc-ride { background: var(--card); border: 1.5px solid var(--line); border-radius: 16px; padding: 16px; transition: all .15s ease;
    box-shadow: 0 2px 10px rgba(15,23,42,0.05); }
.fc-ride:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(15,23,42,0.10); }
.fc-ride.best { border-color: var(--green); box-shadow: 0 0 0 3px rgba(22,163,74,0.12); }
.fc-ride.est { background: linear-gradient(135deg, var(--navy), var(--navy-2)); border-color: var(--navy); color: #fff; }
.fc-ride.na { opacity: .55; }
.fc-ride-top { display: flex; align-items: center; gap: 10px; }
.fc-ride-icon { font-size: 26px; }
.fc-ride-name { font-size: 15px; font-weight: 700; line-height: 1.2; }
.fc-ride-sub { font-size: 12px; color: var(--muted); }
.fc-ride.est .fc-ride-sub { color: rgba(255,255,255,0.7); }
.fc-price { font-size: 32px; font-weight: 800; letter-spacing: -0.5px; margin: 12px 0 8px 0; }
.fc-ride.est .fc-price { color: var(--amber); }
.fc-badge { display: inline-block; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; background: #EEF2F7; color: #334155; }
.fc-ride.best .fc-badge { background: #DCFCE7; color: #166534; }
.fc-ride.est .fc-badge { background: rgba(255,255,255,0.15); color: #fff; }

.fc-save { display: flex; align-items: center; gap: 10px; background: #E8F8EE; border: 1px solid #A7E3BC; color: #146C36;
    padding: 12px 16px; border-radius: 12px; font-weight: 600; font-size: 14px; margin: 4px 0 10px 0; }

/* weather outlook */
.fc-outlook { display: flex; gap: 10px; overflow-x: auto; padding: 4px 0 8px 0; }
.fc-hour { min-width: 74px; text-align: center; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 6px; }
.fc-hour-t { font-size: 12px; font-weight: 700; color: var(--muted); }
.fc-hour-i { font-size: 24px; margin: 2px 0; }
.fc-hour-d { font-size: 15px; font-weight: 800; }
.fc-hour-r { font-size: 11px; color: #2563EB; font-weight: 600; }

/* places on the way */
.fc-poi { padding: 6px 0 2px 0; }
.fc-poi-name { font-size: 15px; font-weight: 700; color: var(--ink); }
.fc-poi-cuisine { font-size: 12px; font-weight: 600; color: #7C3AED; }
.fc-poi-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }

/* empty state */
.fc-how { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-top: 8px; }
.fc-how-card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; }
.fc-how-icon { font-size: 30px; margin-bottom: 8px; }
.fc-how-title { font-weight: 800; font-size: 16px; margin-bottom: 4px; }
.fc-how-text { color: var(--muted); font-size: 13px; line-height: 1.5; }

.fc-footer { text-align: center; color: var(--muted); font-size: 12px; padding: 22px 8px 6px 8px; line-height: 1.7; }
.fc-footer b { color: var(--ink); }

@media (max-width: 768px) {
  .fc-nav { padding: 12px 14px; } .fc-brand-name { font-size: 19px; } .fc-price { font-size: 28px; }
}
"""


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def navbar(chips: Sequence[str]) -> str:
    chip_html = "".join(f'<div class="fc-chip">{esc(c)}</div>' for c in chips if c)
    return (f'<div class="fc-nav"><div class="fc-brand"><div class="fc-logo">🚕</div><div>'
            f'<div class="fc-brand-name">{esc(APP_NAME[:4])}<span>{esc(APP_NAME[4:])}</span></div>'
            f'<div class="fc-brand-tag">{esc(APP_TAGLINE)}</div></div></div>'
            f'<div class="fc-chips">{chip_html}</div></div>')


def section_title(title: str, subtitle: str = "") -> str:
    sub = f'<div class="fc-sub">{esc(subtitle)}</div>' if subtitle else ""
    return f'<div class="fc-h">{esc(title)}</div>{sub}'


def label(text: str) -> str:
    return f'<div class="fc-label">{esc(text)}</div>'


def step_banner(text: str, number: Optional[str] = None, done: bool = False) -> str:
    badge = f'<span class="fc-step-n">{esc(number)}</span>' if number else '<span class="fc-step-n">✓</span>'
    return f'<div class="fc-step{" ok" if done else ""}">{badge}<span>{esc(text)}</span></div>'


def location_chip(color: str, title: str, text: str) -> str:
    return (f'<div class="fc-loc"><span class="fc-dot" style="background:{color}"></span><div>'
            f'<div class="fc-loc-label">{esc(title)}</div><div class="fc-loc-text">{esc(_shorten(text))}</div></div></div>')


def tile(icon: str, title: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="fc-tile-sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="fc-tile"><div class="fc-tile-icon">{esc(icon)}</div><div>'
            f'<div class="fc-tile-label">{esc(title)}</div><div class="fc-tile-value">{esc(value)}</div>{sub_html}</div></div>')


def tiles_row(tiles: Iterable[str]) -> str:
    return '<div class="fc-tiles">' + "".join(tiles) + "</div>"


def ride_card(icon: str, name: str, sub: str, price: Optional[float], badge: str = "",
              best: bool = False, estimate: bool = False) -> str:
    cls = "fc-ride" + (" best" if best else "") + (" est" if estimate else "") + (" na" if price is None else "")
    price_text = "Not available" if price is None else inr(price)
    price_style = ' style="font-size:20px;margin:20px 0 14px 0"' if price is None else ""
    badge_html = f'<span class="fc-badge">{esc(badge)}</span>' if badge else ""
    return (f'<div class="{cls}"><div class="fc-ride-top"><span class="fc-ride-icon">{esc(icon)}</span><div>'
            f'<div class="fc-ride-name">{esc(name)}</div><div class="fc-ride-sub">{esc(sub)}</div></div></div>'
            f'<div class="fc-price"{price_style}>{price_text}</div>{badge_html}</div>')


def rides_grid(cards: Iterable[str]) -> str:
    return '<div class="fc-rides">' + "".join(cards) + "</div>"


def savings_banner(cheapest_name: str, cheapest_price: float, saving: float) -> str:
    extra = f" — save up to {inr(saving)} compared with the priciest option" if saving >= 1 else ""
    return f'<div class="fc-save">💡 <span>Lowest fare: <b>{esc(cheapest_name)}</b> at <b>{inr(cheapest_price)}</b>{esc(extra)}</span></div>'


def outlook_strip(outlook: Sequence[dict]) -> str:
    if not outlook:
        return ""
    cells = []
    for h in outlook:
        temp = "–" if h.get("temperature_c") is None else f"{h['temperature_c']:.0f}°"
        rain = f'<div class="fc-hour-r">{h["precipitation_mm"]:g} mm</div>' if h.get("precipitation_mm") else '<div class="fc-hour-r">&nbsp;</div>'
        cells.append(f'<div class="fc-hour"><div class="fc-hour-t">{esc(h["label"])}</div>'
                     f'<div class="fc-hour-i">{esc(h["icon"])}</div><div class="fc-hour-d">{temp}</div>{rain}</div>')
    return '<div class="fc-outlook">' + "".join(cells) + "</div>"


def poi_row(name: str, cuisine: str, meta: str) -> str:
    cuisine_html = f' <span class="fc-poi-cuisine">· {esc(cuisine)}</span>' if cuisine else ""
    return (f'<div class="fc-poi"><div class="fc-poi-name">{esc(name)}{cuisine_html}</div>'
            f'<div class="fc-poi-meta">{esc(meta)}</div></div>')


def how_it_works() -> str:
    steps = [
        ("📍", "1. Set your route", "Tap the map to drop your pickup and drop-off pins, or search for a place by name."),
        ("💰", "2. Compare fares", "See estimated fares for auto, taxi, sedan and SUV across popular cab services side by side."),
        ("🍽️", "3. Enjoy the journey", "Get food, shopping and sightseeing suggestions along your route, timed to your trip."),
    ]
    cards = "".join(f'<div class="fc-how-card"><div class="fc-how-icon">{i}</div><div class="fc-how-title">{esc(t)}</div>'
                    f'<div class="fc-how-text">{esc(d)}</div></div>' for i, t, d in steps)
    return f'<div class="fc-how">{cards}</div>'


def footer() -> str:
    return (f'<div class="fc-footer"><b>{esc(APP_NAME)}</b> · {esc(CITY)}<br>'
            "Fares shown are estimates for comparison only and may differ from the price you are charged. "
            "Not affiliated with Ola, Uber or Rapido.<br>"
            "Map data © OpenStreetMap contributors · Weather by Open-Meteo</div>")
