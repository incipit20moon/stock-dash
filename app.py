import hashlib
import html
import hmac
import json
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from research_ui import render_research
from education import render_education
from automatic import brief
from data_registry import PROVIDERS, capabilities as active_capabilities, health_all
from providers import DataError, Official, demo
from storage import Store
from portfolio_ui import render_portfolio
from ui_v2 import apply_theme, brand, card, empty_state, hero, source_badge


load_dotenv()
st.set_page_config(
    page_title="StockDash · PlanX Investment OS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    for key in [
        "APP_PASSWORD",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "DATA_GO_KR_SERVICE_KEY",
        "DART_CRTFC_KEY",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "KIS_ENV", "KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO", "KIS_ACNT_PRDT_CD",
    ]:
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except FileNotFoundError:
    pass

apply_theme()


class SessionStore:
    cloud = False

    def read(self):
        return st.session_state.setdefault("practice_data", {"stocks": [], "journal": [], "runs": []})

    def save_stock(self, stock):
        data = self.read()
        for index, old in enumerate(data["stocks"]):
            if old["code"] == stock["code"]:
                data["stocks"][index] = {**old, **stock}
                return
        data["stocks"].append(stock)

    def log(self, collection, item):
        self.read()[collection].append(item)

    def change(self, operation):
        operation(self.read())


def load_store(password):
    sample = not password
    if sample or st.session_state.get("practice_mode"):
        current_store = SessionStore()
    else:
        current_store = Store()
    return sample, current_store, current_store.read()


def stock_label(item):
    code = item.get("code", "")
    suffix = "코드 확인 대기" if code.startswith("pending-") else code
    return f"{item.get('name', '종목')} · {suffix}"


def extract_business_sentences(report):
    excerpt = report.get("business_excerpt", "")
    sentences = [
        x.strip()
        for x in re.split(r"(?<=[.!?])\s+", excerpt)
        if 35 < len(x.strip()) < 650
        and any(w in x for w in ["사업", "제조", "생산", "판매", "서비스"])
        and re.search(r"다[.!?]$", x.strip())
        and "---" not in x
    ]
    return sentences[:3]


password = os.getenv("APP_PASSWORD", "")
if password and not st.session_state.get("authorized"):
    hero("StockDash", "공식 데이터를 연결해 시장과 기업의 변화를 한 흐름으로 읽습니다.", "SECURE ACCESS")
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        with st.container(border=True):
            st.subheader("개인 대시보드 열기")
            with st.form("login"):
                entered = st.text_input("비밀번호", type="password", placeholder="설정한 비밀번호를 입력하세요")
                if st.form_submit_button("대시보드 열기", type="primary", use_container_width=True):
                    if hmac.compare_digest(entered.encode(), password.encode()):
                        st.session_state.authorized = True
                        st.rerun()
                    st.error("비밀번호를 확인하세요.")
    st.stop()

try:
    sample_mode, store, state = load_store(password)
except Exception:
    hero("저장 공간 연결 확인", "기존 자료는 덮어쓰지 않습니다. 저장소 설정만 확인합니다.", "STORAGE")
    st.error("비밀번호 확인은 통과했지만 종목 저장 공간을 열지 못했습니다.")
    url_set = bool(os.getenv("SUPABASE_URL", "").strip())
    key_set = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip())
    if url_set != key_set:
        st.info("Supabase URL과 service_role 키 중 하나만 설정되어 있습니다.")
    elif url_set:
        st.info("Supabase 프로젝트 주소·서버 키·schema.sql 실행 여부를 확인하세요.")
    else:
        st.info("로컬 저장 파일을 열지 못했습니다. 아래 임시 실습은 현재 접속에서만 유지됩니다.")
    if st.button("저장 연결 없이 임시 실습 시작", type="primary"):
        st.session_state.practice_mode = True
        st.rerun()
    st.stop()


REMOVE_FROM_MY_STOCKS = {"현대", "현대자동차"}


def remove_requested_stocks(store, state):
    """Remove explicitly requested names from the persistent '내 종목' list."""
    unwanted = {name.casefold() for name in REMOVE_FROM_MY_STOCKS}
    removed_codes = {
        item.get("code")
        for item in state.get("stocks", [])
        if item.get("name", "").strip().casefold() in unwanted
    }
    if not removed_codes:
        return

    def cleanup(data):
        data["stocks"] = [
            item for item in data.get("stocks", [])
            if item.get("name", "").strip().casefold() not in unwanted
        ]

    store.change(cleanup)
    state["stocks"] = [
        item for item in state.get("stocks", [])
        if item.get("name", "").strip().casefold() not in unwanted
    ]
    if st.session_state.get("selected_code") in removed_codes:
        st.session_state.pop("selected_code", None)
    latest = st.session_state.get("latest_analysis")
    if latest and latest.get("code") in removed_codes:
        st.session_state.pop("latest_analysis", None)


