# news_engine.py (공식 RSS 기반 뉴스/테마/티커 매핑 확장 + 한글 변환 + 근거 생성)
# -*- coding: utf-8 -*-

from __future__ import annotations
import feedparser
from datetime import datetime, timedelta
from dateutil import parser as dtp
from zoneinfo import ZoneInfo
import yaml
import re

KST = ZoneInfo("Asia/Seoul")

# --- 테마/키워드/티커 매핑 ---
#  - direct: 뉴스에 직접적으로 1차 영향이 갈 가능성이 높은 종목
#  - related: 공급망/수혜/파생 테마로 2차 영향 가능성이 있는 종목(가점은 절반)
THEME_MAP = {
    "지정학/전쟁": {
        "keywords": ["전쟁","휴전","군사충돌","격화","무력 충돌","제재","지정학","북한","중동","우크라이나","대만","남중국해","이스라엘","하마스","이란","러시아","미사일","방위비","국방"],
        "direct":  ["012450","079550","064350","042660","003490","010950","096770"],  # 한화에어로,LIG넥스원,현대로템,한화오션,대한항공,S-Oil,SK이노베이션
        "related": ["004020","005490","009540","010140","011200","011930"]           # 현대제철,포스코홀딩스,한국조선해양,삼성중공업,HMM,삼성전자(부품 공급망 파급 고려)
    },
    "반도체/AI": {
        "keywords": ["반도체","메모리","HBM","AI","칩","파운드리","GPU","엔비디아","클라우드","서버","디램","낸드","공급 부족","증설","제조 장비"],
        "direct":  ["005930","000660","108320","000990","009150","034220"],           # 삼성전자,SK하이닉스,LX세미콘,DB하이텍,삼성전기,LG디스플레이
        "related": ["012450","066570","093370","036570","015760"]                     # 한화에어로(장비/정밀),LG전자,SK하이닉스 우군? (보수적),NC/카카오? -> 파급업종 예시/전력
    },
    "2차전지/EV": {
        "keywords": ["2차전지","배터리","전고체","양극재","음극재","EV","전기차","충전소","리콜","테슬라","주행거리"],
        "direct":  ["051910","006400","005380","000270","011170"],                    # LG화학,삼성SDI,현대차,기아,롯데케미칼
        "related": ["012330","010950","096770","034730"]                              # 현대모비스,S-Oil,SK이노베이션(정유/소재),SK
    },
    "원자재/에너지": {
        "keywords": ["유가","브렌트","WTI","OPEC","감산","증산","정유","원자재","구리","철광석","천연가스","우라늄","전력요금"],
        "direct":  ["010950","096770","078930","004020","005490"],                    # S-Oil,SK이노베이션,GS,현대제철,포스코홀딩스
        "related": ["003490","011200","010140","009540","015760"]                     # 대한항공,HMM,삼성중공업,한국조선해양,한전
    },
    "금리/환율/매크로": {
        "keywords": ["금리","연준","기준금리","국채금리","환율","달러","원화","물가","CPI","PPI","고용","경기침체","연착륙","성장률","무역수지"],
        "direct":  ["105560","055550","086790","316140","028260"],                    # KB금융,신한지주,하나금융,우리금융,삼성물산(환율 민감 대형 수출 지주)
        "related": ["005930","000660","005380","051910","006400","035420","035720"]   # 수출주/플랫폼 등 전반
    },
    "정책/정부": {
        "keywords": ["정부","정책","규제","완화","지원책","세제","보조금","입법","개정","발표","공공","인프라","디지털","데이터센터"],
        "direct":  ["030200","017670","034730","035420","035720"],                    # KT,SK텔,SK,NAVER,카카오
        "related": ["005930","000660","051910","034220","069960","008770"]            # 인프라/통신/소비 파생
    },
    "바이오/헬스케어": {
        "keywords": ["임상","허가","FDA","식약처","신약","백신","실패","성공","의료기기","제네릭","바이오"],
        "direct":  ["068270","207940","128940"],                                      # 셀트리온,삼성바이오로직스,한미약품
        "related": ["011070","006280","003490"]                                       # LG이노텍?, 현대약품?, 대한항공(화물) - 예시
    },
    "소비/리테일/관광": {
        "keywords": ["면세","관광","소비 심리","리테일","백화점","중국 관광","입국","출국","유커","마케팅","페스티벌"],
        "direct":  ["008770","004170","023530","069960"],                              # 호텔신라,신세계,롯데쇼핑,롯데지주
        "related": ["003490","000080","004990"]                                        # 대한항공,하이트진로,롯데지주2? (보수적 예시)
    },
    "조선/해운/물류": {
        "keywords": ["선박","조선","수주","운임","해운","물류","컨테이너","친환경 선박","LNG"],
        "direct":  ["009540","010140","042660","011200"],                              # 한국조선해양,삼성중공업,한화오션,HMM
        "related": ["010950","096770","005490","004020"]                               # 정유/철강 소재 수요
    },
    "통신/데이터센터": {
        "keywords": ["5G","요금제","망 투자","데이터센터","전력","클라우드","IDC","AI 서버"],
        "direct":  ["030200","017670","032640"],                                       # KT,SK텔레콤,LG유플러스
        "related": ["005930","000660","034730","015760"]                               # 서버/전력 수요 파생
    },
    "플랫폼/인터넷": {
        "keywords": ["플랫폼","검색","콘텐츠","게임","광고","커머스","트래픽","규제","과징금"],
        "direct":  ["035420","035720","251270"],                                       # NAVER,카카오,넷마블(예시)
        "related": ["034730","030200","017670"]                                        # 인프라/데이터센터/통신
    },
    "자동차/부품": {
        "keywords": ["전기차","SUV","출시","리콜","생산차질","수출","판매호조","자율주행","로보택시"],
        "direct":  ["005380","000270","012330"],                                       # 현대차,기아,현대모비스
        "related": ["051910","006400","011170","010950","096770"]                      # 배터리/소재/정유
    },
}

