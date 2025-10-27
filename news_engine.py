# news_engine.py (공식 RSS 기반 뉴스/테마/티커 매핑)
# -*- coding: utf-8 -*-

from __future__ import annotations
import feedparser
from datetime import datetime, timedelta
from dateutil import parser as dtp
from zoneinfo import ZoneInfo
import yaml
import re

KST = ZoneInfo("Asia/Seoul")

# --- 테마/키워드/티커 매핑 (예시) ---
THEME_MAP = {
    "지정학/전쟁": {
        "keywords": ["전쟁","휴전","군사충돌","격화","무력 충돌","제재","지정학",
                     "북한","중동","우크라이나","대만","남중국해","이스라엘","하마스","이란","러시아"],
        "tickers": ["012450","079550","428050","003490","010950","010955"]  # 방산/항공/정유 등
    },
    "반도체/AI": {
        "keywords": ["반도체","메모리","HBM","AI","칩","파운드리","GPU","엔비디아","클라우드"],
        "tickers": ["005930","000660","096770","034220"]
    },
    "2차전지/EV": {
        "keywords": ["2차전지","배터리","전고체","양극재","음극재","EV","전기차","테슬라"],
        "tickers": ["051910","003670","005380","066970"]
    },
    "정책/정부": {
        "keywords": ["정부","정책","규제","완화","지원책","세제","보조금","발표","입법","개정"],
        "tickers": ["030200","034730","017670","034020","055550"]
    },
    "금리/환율/매크로": {
        "keywords": ["금리","연준","기준금리","국채금리","환율","달러","원화","물가","CPI","PPI","고용"],
        "tickers": ["105560","005930","000660","005380"]
    },
    "원자재/에너지": {
        "keywords": ["유가","브렌트","WTI","원자재","구리","철광석","OPEC","감산","증산"],
        "tickers": ["010950","010955","003490","004020"]
    },
    "바이오/헬스케어": {
        "keywords": ["임상","허가","FDA","식약처","신약","의료기기","바이오"],
        "tickers": ["207940","068270","128940"]
    },
    "소비/리테일/관광": {
        "keywords": ["면세","관광","소비 심리","리테일","백화점","중국 관광","입국"],
        "tickers": ["008770","069960","004170"]
    },
    "통신/데이터센터": {
        "keywords": ["5G","요금제","망 투자","데이터센터","전력"],
        "tickers": ["030200","034730","017670"]
    },
    "조선/해운/물류": {
        "keywords": ["선박","조선","수주","운임","해운","물류","컨테이너"],
        "tickers": ["009540","010140","011200","011930","086280"]
    },
}

def load_sources(path: str="news_sources.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _in_kst_window(published: datetime, ref_day: datetime.date) -> bool:
    """KST 기준: 전일 15:30 ~ 당일 08:30 기사만 True"""
    start = datetime.combine(ref_day - timedelta(days=1), datetime.min.time(), tzinfo=KST).replace(hour=15, minute=30)
    end   = datetime.combine(ref_day, datetime.min.time(), tzinfo=KST).replace(hour=8, minute=30)
    return start <= published <= end

def _themes_in_title(title: str) -> list[str]:
    t = title.lower()
    hits = []
    for theme, cfg in THEME_MAP.items():
        for kw in cfg["keywords"]:
            if re.search(kw.lower(), t, flags=re.IGNORECASE):
                hits.append(theme)
                break
    return hits

def collect_news(ref_day: datetime.date, yml_path: str="news_sources.yaml") -> dict:
    """
    ref_day 기준 유효 기사만 수집하고, 기사별로 '영향 종목'을 매핑.
    return:
    {
      "highlights": [ { "source": "...", "title": "...", "link": "...",
                        "published": datetime, "themes": [...], "tickers": [...] }, ... ],
      "theme_score": { "반도체/AI": 3.0, ... }
    }
    """
    src = load_sources(yml_path)
    raw = []
    for group in ["domestic", "us_major", "gov_kr"]:
        for name, url in (src.get(group) or {}).items():
            try:
                d = feedparser.parse(url)
                for e in d.entries:
                    pub = None
                    for field in ["published", "pubDate", "updated"]:
                        if getattr(e, field, None):
                            pub = dtp.parse(getattr(e, field)).astimezone(KST)
                            break
                    if not pub or not _in_kst_window(pub, ref_day):
                        continue
                    title = e.title if hasattr(e, "title") else ""
                    link  = e.link  if hasattr(e, "link") else ""
                    if not title or not link:
                        continue
                    themes = _themes_in_title(title)
                    tset = set()
                    for th in themes:
                        for tk in THEME_MAP[th]["tickers"]:
                            tset.add(tk)
                    raw.append({
                        "source": name,
                        "title": title.strip(),
                        "link": link.strip(),
                        "published": pub,
                        "themes": themes,
                        "tickers": sorted(tset)
                    })
            except Exception:
                continue

    # 중복 제목 제거 + 최신순
    seen = set(); highlights = []
    for it in sorted(raw, key=lambda x: x["published"], reverse=True):
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        highlights.append(it)

    # 테마 스코어 집계
    theme_score = {}
    for it in highlights:
        for th in it["themes"]:
            theme_score[th] = theme_score.get(th, 0.0) + 1.0

    # 길이 관리
    highlights = highlights[:6]

    return {"highlights": highlights, "theme_score": theme_score}

def map_theme_to_tickers(theme_score: dict) -> dict[str, float]:
    """테마 스코어를 티커 가중치로 확장"""
    ticker_score = {}
    for theme, s in theme_score.items():
        cfg = THEME_MAP.get(theme)
        if not cfg:
            continue
        for tkr in cfg["tickers"]:
            ticker_score[tkr] = ticker_score.get(tkr, 0.0) + s
    return ticker_score

def format_news_header(news: dict) -> str:
    """모바일 최적화 헤더: 기사별 영향 종목도 같이 노출"""
    lines = []
    lines.append("🌅 아침 시황/뉴스 (전일 15:30 ~ 오늘 08:30)")
    for it in news["highlights"]:
        ts = it["published"].strftime("%H:%M")
        impacted = ", ".join(it["tickers"][:3]) if it["tickers"] else "—"
        lines.append(f"- [{ts}] {it['title']} ({it['source']}) → 영향: {impacted}")
    if news["theme_score"]:
        hot = sorted(news["theme_score"].items(), key=lambda x: x[1], reverse=True)[:3]
        if hot:
            lines.append("")
            lines.append("🔥 강한 테마: " + ", ".join([f"{k}" for k,_ in hot]))
    return "\n".join(lines)