remove_requested_stocks(store, state)


def run_analysis(code):
    try:
        with st.spinner("공식 시세 · 결산 · 가치 · 사업 공시를 확인합니다…"):
            provider = st.session_state.get("directory_provider") or Official()
            if code.startswith("pending-"):
                pending = next((s for s in state["stocks"] if s["code"] == code), {})
                matches = provider.search(pending.get("name", ""))
                if len(matches) != 1:
                    st.session_state.search_candidates = matches
                    st.info("검색 목록에서 정확한 종목을 선택하세요.")
                    return
                code = matches[0]["code"]

            price, price_day, price_name = provider.price(code, date.today())
            try:
                report = provider.automatic(code)
            except DataError as error:
                existing = next((s for s in state["stocks"] if s["code"] == code), {})
                partial = {
                    **existing,
                    "code": code,
                    "name": price_name,
                    "kind": existing.get("kind", "관심"),
                    "price_snapshot": {"price": price, "date": price_day},
                    "analysis_error": str(error),
                }
                st.session_state.latest_analysis = partial
                try:
                    store.save_stock(partial)
                    st.session_state.save_notice = "시세·관심종목은 저장했습니다. 재무 분석은 완료되지 않았습니다."
                except Exception:
                    st.session_state.save_notice = "시세만 조회했습니다. 저장소 기록은 실패했습니다."
                st.session_state.selected_code = code
                st.session_state.force_nav = "종목 분석"
                st.session_state.pop("stock_picker", None)
                st.session_state.pop("search_candidates", None)
                st.rerun()

            result = brief(report)
            ai = None  # Narrative research is supplied through chat, without an LLM API.
            at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            existing = next((s for s in state["stocks"] if s["code"] == code), {})
            stock = {
                **existing,
                "code": code,
                "name": report["name"],
                "kind": existing.get("kind", "관심"),
                "year": report["years"][-1]["year"],
                "report": report,
                "automatic_brief": result,
                "ai_brief": ai,
                "analyzed_at": at,
                "analysis_error": None,
            }
            st.session_state.latest_analysis = stock
            try:
                store.save_stock(stock)
                store.log(
                    "journal",
                    {
                        "code": code,
                        "at": at,
                        "kind": "automatic",
                        "report": report,
                        "automatic_brief": result,
                        "ai_brief": ai,
                    },
                )

                def consolidate(data):
                    pending_ids = {
                        s["code"]
                        for s in data["stocks"]
                        if s["code"].startswith("pending-")
                        and s["name"].casefold() == report["name"].casefold()
                    }
                    for item in data["journal"]:
                        if item["code"] in pending_ids:
                            item["code"] = code
                    data["stocks"] = [s for s in data["stocks"] if s["code"] not in pending_ids]

                store.change(consolidate)
                st.session_state.save_notice = "분석 결과와 이력을 저장했습니다."
            except Exception:
                st.session_state.save_notice = "분석은 끝났지만 저장하지 못했습니다. JSON 다운로드로 보관할 수 있습니다."

            st.session_state.selected_code = code
            st.session_state.force_nav = "종목 분석"
            st.session_state.pop("stock_picker", None)
            st.session_state.pop("search_candidates", None)
        st.rerun()
    except DataError as error:
        st.error(str(error))
    except Exception:
        st.error("분석을 마치지 못했습니다. 이전 결과는 유지됩니다.")


choices = {s["code"]: s for s in state.get("stocks", [])}
latest = st.session_state.get("latest_analysis")
if latest:
    choices[latest["code"]] = latest

if st.session_state.get("force_nav"):
    st.session_state.nav_choice = st.session_state.pop("force_nav")

NAV_ITEMS = ["홈", "내 종목", "계좌 연결", "교육자료", "설정"]
legacy = {"통합 분석":"홈", "AI 인사이트":"홈", "관심 종목":"내 종목", "포트폴리오":"계좌 연결"}
current = st.session_state.get("nav_choice", "홈")
if current not in NAV_ITEMS:
    st.session_state.nav_choice = legacy.get(current, "설정")
    if current not in legacy:
        st.session_state.advanced_page = current