# --- 간단 한글 변환(영어 핵심 용어 치환) ---
_EN2KO = {
    "fed": "연준", "federal reserve": "연준", "rate": "금리", "rates": "금리", "hike": "인상", "cut": "인하",
    "inflation": "물가", "cpi": "소비자물가", "ppi": "생산자물가", "jobs": "고용", "payrolls": "비농업고용",
    "recession": "경기침체", "soft landing": "연착륙", "oil": "유가", "brent": "브렌트유", "wti": "WTI",
    "chip": "칩", "chips": "칩", "semiconductor": "반도체", "ai": "AI", "gpu": "GPU",
    "ceasefire": "휴전", "sanction": "제재", "sanctions": "제재", "geopolitics": "지정학",
    "earnings": "실적", "guidance": "가이던스", "outlook": "전망",
    "bond": "채권", "yields": "금리", "yield": "금리", "dollar": "달러", "currency": "환율",
    "china": "중국", "taiwan": "대만", "ukraine": "우크라이나", "israel": "이스라엘", "gaza": "가자지구",
}

def _to_korean_headline(title: str) -> str:
    t = title
    low = t.lower()
    for en, ko in _EN2KO.items():
        if en in low:
            t = t.replace(en, ko).replace(en.title(), ko).replace(en.upper(), ko)
    return (t[:120] + "…") if len(t) > 120 else t

def _short_time(dt) -> str:
    return dt.strftime("%H:%M")

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
    ref_day 기준 유효 기사만 수집하고, 기사별로 '영향 종목'(direct+related)을 매핑.
    return:
    {
      "highlights": [ { "source": "...", "title": "...", "link": "...",
                        "published": datetime, "themes": [...], "tickers_direct": [...], "tickers_related": [...], "tickers": [...] }, ... ],
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
                    tset_d = set(); tset_r = set()
                    for th in themes:
                        cfg = THEME_MAP.get(th, {})
                        for tk in cfg.get("direct", []):
                            tset_d.add(tk)
                        for tk in cfg.get("related", []):
                            tset_r.add(tk)
                    # 통합 표시용
                    t_all = sorted(list(tset_d | tset_r))
                    raw.append({
                        "source": name,
                        "title": title.strip(),
                        "link": link.strip(),
                        "published": pub,
                        "themes": themes,
                        "tickers_direct": sorted(list(tset_d)),
                        "tickers_related": sorted(list(tset_r)),
                        "tickers": t_all
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

    # 테마 스코어 집계 (기사 수 기반, 단순합)
    theme_score = {}
    for it in highlights:
        for th in it["themes"]:
            theme_score[th] = theme_score.get(th, 0.0) + 1.0

    # 길이 관리
    highlights = highlights[:8]

    return {"highlights": highlights, "theme_score": theme_score}

def map_theme_to_tickers(theme_score: dict) -> dict[str, float]:
    """테마 스코어를 티커 가중치로 확장 (direct 1.0, related 0.5)"""
    ticker_score = {}
    for theme, s in theme_score.items():
        cfg = THEME_MAP.get(theme)
        if not cfg:
            continue
        for tkr in cfg.get("direct", []):
            ticker_score[tkr] = ticker_score.get(tkr, 0.0) + 1.0 * s
        for tkr in cfg.get("related", []):
            ticker_score[tkr] = ticker_score.get(tkr, 0.0) + 0.5 * s
    return ticker_score

def format_news_header(news: dict, name_map: dict[str, str] | None = None) -> str:
    """모바일 헤더: 기사별 영향 종목(이름) 표시. direct 우선, 부족하면 related 보조."""
    lines = []
    lines.append("🌅 아침 시황/뉴스 (전일 15:30 ~ 오늘 08:30)")
    for it in news["highlights"]:
        ts = _short_time(it["published"])
        title_ko = _to_korean_headline(it["title"])
        show = it["tickers_direct"] + [t for t in it["tickers_related"] if t not in it["tickers_direct"]]
        show = show[:3]
        if name_map:
            show = [name_map.get(t, t) for t in show]
        impacted_str = ", ".join(show) if show else "—"
        lines.append(f"- [{ts}] {title_ko} ({it['source']}) → 영향: {impacted_str}")
    if news["theme_score"]:
        hot = sorted(news["theme_score"].items(), key=lambda x: x[1], reverse=True)[:3]
        if hot:
            lines.append("")
            lines.append("🔥 강한 테마: " + ", ".join([f"{k}" for k,_ in hot]))
    return "\n".join(lines)

def build_ticker_reasons(news: dict, name_map: dict[str, str]) -> dict[str, list[str]]:
    """각 티커별로 관련 뉴스 1~2줄 근거 생성. direct 우선, 없으면 related 사용."""
    reasons: dict[str, list[str]] = {}
    for it in news["highlights"]:
        title_ko = _to_korean_headline(it["title"])
        ts = _short_time(it["published"])
        src = it["source"]
        # 먼저 direct
        targets = it.get("tickers_direct", [])
        if not targets:
            targets = it.get("tickers_related", [])
        for tk in targets:
            line = f"[{ts}] {title_ko} ({src})"
            arr = reasons.setdefault(tk, [])
            if len(arr) < 2:
                arr.append(line)
    return reasons