with st.sidebar:
    brand()
    nav = st.radio("메뉴", NAV_ITEMS, key="nav_choice")
    st.markdown("---")
    if choices and nav == "설정":
        codes = list(choices)
        preferred = st.session_state.get("selected_code")
        selected = st.selectbox(
            "현재 종목",
            codes,
            index=codes.index(preferred) if preferred in codes else 0,
            format_func=lambda c: stock_label(choices[c]),
            key="stock_picker",
        )
        stock = choices[selected]
    elif choices:
        stock = choices.get(st.session_state.get("selected_code"), next(iter(choices.values())))
    else:
        stock = {"code": "SAMPLE", "name": "가상 반도체", "report": demo()}

    if sample_mode:
        st.caption("가상 예시 모드")
    elif st.session_state.get("practice_mode"):
        st.caption("임시 저장 모드")
    else:
        st.caption("클라우드 저장" if store.cloud else "실행 서버 저장")

    if password and st.button("로그아웃", use_container_width=True):
        st.session_state.clear()
        st.rerun()

report = stock.get("report")
is_demo = stock.get("code") == "SAMPLE"


def global_search():
    if sample_mode:
        st.info("현재는 가상 예시 모드입니다. APP_PASSWORD와 공식 API 키가 설정되면 실데이터 검색이 열립니다.")
        return
    with st.form("global_search"):
        col_q, col_b = st.columns([6, 1])
        with col_q:
            query = st.text_input(
                "통합 검색",
                placeholder="종목명, 종목코드, 기업명 일부를 검색하세요. 예: 삼성전자 · 005930 · 하이닉스",
                label_visibility="collapsed",
            )
        with col_b:
            submitted = st.form_submit_button("검색·분석", type="primary", use_container_width=True)
    if submitted:
        try:
            provider = st.session_state.get("directory_provider") or Official()
            st.session_state.directory_provider = provider
            matches = provider.search(query)
            st.session_state.search_candidates = matches
            if len(matches) == 1:
                run_analysis(matches[0]["code"])
            elif not matches:
                st.info("일치하는 상장 기업이 없습니다. 기업명 일부나 6자리 종목코드로 다시 검색하세요.")
        except DataError as error:
            st.error(str(error))

    matches = st.session_state.get("search_candidates", [])
    if len(matches) > 1:
        with st.container(border=True):
            st.caption("검색어와 일치하는 기업입니다.")
            with st.form("candidate"):
                candidate = st.selectbox(
                    "검색된 종목",
                    matches,
                    format_func=lambda x: x["name"] + " · " + x["code"],
                )
                if st.form_submit_button("이 종목 분석", type="primary"):
                    run_analysis(candidate["code"])




def render_home():
    """Image-inspired investment dashboard home."""
    st.markdown(
        '''<div class="stockdash-topbar">
          <div class="stockdash-greeting">
            <h1>안녕하세요, 투자자님! 👋</h1>
            <p>오늘의 시장 흐름과 내 종목을 한 화면에서 확인하세요.</p>
          </div>
          <div class="stockdash-search">⌕  종목명 또는 코드 검색</div>
        </div>''',
        unsafe_allow_html=True,
    )

    global_search()

    caps = active_capabilities()
    market_items = [
        ("KOSPI", "market.index"),
        ("KOSDAQ", "market.index"),
        ("NASDAQ", "market.index"),
        ("S&P 500", "market.index"),
        ("USD/KRW", "macro.fx"),
    ]
    cards = []
    for label, cap in market_items:
        connected = cap in caps
        cards.append(
            f'''<div class="stockdash-kpi">
              <div class="stockdash-kpi-label">{html.escape(label)}</div>
              <div class="stockdash-kpi-value">{'연결됨' if connected else '연결 대기'}</div>
              <div class="stockdash-kpi-note">{html.escape(cap)}</div>
            </div>'''
        )
    st.markdown('<div class="stockdash-kpi-grid">' + "".join(cards) + '</div>', unsafe_allow_html=True)

    saved = [
        s for s in state.get("stocks", [])
        if s.get("name", "").strip().casefold() not in REMOVE_FROM_MY_STOCKS
    ]
    focus = stock if stock.get("code") != "SAMPLE" else (saved[0] if saved else stock)
    focus_report = focus.get("report") or {}
    focus_price = focus_report.get("price")
    focus_price_text = f"{focus_price:,.0f}원" if isinstance(focus_price, (int, float)) else "분석 데이터 대기"
    focus_name = html.escape(focus.get("name", "삼성전자"))
    focus_code = html.escape(focus.get("code", ""))

    if focus_report:
        result = brief(focus_report)
        fair = result.get("fair")
        growth_text = result.get("growth", "자료 부족")
        value_text = result.get("value", "자료 부족")
        fair_text = f"{fair['base']:,.0f}원" if fair else "자료 부족"
        price_date = focus_report.get("price_date", "")
        close_text = f"{focus_report.get('price', 0):,.0f}원" if isinstance(focus_report.get("price"), (int,float)) else "—"
        ohlc = [
            ("기준 종가", close_text),
            ("성장", str(growth_text)),
            ("가치", str(value_text)),
            ("참고가", fair_text),
            ("기준일", str(price_date or "—")),
        ]
    else:
        ohlc = [
            ("기준 종가", "—"), ("성장", "—"), ("가치", "—"), ("참고가", "—"), ("기준일", "—")
        ]

    hero_stats = "".join(
        f'<div><span>{html.escape(k)}</span><strong>{html.escape(v)}</strong></div>' for k, v in ohlc
    )

    watch_rows = []
    for item in saved[:5]:
        rep = item.get("report") or {}
        p = rep.get("price")
        ptxt = f"{p:,.0f}원" if isinstance(p, (int,float)) else "—"
        status = "분석 완료" if rep else "분석 필요"
        watch_rows.append(
            f'''<div class="stockdash-watch-row">
              <div><span class="stockdash-stock-name">{html.escape(item.get("name","종목"))}</span>
              <span class="stockdash-stock-code">{html.escape(item.get("code",""))}</span></div>
              <div class="stockdash-stock-price">{html.escape(ptxt)}</div>
              <div class="stockdash-stock-change">{html.escape(status)}</div>
              <div><span class="stockdash-chip">{html.escape(item.get("kind","관심"))}</span></div>
            </div>'''
        )

    st.markdown(
        f'''<div class="stockdash-grid-3">
          <div class="stockdash-hero-card">
            <div><span class="stockdash-hero-name">{focus_name}</span><span class="stockdash-hero-code">{focus_code}</span></div>
            <div class="stockdash-hero-price">{html.escape(focus_price_text)}</div>
            <div class="stockdash-hero-change">공식 데이터 기준</div>
            <div class="stockdash-hero-meta">
              <span class="stockdash-dark-chip">코스피</span>
              <span class="stockdash-dark-chip">내 종목</span>
              <span class="stockdash-dark-chip">분석 포커스</span>
            </div>
            <div class="stockdash-ohlc">{hero_stats}</div>
          </div>

          <div class="stockdash-small-card">
            <div class="stockdash-title-row"><strong>{focus_name} 주가 차트</strong><span>공식 데이터 기반</span></div>
            <div style="height:220px;display:flex;align-items:center;justify-content:center;border-radius:12px;background:linear-gradient(180deg,#F8FAFF,#FFFFFF);color:#94A3B8;font-size:12px;text-align:center;padding:20px">
              분석 데이터가 연결되면<br>가격 추이 차트가 이 영역에 표시됩니다.
            </div>
          </div>

          <div class="stockdash-small-card">
            <div class="stockdash-title-row"><strong>내 종목</strong><span>전체보기</span></div>
            {''.join(watch_rows) if watch_rows else '<div class="stockdash-ai-text">아직 저장된 종목이 없습니다.<br>삼성전자부터 추가해보세요.</div>'}
          </div>
        </div>''',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="stockdash-section"><h3>포트폴리오 & 인사이트</h3><span>내 데이터 기준</span></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1.25, 1, 1], gap="large")

    with col1:
        with st.container(border=True):
            st.subheader("내 포트폴리오 현황")
            snapshot = st.session_state.get("account_snapshot") or {}
            positions = snapshot.get("positions", [])
            total_value = snapshot.get("total_value")
            if isinstance(total_value, (int, float)):
                st.metric("총 자산", f"{total_value:,.0f}원")
            else:
                st.metric("총 자산", "계좌 연결 필요")
            st.caption(f"보유 종목 {len(positions)}개" if positions else "계좌를 연결하면 보유 종목이 표시됩니다.")

    with col2:
        with st.container(border=True):
            st.subheader("자산 비중")
            st.markdown(
                '''<div style="height:180px;display:flex;align-items:center;justify-content:center;border-radius:999px;
                background:conic-gradient(#2563EB 0 62%,#93C5FD 62% 78%,#E5E7EB 78% 100%);max-width:180px;margin:0 auto">
                  <div style="width:110px;height:110px;border-radius:999px;background:white;display:flex;align-items:center;justify-content:center;text-align:center;font-weight:800;color:#111827">
                    Asset<br>Mix
                  </div>
                </div>''',
                unsafe_allow_html=True,
            )

    with col3:
        with st.container(border=True):
            st.subheader("AI 인사이트 요약")
            ai = focus.get("ai_brief") or {}
            if ai.get("status") == "ok" and ai.get("text"):
                st.write(ai["text"])
            else:
                st.markdown(
                    '<div class="stockdash-ai"><div class="stockdash-ai-title">AI SUMMARY</div>'
                    '<div class="stockdash-ai-text">공식 데이터와 공시 기반 분석 결과가 준비되면 핵심 변화와 확인 포인트를 이 영역에 요약합니다.</div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown('<div class="stockdash-section"><h3>오늘의 정보</h3><span>공시 · 빠른 메뉴</span></div>', unsafe_allow_html=True)
    left, right = st.columns([1.4, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("주요 뉴스 & 공시")
            notices = []
            if focus_report:
                notices = sorted(focus_report.get("disclosures", []), key=lambda x: x.get("date", ""), reverse=True)
            if notices:
                for item in notices[:5]:
                    st.link_button(
                        f"{item.get('date','')} · {item.get('title','')}",
                        item.get("url", "#"),
                        use_container_width=True,
                    )
            else:
                st.caption("분석된 종목의 최근 공시가 이곳에 표시됩니다.")

    with right:
        st.markdown(
            '''<div class="stockdash-small-card">
              <div class="stockdash-title-row"><strong>빠른 메뉴</strong><span>바로가기</span></div>
              <div class="stockdash-quick-grid">
                <div class="stockdash-quick">🔎<b>종목 검색</b></div>
                <div class="stockdash-quick">⭐<b>관심 종목</b></div>
                <div class="stockdash-quick">📊<b>시장 현황</b></div>
                <div class="stockdash-quick">📄<b>종목 분석</b></div>
                <div class="stockdash-quick">💼<b>계좌 연결</b></div>
                <div class="stockdash-quick">💡<b>AI 인사이트</b></div>
              </div>
            </div>''',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="stockdash-footer">StockDash · 공식 데이터와 공시를 기반으로 구성한 개인 투자 대시보드</div>',
        unsafe_allow_html=True,
    )

def render_market():
    hero("시장 현황", "지수·거래대금·시장 폭·투자자 수급을 한 화면으로 연결하는 영역입니다.", "MARKET")
    caps = active_capabilities()
    source_badge(f"현재 활성 Capability {len(caps)}개", "ok" if caps else "wait")
    st.markdown("")
    rows = [
        ("시장 지수", "market.index", "KOSPI·KOSDAQ 지수와 등락"),
        ("시장 폭", "market.breadth", "상승·하락 종목 수와 확산도"),
        ("거래대금", "market.turnover", "시장/종목 거래대금"),
        ("투자자 수급", "market.investor_flow", "외국인·기관·개인 순매수"),
        ("업종", "sector.performance", "업종별 등락과 주도 섹터"),
        ("환율", "macro.fx", "원/달러 등 거시 변수"),
    ]
    for title, cap, desc in rows:
        with st.container(border=True):
            a, b = st.columns([2, 5])
            with a:
                st.markdown(f"**{title}**")
                source_badge("연결됨" if cap in caps else "기관 API 필요", "ok" if cap in caps else "wait")
            with b:
                st.write(desc)
                st.caption(cap)


def render_stock():
    title = stock["name"] + (" · 가상 예시" if is_demo else " · " + ("코드 확인 대기" if stock["code"].startswith("pending-") else stock["code"]))
    hero(title, "기업 특징 → 실적 → 가치 → 공시 → 다음 확인 질문 순서로 읽습니다.", "STOCK 360")
    global_search()

    if not is_demo:
        b1, b2 = st.columns([1, 5])
        with b1:
            if st.button("최신 데이터", type="primary", use_container_width=True):
                run_analysis(stock["code"])
        with b2:
            if st.session_state.get("save_notice"):
                st.caption(st.session_state.save_notice)

    if stock.get("analysis_error"):
        st.warning(stock["analysis_error"])
        snapshot = stock.get("price_snapshot")
        if snapshot:
            st.metric("조회된 기준 종가", f"{snapshot['price']:,.0f}원")
            st.caption("시세 기준일: " + snapshot["date"])

    if not report:
        empty_state("기업·재무 자료 없음", "관심종목과 투자일지는 사용할 수 있습니다. 데이터가 없으면 임의 분석값을 만들지 않습니다.")
        return

    result = brief(report)
    fair = result["fair"]
    company = report.get("company", {})
    sectors = result["sectors"]
    sentences = extract_business_sentences(report)

    st.caption(
        f"시세 {report.get('price_date','')} · 결산 {report['years'][-1]['year']} · "
        f"{report.get('basis','')} · 조회 {report.get('fetched','')}"
    )
    if report.get("sample"):
        st.warning("가상 종목·숫자입니다. 실제 투자 판단에 사용하지 마세요.")

    tabs = st.tabs(["한눈에 분석", "기업·섹터", "공시", "투자일지"])
    with tabs[0]:
        cols = st.columns(4)
        cols[0].metric("기준 종가", f"{report['price']:,.0f}원")
        cols[1].metric("성장", result["growth"])
        cols[2].metric("가치 상태", result["value"])
        cols[3].metric("적정주가 참고", f"{fair['base']:,.0f}원" if fair else "자료 부족")

        left, right = st.columns([2, 1])
        with left:
            with st.container(border=True):
                st.subheader("이 기업은 무엇을 하나요?")
                if sentences:
                    for sentence in sentences:
                        st.write("• " + sentence)
                elif report.get("business_excerpt"):
                    st.info("사업 원문은 수집됐지만 요약할 설명 문장을 찾지 못했습니다.")
                else:
                    st.info("사업 원문이 아직 수집되지 않았습니다.")
                st.caption(f"사업보고서 발췌 · {report['years'][-1]['year']}년 결산 기준")
        with right:
            with st.container(border=True):
                st.subheader("사업 키워드")
                st.write(" · ".join(x["sector"] for x in sectors) if sectors else "분류 대기")
                st.caption("공시 원문 키워드 후보이며 공식 주력 섹터 확정이 아닙니다.")
                st.write("업종코드 · " + str(company.get("induty_code", "미수집")))

        st.subheader("실적 변화")
        chart = pd.DataFrame(report["years"])[["year", "revenue", "profit"]].rename(
            columns={"year": "연도", "revenue": "매출", "profit": "영업이익"}
        )
        chart["연도"] = chart["연도"].astype(str)
        st.bar_chart(chart.set_index("연도"), color=["#2563EB", "#10B981"])
        st.dataframe(chart, hide_index=True, use_container_width=True)
        st.caption("단위 억원 · 확정 결산 기준. 분기 실적이나 미래 전망을 대신하지 않습니다.")

        st.subheader("판단 근거")
        m1, m2, m3 = st.columns(3)
        m1.metric("매출 성장률", f"{result['revenue_growth']:+.1f}%" if result["revenue_growth"] is not None else "자료 부족")
        m2.metric("영업이익 성장률", f"{result['profit_growth']:+.1f}%" if result["profit_growth"] is not None else "자료 부족")
        m3.metric("영업이익률", f"{result['margin']:.1f}%" if result["margin"] is not None else "자료 부족")

        if fair:
            f1, f2, f3 = st.columns(3)
            f1.metric("역사적 낮은 범위", f"{fair['low']:,.0f}원")
            f2.metric("역사적 중간 참고", f"{fair['base']:,.0f}원")
            f3.metric("역사적 높은 범위", f"{fair['high']:,.0f}원")
            st.caption(f"중간 참고값 대비 현재 가격 차이 {fair['gap']:+.1f}% · 매수/매도 신호가 아닙니다.")
        st.write(result["fair_reason"])

        ai = stock.get("ai_brief")
        if ai and ai.get("status") == "ok":
            with st.expander("AI 핵심 해설"):
                st.markdown(ai["text"])
                st.caption("공식 데이터·공시 발췌 기반 해설 · 원문 대조 필요")

    with tabs[1]:
        st.subheader("기업 핵심 분석")
        st.write(result["summary"])
        if company:
            st.caption("DART 기업명 · " + str(company.get("corp_name", "")) + " / 업종코드 · " + str(company.get("induty_code", "")))
        excerpt = report.get("business_excerpt", "")
        if excerpt:
            with st.container(border=True):
                st.write(excerpt[:2200] + ("…" if len(excerpt) > 2200 else ""))
            with st.expander("사업보고서 발췌 전체 보기"):
                st.text(excerpt)
        if sectors:
            st.subheader("섹터 후보와 확인 지표")
            for sector in sectors:
                with st.container(border=True):
                    st.markdown("**" + sector["sector"] + "**")
                    st.write(sector["logic"])
                    st.write("확인할 지표 · " + " · ".join(sector["signals"]))
                    st.caption("원문 발견 단어 · " + ", ".join(sector["keywords"]))

    with tabs[2]:
        st.subheader("최근 공시")
        st.caption("현재 수집본 기준이며 실시간 뉴스 전체를 뜻하지 않습니다.")
        notices = sorted(report.get("disclosures", []), key=lambda x: x.get("date", ""), reverse=True)
        if notices:
            for item in notices[:12]:
                st.link_button(item["date"] + " · " + item["title"], item["url"], use_container_width=True)
        else:
            empty_state("최근 공시 없음", "현재 수집본에 공시가 없으며, 공시가 없다는 확정 판단은 아닙니다.")

    with tabs[3]:
        if is_demo:
            st.info("실제 종목을 분석하면 투자일지와 분석 이력을 저장할 수 있습니다.")
        else:
            with st.form("note"):
                kind = st.selectbox("내 종목 구분", ["관심", "보유"], index=1 if stock.get("kind") == "보유" else 0)
                note = st.text_area("나의 판단 · 다음 확인 조건")
                if st.form_submit_button("기록 저장", type="primary"):
                    try:
                        store.save_stock({"code": stock["code"], "kind": kind})
                        store.log(
                            "journal",
                            {
                                "code": stock["code"],
                                "at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                                "kind": "note",
                                "note": note,
                            },
                        )
                        st.session_state.pop("latest_analysis", None)
                        st.rerun()
                    except Exception:
                        st.error("기록 저장 실패. 입력 내용을 복사해 보관하세요.")

            st.download_button(
                "현재 분석 JSON 다운로드",
                json.dumps(stock, ensure_ascii=False, indent=2),
                file_name=stock["code"] + "-analysis.json",
                mime="application/json",
            )
            history = [item for item in state.get("journal", []) if item["code"] == stock["code"]]
            for item in reversed(history):
                with st.expander(item["at"] + " · " + item["kind"]):
                    if item.get("note"):
                        st.write(item["note"])
                    elif item.get("automatic_brief"):
                        st.write(item["automatic_brief"]["summary"])
                        st.caption("시세 기준일 · " + item.get("report", {}).get("price_date", ""))


def render_disclosures():
    hero("공시 분석", "실적·수주·투자·자본조달 등 기업의 공식 변화를 먼저 확인합니다.", "DART")
    global_search()
    if not report:
        empty_state("분석할 공시가 없습니다", "종목을 검색해 공식 공시 데이터를 먼저 수집하세요.")
        return
    notices = sorted(report.get("disclosures", []), key=lambda x: x.get("date", ""), reverse=True)
    st.subheader(stock["name"] + " · 최근 공시")
    if notices:
        for item in notices[:20]:
            with st.container(border=True):
                a, b = st.columns([1, 6])
                with a:
                    st.markdown("**" + item["date"] + "**")
                with b:
                    st.write(item["title"])
                    st.link_button("공시 원문", item["url"])
    else:
        empty_state("현재 수집 공시 없음", "공시 수집 범위와 기준일을 확인하세요.")


def render_watchlist():
    hero("관심 종목", "분석이 끝나지 않아도 저장하고, 다음 확인 조건을 남길 수 있습니다.", "WATCHLIST")
    if sample_mode:
        st.info("APP_PASSWORD 설정 후 개인 관심종목 저장이 활성화됩니다.")
        return

    with st.container(border=True):
        st.subheader("관심종목 추가")
        with st.form("save_watch_only"):
            name = st.text_input("종목명", placeholder="예: 삼성전자")
            code = st.text_input("종목코드", placeholder="선택 · 6자리", max_chars=6)
            if st.form_submit_button("관심종목 저장", type="primary"):
                name, code = name.strip(), code.strip()
                if not name or (code and (len(code) != 6 or not code.isascii() or not code.isdigit())):
                    st.error("종목명을 입력하고, 코드는 생략하거나 숫자 6자리로 입력하세요.")
                else:
                    existing = next((s for s in state["stocks"] if s["name"].casefold() == name.casefold()), {})
                    identity = existing.get("code") or code or "pending-" + hashlib.sha256(name.casefold().encode()).hexdigest()[:16]
                    try:
                        store.save_stock({"code": identity, "name": name, "kind": existing.get("kind", "관심")})
                        st.session_state.selected_code = identity
                        st.rerun()
                    except Exception:
                        st.error("관심종목 저장에 실패했습니다.")

    st.subheader("저장된 종목")
    if choices:
        rows = []
        for item in choices.values():
            if item.get("code") == "SAMPLE":
                continue
            rows.append(
                {
                    "종목": item.get("name", ""),
                    "코드": "확인 대기" if item["code"].startswith("pending-") else item["code"],
                    "구분": item.get("kind", "관심"),
                    "최근 분석": item.get("analyzed_at", "")[:16].replace("T", " "),
                    "상태": "분석 필요" if not item.get("report") else "분석 저장됨",
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            empty_state("관심종목 없음", "위 입력창에서 첫 종목을 추가하세요.")
    else:
        empty_state("관심종목 없음", "위 입력창에서 첫 종목을 추가하세요.")


def render_ai():
    hero("AI 인사이트", "AI는 숫자를 만들지 않고 수집된 공식 데이터의 변화와 의미를 설명합니다.", "AI")
    if not report:
        empty_state("분석 데이터가 필요합니다", "종목 분석을 먼저 실행한 뒤 AI 해설을 확인하세요.")
        return
    ai = stock.get("ai_brief")
    if ai and ai.get("status") == "ok":
        st.subheader(stock["name"] + " · 핵심 해설")
        st.markdown(ai["text"])
        st.caption("AI 해설 · 공식 데이터와 공시 발췌 기반 · 원문 대조 필요")
    else:
        empty_state(
            "AI 해설 미연결",
            "OPENAI_API_KEY와 사용 가능한 OPENAI_MODEL이 설정되면 종목 분석 시 공식 데이터 기반 해설을 함께 생성합니다.",
        )


def render_sources():
    hero("데이터 연결 관리", "기관 API의 인증·응답·사용 가능 기능을 한 곳에서 확인합니다.", "DATA SOURCES")
    st.caption("키 값 자체는 화면에 표시하지 않습니다.")

    if st.button("전체 연결 진단", type="primary"):
        with st.spinner("기관 API 상태를 확인합니다…"):
            st.session_state.provider_health = health_all()

    health_by_id = {row["provider_id"]: row for row in st.session_state.get("provider_health", [])}
    for spec in PROVIDERS:
        check = health_by_id.get(spec.provider_id)
        with st.container(border=True):
            left, right = st.columns([2, 5])
            with left:
                st.subheader(spec.name)
                if not check:
                    source_badge("진단 전", "wait")
                elif check["status"] == "ok":
                    source_badge("정상", "ok")
                elif check["status"] == "not_configured":
                    source_badge("인증정보 필요", "wait")
                else:
                    source_badge("확인 필요", "bad")
            with right:
                st.markdown("**사용 가능 기능**")
                st.write(" · ".join(spec.capabilities))
                if check:
                    st.caption(
                        f"{check['detail']} · 응답 {check['latency_ms']}ms · 확인 {check['checked_at']}"
                    )

    st.subheader("추가 기관 API 슬롯")
    empty_state(
        "Adapter Registry 준비됨",
        "새 기관 API는 기관명·문서·인증정보를 받으면 Capability를 분류한 뒤 독립 Adapter로 연결합니다.",
    )


def render_placeholder(title, subtitle, required):
    hero(title, subtitle, title.upper())
    caps = active_capabilities()
    for name, cap, desc in required:
        with st.container(border=True):
            a, b = st.columns([2, 5])
            with a:
                st.markdown("**" + name + "**")
                source_badge("연결됨" if cap in caps else "API 연결 대기", "ok" if cap in caps else "wait")
            with b:
                st.write(desc)
                st.caption(cap)


if nav == "홈":
    render_home()
elif nav == "내 종목":
    render_research(store, state, sample_mode)
elif nav == "계좌 연결":
    render_portfolio(store, sample_mode)
elif nav == "교육자료":
    render_education()
else:
    st.header("설정과 추가 도구")
    st.caption("계좌 연결 없이도 내 종목을 추가하고 조사 결과를 확인할 수 있습니다.")
    options = ["사용 안내", "데이터 연결 관리", "종목 분석", "공시 분석", "시장 현황", "테마 & 섹터"]
    previous = st.session_state.get("advanced_page", "사용 안내")
    if previous not in options: st.session_state.advanced_page = "사용 안내"
    page = st.selectbox("필요한 도구", options, key="advanced_page")
    if page == "사용 안내":
        st.markdown("**1. 내 종목**에서 기업 이름을 추가하세요.\n\n**2. 조사 요청**을 열어 요청문을 이 채팅에 보내세요.\n\n**3. 종목을 선택**해 핵심 요약과 자세한 근거를 확인하세요.")
        st.link_button("상세 사용 안내", "https://github.com/planxs-ai/stock-dash/blob/main/CHAT-RESEARCH.md")
    elif page == "데이터 연결 관리": render_sources()
    elif page == "종목 분석": render_stock()
    elif page == "공시 분석": render_disclosures()
    elif page == "시장 현황": render_market()
    else:
        render_placeholder("테마 & 섹터", "산업별 흐름을 확인합니다.", [("업종 강도", "sector.performance", "업종별 등락과 거래대금"), ("업종 수급", "sector.flow", "외국인·기관 자금 흐름"), ("산업 수출", "industry.export", "품목별 수출 변화")])
