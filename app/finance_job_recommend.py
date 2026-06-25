from __future__ import annotations

import os
import re
import json
import html as html_lib
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

import gradio as gr
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class FinanceJob:
    id: str
    title: str
    summary: str
    keywords: tuple[str, ...]
    skills: tuple[str, ...]
    preparation: str


JOBS: tuple[FinanceJob, ...] = (
    FinanceJob(
        id="finance_data_analyst",
        title="금융 데이터 분석가",
        summary="고객, 거래, 상품, 리스크 데이터를 분석해 금융 의사결정을 돕는 직무입니다.",
        keywords=("데이터", "분석", "sql", "python", "파이썬", "통계", "시각화", "고객 데이터", "거래 데이터"),
        skills=("SQL", "Python", "통계 기초", "데이터 시각화", "금융 데이터 이해"),
        preparation="고객·거래 데이터를 활용한 분석 프로젝트를 만들고 결과를 대시보드나 리포트로 정리하세요.",
    ),
    FinanceJob(
        id="retail_sales",
        title="리테일 금융/증권 영업",
        summary="개인 고객을 대상으로 금융상품을 상담하고 계좌, 상품, 서비스 이용을 안내하는 직무입니다.",
        keywords=("고객", "상담", "소통", "영업", "대면", "서비스", "창구", "금융상품", "증권"),
        skills=("고객 응대", "커뮤니케이션", "금융상품 기초", "설득력", "관계 관리"),
        preparation="고객 응대 경험을 정리하고 예금, 펀드, 증권상품의 기본 구조를 익히세요.",
    ),
    FinanceJob(
        id="pb_wm",
        title="PB/WM 자산관리",
        summary="고객의 자산 현황과 투자 성향을 바탕으로 포트폴리오를 상담하는 직무입니다.",
        keywords=("pb", "wm", "자산", "자산관리", "투자", "주식", "포트폴리오", "재무설계", "고액"),
        skills=("투자상품 이해", "포트폴리오 구성", "상담력", "시장 이해", "신뢰 형성"),
        preparation="투자상품과 자산배분 사례를 공부하고 고객 성향별 상담 시나리오를 연습하세요.",
    ),
    FinanceJob(
        id="financial_platform_pm",
        title="금융 플랫폼 기획자",
        summary="금융 앱과 디지털 서비스의 기능, UX, 사용자 흐름을 기획하는 직무입니다.",
        keywords=("플랫폼", "기획", "서비스", "ux", "ui", "앱", "핀테크", "프로덕트", "pm", "사용자"),
        skills=("서비스 기획", "UX 사고", "요구사항 정리", "데이터 기반 개선", "핀테크 이해"),
        preparation="금융 앱의 사용자 흐름을 분석하고 문제 정의부터 개선안까지 기획서로 정리하세요.",
    ),
    FinanceJob(
        id="risk_credit",
        title="리스크 관리/여신 심사",
        summary="신용도, 대출 가능성, 연체 가능성 등 금융 리스크를 검토하는 직무입니다.",
        keywords=("리스크", "위험", "신용", "여신", "심사", "대출", "연체", "채권", "평가"),
        skills=("재무제표 이해", "신용평가", "통계적 사고", "규정 이해", "꼼꼼함"),
        preparation="재무제표 분석과 신용평가 기준을 공부하고 대출 심사 케이스를 정리해보세요.",
    ),
    FinanceJob(
        id="research_investment",
        title="리서치/투자분석",
        summary="경제, 산업, 기업 데이터를 분석해 투자 판단 자료를 작성하는 직무입니다.",
        keywords=("리서치", "투자분석", "투자", "주식", "경제", "시장", "기업 분석", "산업", "보고서"),
        skills=("재무제표 분석", "경제 지표 이해", "기업 분석", "보고서 작성", "논리적 사고"),
        preparation="관심 산업 리포트를 읽고 기업 하나를 골라 투자 포인트와 리스크를 작성하세요.",
    ),
    FinanceJob(
        id="compliance_internal_control",
        title="컴플라이언스/내부통제",
        summary="금융 관련 법규, 내부 규정, 사고 예방 체계를 점검하는 직무입니다.",
        keywords=("컴플라이언스", "준법", "내부통제", "규정", "법", "감사", "금융소비자보호", "통제"),
        skills=("금융 법규 이해", "문서 검토", "윤리의식", "꼼꼼함", "리스크 예방 사고"),
        preparation="금융소비자보호, 자금세탁방지, 내부통제 관련 이슈를 사례 중심으로 정리하세요.",
    ),
    FinanceJob(
        id="investment_banking",
        title="증권사 IB",
        summary="기업금융, IPO, 채권 발행, 인수금융, M&A 등 기업의 자금조달과 거래를 지원하는 직무입니다.",
        keywords=("ib", "기업금융", "ipo", "상장", "m&a", "인수합병", "ecm", "dcm", "채권 발행", "프로젝트파이낸싱", "pf"),
        skills=("재무제표 분석", "기업가치평가", "시장 리서치", "자료 작성", "딜 프로세스 이해"),
        preparation="IPO나 M&A 사례를 하나 골라 산업, 기업가치, 투자 포인트를 짧은 피치북 형태로 정리하세요.",
    ),
    FinanceJob(
        id="sales_trading",
        title="증권사 S&T/트레이딩",
        summary="주식, 채권, 파생상품 등 금융상품을 매매하고 시장 흐름에 맞춰 운용 전략을 실행하는 직무입니다.",
        keywords=("s&t", "트레이딩", "딜링", "채권", "파생", "파생상품", "주식매매", "시장", "금리", "환율"),
        skills=("시장 모니터링", "금리·환율 이해", "수리적 사고", "리스크 관리", "빠른 의사결정"),
        preparation="금리, 환율, 주가지수 변화를 기록하고 투자 아이디어와 리스크를 함께 정리하는 습관을 만드세요.",
    ),
    FinanceJob(
        id="institutional_sales",
        title="증권사 기관영업",
        summary="연기금, 운용사, 법인 고객에게 리서치, 상품, 거래 서비스를 연결하는 B2B 영업 직무입니다.",
        keywords=("기관영업", "법인영업", "연기금", "운용사", "기관", "b2b", "세일즈", "고객관리", "리서치 세일즈"),
        skills=("시장 이해", "고객 커뮤니케이션", "상품 설명력", "관계 관리", "리서치 활용"),
        preparation="기관 고객 입장에서 필요한 시장 정보와 상품 설명을 1페이지 브리프로 정리해보세요.",
    ),
    FinanceJob(
        id="structured_products",
        title="증권사 금융상품/파생 구조화",
        summary="ELS, DLS, 채권형 상품 등 투자상품의 구조, 수익 조건, 리스크를 설계하는 직무입니다.",
        keywords=("els", "dls", "구조화", "금융상품", "파생", "파생상품", "상품개발", "채권형", "수익구조"),
        skills=("상품 구조 이해", "수리적 사고", "리스크 분석", "규정 이해", "투자자 관점"),
        preparation="ELS나 채권형 상품의 수익 조건과 손실 조건을 직접 풀어 설명하는 자료를 만들어보세요.",
    ),
    FinanceJob(
        id="card_product_planning",
        title="카드 상품기획",
        summary="신용카드와 체크카드의 혜택, 타깃 고객, 수익 구조, 출시 전략을 기획하는 직무입니다.",
        keywords=("카드", "신용카드", "체크카드", "상품기획", "혜택", "포인트", "마일리지", "연회비", "소비"),
        skills=("고객 세그먼트 분석", "손익 감각", "혜택 설계", "제휴 이해", "서비스 기획"),
        preparation="인기 카드 2~3개를 비교해 타깃, 혜택, 수익 구조를 표로 정리하고 개선 아이디어를 붙여보세요.",
    ),
    FinanceJob(
        id="card_marketing_crm",
        title="카드 마케팅/CRM",
        summary="고객 소비 데이터와 캠페인 성과를 바탕으로 카드 이용을 늘리는 마케팅 전략을 세우는 직무입니다.",
        keywords=("카드", "마케팅", "crm", "캠페인", "프로모션", "소비 데이터", "고객 세분화", "이용률", "혜택"),
        skills=("데이터 기반 마케팅", "고객 분석", "캠페인 기획", "성과 측정", "커뮤니케이션"),
        preparation="소비 업종별 고객군을 가정하고 각 고객군에 맞는 카드 캠페인 메시지와 KPI를 설계하세요.",
    ),
    FinanceJob(
        id="card_credit_strategy",
        title="카드 신용/리스크 전략",
        summary="카드 발급, 한도, 연체 가능성, 부정 사용 리스크를 데이터로 관리하는 직무입니다.",
        keywords=("카드", "신용", "리스크", "한도", "연체", "부정사용", "fraud", "심사", "스코어링"),
        skills=("신용평가 이해", "데이터 분석", "통계적 사고", "정책 설계", "리스크 모니터링"),
        preparation="연체율, 승인율, 한도 정책 같은 지표를 공부하고 신용평가 모델의 입력 변수를 정리하세요.",
    ),
    FinanceJob(
        id="merchant_payment_partnership",
        title="가맹점/결제 제휴",
        summary="가맹점, PG, 간편결제, 플랫폼 파트너와 제휴해 결제 이용처와 거래 규모를 넓히는 직무입니다.",
        keywords=("가맹점", "결제", "pg", "간편결제", "페이", "제휴", "파트너십", "정산", "승인"),
        skills=("제휴 제안", "결제 프로세스 이해", "B2B 커뮤니케이션", "데이터 기반 협상", "운영 관리"),
        preparation="자주 쓰는 결제 서비스의 가맹점 구조와 수수료, 고객 혜택을 조사해 제휴 제안서를 만들어보세요.",
    ),
    FinanceJob(
        id="insurance_product_actuary",
        title="보험 상품개발/계리",
        summary="보험료, 보장 구조, 손해율, 준비금 등을 계산해 보험상품을 설계하고 관리하는 직무입니다.",
        keywords=("보험", "상품개발", "계리", "보험계리", "보험료", "손해율", "준비금", "위험률", "보장"),
        skills=("보험수리", "통계", "상품 구조 이해", "손해율 분석", "엑셀·Python 활용"),
        preparation="보험계리사 과목과 손해율 개념을 공부하고, 간단한 보험료 산출 로직을 엑셀로 구현해보세요.",
    ),
    FinanceJob(
        id="insurance_underwriting",
        title="보험 언더라이팅/UW",
        summary="가입자의 위험 정보를 심사해 보험 인수 여부와 조건을 판단하는 직무입니다.",
        keywords=("언더라이팅", "uw", "인수심사", "보험심사", "위험심사", "건강고지", "계약심사", "보험"),
        skills=("위험 판단", "약관 이해", "자료 검토", "꼼꼼함", "의사결정 기준 수립"),
        preparation="보험 가입 심사 사례를 찾아 어떤 위험 요인이 인수 조건에 영향을 주는지 정리하세요.",
    ),
    FinanceJob(
        id="insurance_claims",
        title="보험 보상/손해사정",
        summary="사고나 질병 발생 시 약관과 사실관계를 확인해 보험금 지급 여부와 금액을 판단하는 직무입니다.",
        keywords=("보상", "손해사정", "보험금", "지급심사", "사고", "질병", "약관", "자동차보험", "장기보험"),
        skills=("약관 해석", "사실관계 확인", "고객 응대", "문서 검토", "분쟁 예방"),
        preparation="자동차보험이나 실손보험 보상 사례를 읽고 사고 접수부터 지급 판단까지 흐름을 정리하세요.",
    ),
    FinanceJob(
        id="insurance_asset_management",
        title="보험사 자산운용/ALM",
        summary="보험사의 장기 부채와 지급 여력을 고려해 채권, 대체투자 등 자산을 운용하는 직무입니다.",
        keywords=("보험", "자산운용", "alm", "채권", "대체투자", "금리", "듀레이션", "지급여력", "운용"),
        skills=("채권 이해", "금리 분석", "ALM 기초", "리스크 관리", "투자 분석"),
        preparation="보험사가 왜 장기 채권과 ALM을 중요하게 보는지 정리하고 금리 변화의 영향을 공부하세요.",
    ),
    FinanceJob(
        id="insurance_digital_service",
        title="보험 디지털 서비스 기획",
        summary="보험 가입, 청구, 헬스케어, 고객관리 경험을 모바일과 디지털 채널에서 개선하는 직무입니다.",
        keywords=("보험", "디지털", "앱", "모바일", "청구", "헬스케어", "서비스 기획", "ux", "고객경험"),
        skills=("서비스 기획", "보험 프로세스 이해", "UX 개선", "데이터 기반 문제정의", "프로젝트 관리"),
        preparation="보험 앱의 가입·청구 흐름을 직접 써보고 불편한 지점을 개선안 형태로 정리하세요.",
    ),
)

FINANCE_WORDS = (
    "금융",
    "은행",
    "증권",
    "보험",
    "투자",
    "자산",
    "대출",
    "여신",
    "신용",
    "리스크",
    "핀테크",
    "주식",
    "경제",
    "펀드",
    "카드",
    "가맹점",
    "결제",
    "보험금",
    "계리",
    "언더라이팅",
    "손해사정",
    "ib",
    "트레이딩",
    "채권",
    "파생",
    "ipo",
    "m&a",
)
PROFILE_HINTS = (
    "전공",
    "학과",
    "관심",
    "경험",
    "프로젝트",
    "인턴",
    "역량",
    "자격증",
    "sql",
    "python",
    "파이썬",
    "엑셀",
    "상담",
    "분석",
    "기획",
)

EXAMPLE_PROFILE = (
    "경제학과이고 증권사 IB, 카드 데이터 마케팅, 보험 상품개발 중에서 고민하고 있습니다. "
    "SQL과 Python을 공부했고 기업 재무제표 분석과 고객 소비 데이터 분석 프로젝트를 해봤습니다. "
    "숫자로 문제를 찾고 보고서나 기획안으로 정리하는 업무를 선호합니다."
)

LINKAREER_RECRUIT_URL = "https://linkareer.com/list/recruit"
JASOSEOL_RECRUIT_URL = "https://jasoseol.com/recruit"
CATCH_RECRUIT_SEARCH_URL = "https://www.catch.co.kr/NCS/RecruitSearch"
SARAMIN_RECRUIT_SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}
OPENAI_JOB_MODEL = os.getenv("OPENAI_JOB_MODEL", "gpt-4.1-mini")
FINANCE_COMPANY_HINTS = (
    "은행",
    "증권",
    "카드",
    "보험",
    "캐피탈",
    "투자",
    "자산운용",
    "저축은행",
    "신협",
    "새마을금고",
    "농협",
    "수협",
    "신한",
    "KB",
    "국민",
    "하나",
    "우리",
    "NH",
    "삼성생명",
    "삼성화재",
    "현대카드",
    "현대해상",
    "롯데카드",
    "롯데손해보험",
    "BC",
    "비씨",
    "동양생명",
    "한화생명",
    "교보생명",
    "미래에셋",
    "한국투자",
)

JOB_SOURCE_TERMS = {
    "finance_data_analyst": ("금융데이터", "금융 데이터", "데이터분석"),
    "retail_sales": ("금융영업", "증권영업", "고객상담"),
    "pb_wm": ("PB", "WM", "자산관리"),
    "financial_platform_pm": ("금융 서비스기획", "핀테크 기획", "결제 기획"),
    "risk_credit": ("리스크관리", "여신심사", "신용평가"),
    "research_investment": ("투자분석", "리서치", "기업분석"),
    "compliance_internal_control": ("컴플라이언스", "내부통제", "준법감시"),
    "investment_banking": ("IB", "기업금융", "IPO", "M&A", "인수금융", "PF"),
    "sales_trading": ("트레이딩", "S&T", "채권", "파생", "운용", "딜링"),
    "institutional_sales": ("기관영업", "법인영업", "세일즈", "리서치"),
    "structured_products": ("ELS", "DLS", "구조화", "파생상품", "금융상품"),
    "card_product_planning": ("카드", "상품기획", "혜택", "제휴"),
    "card_marketing_crm": ("카드", "마케팅", "CRM", "캠페인", "데이터"),
    "card_credit_strategy": ("카드", "신용", "리스크", "한도", "연체"),
    "merchant_payment_partnership": ("가맹점", "결제", "PG", "간편결제", "제휴"),
    "insurance_product_actuary": ("보험", "상품개발", "계리", "손해율"),
    "insurance_underwriting": ("언더라이팅", "UW", "인수심사", "보험심사"),
    "insurance_claims": ("보상", "손해사정", "보험금", "지급심사"),
    "insurance_asset_management": ("보험", "자산운용", "ALM", "채권"),
    "insurance_digital_service": ("보험", "디지털", "서비스기획", "청구"),
}
JOB_CONTEXT_TERMS = {
    "finance_data_analyst": ("금융", "은행", "증권", "보험", "카드", "투자", "신용", "리스크", "자산", "결제", "여신"),
    "retail_sales": ("금융", "은행", "증권", "보험", "카드", "금융상품", "투자", "자산"),
    "pb_wm": ("PB", "WM", "자산관리", "투자", "증권", "은행", "포트폴리오", "재무설계"),
    "financial_platform_pm": ("금융", "핀테크", "은행", "카드", "보험", "증권", "결제", "대출"),
    "risk_credit": ("리스크", "신용", "여신", "대출", "카드", "금융", "은행", "연체"),
    "research_investment": ("리서치", "투자", "증권", "기업분석", "산업분석", "주식", "자산운용"),
    "compliance_internal_control": ("컴플라이언스", "준법", "내부통제", "금융", "은행", "증권", "보험", "카드"),
    "investment_banking": ("증권", "IB", "기업금융", "IPO", "M&A", "인수금융", "PF", "투자", "자산운용"),
    "sales_trading": ("증권", "트레이딩", "S&T", "채권", "파생", "딜링", "운용"),
    "institutional_sales": ("증권", "기관영업", "법인영업", "연기금", "운용사"),
    "structured_products": ("증권", "ELS", "DLS", "구조화", "파생상품", "금융상품"),
    "card_product_planning": ("카드", "신용카드", "체크카드", "혜택", "결제"),
    "card_marketing_crm": ("카드", "신용카드", "체크카드", "결제", "소비 데이터"),
    "card_credit_strategy": ("카드", "신용", "리스크", "한도", "연체", "부정사용"),
    "merchant_payment_partnership": ("가맹점", "결제", "PG", "간편결제", "페이", "카드"),
    "insurance_product_actuary": ("보험", "계리", "상품개발", "손해율", "보험료"),
    "insurance_underwriting": ("보험", "언더라이팅", "UW", "인수심사"),
    "insurance_claims": ("보험", "보상", "손해사정", "보험금", "지급심사"),
    "insurance_asset_management": ("보험", "자산운용", "ALM", "채권", "지급여력"),
    "insurance_digital_service": ("보험", "디지털", "청구", "헬스케어", "고객경험"),
}
JOB_POSTING_HINTS = (
    "채용",
    "공고",
    "모집",
    "지원",
    "신입",
    "인턴",
    "경력",
    "recruit",
    "career",
    "job",
    "jobs",
    "intern",
)
TRUSTED_JOB_DOMAINS = (
    "jasoseol.com",
    "linkareer.com",
    "catch.co.kr",
    "jobkorea.co.kr",
    "saramin.co.kr",
    "incruit.com",
    "wanted.co.kr",
    "superookie.com",
)


@dataclass(frozen=True)
class Posting:
    source: str
    company: str
    title: str
    url: str
    deadline: str = ""
    location: str = ""


class LinkareerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Posting] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._hrefs: list[str] = []
        self._cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "tr" and "data-activityid" in attr_map:
            self._in_row = True
            self._cells = []
            self._hrefs = []
        if self._in_row and tag == "td":
            self._in_cell = True
            self._cell_text = []
        if self._in_row and tag == "a" and attr_map.get("href"):
            self._hrefs.append(str(attr_map["href"]))

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            text = data.strip()
            if text:
                self._cell_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._in_row and tag == "td":
            self._in_cell = False
            self._cells.append(" ".join(self._cell_text))
        if self._in_row and tag == "tr":
            self._in_row = False
            if len(self._cells) >= 5:
                activity_url = next((href for href in self._hrefs if "/activity/" in href), self._hrefs[-1] if self._hrefs else "")
                self.rows.append(
                    Posting(
                        source="링커리어",
                        company=self._cells[0],
                        title=self._cells[1],
                        url=urljoin(LINKAREER_RECRUIT_URL, activity_url),
                        location=self._cells[3],
                        deadline=self._cells[4],
                    )
                )


class CatchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Posting] = []
        self._current_href = ""
        self._current_name = ""
        self._current_title = ""
        self._capture = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("href") and "/NCS/RecruitInfoDetails/" in str(attr_map["href"]):
            self._current_href = str(attr_map["href"])
            self._current_name = ""
            self._current_title = ""
        if self._current_href and tag == "p":
            class_name = str(attr_map.get("class") or "")
            if "name" in class_name or "subj" in class_name:
                self._capture = class_name
                self._text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            text = data.strip()
            if text:
                self._text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._capture:
            text = " ".join(self._text)
            if "name" in self._capture:
                self._current_name = text
            if "subj" in self._capture:
                self._current_title = text
            self._capture = ""
        if tag == "a" and self._current_href:
            if self._current_name and self._current_title:
                self.rows.append(
                    Posting(
                        source="캐치",
                        company=self._current_name,
                        title=self._current_title,
                        url=urljoin(CATCH_RECRUIT_SEARCH_URL, self._current_href),
                    )
                )
            self._current_href = ""
            self._current_name = ""
            self._current_title = ""

def recommend(profile_text: str) -> object:
    text = _normalize(profile_text)
    if _needs_more_input(text):
        return gr.update(value=_more_input_message(), visible=True)

    ranked = sorted(
        ((job, _score(job, text)) for job in JOBS),
        key=lambda item: (-item[1], _priority(item[0])),
    )[:3]
    return gr.update(value=_format_recommendations(ranked), visible=True)


def load_example() -> str:
    return EXAMPLE_PROFILE


def clear() -> tuple[str, object]:
    return "", gr.update(value="", visible=False)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _needs_more_input(text: str) -> bool:
    reasons = (
        len(text) < 20,
        not _contains_any(text, FINANCE_WORDS),
        not _contains_any(text, PROFILE_HINTS),
    )
    return sum(reasons) >= 2


def _score(job: FinanceJob, text: str) -> int:
    score = 0
    for keyword in job.keywords:
        if keyword in text:
            score += 3 if len(keyword) > 2 else 2

    if any(word in text for word in FINANCE_WORDS):
        score += 1
    if job.id in ("finance_data_analyst", "risk_credit", "research_investment") and any(
        word in text for word in ("데이터", "분석", "sql", "python", "통계")
    ):
        score += 2
    if job.id in ("retail_sales", "pb_wm") and any(word in text for word in ("고객", "상담", "소통", "영업")):
        score += 2
    if job.id == "financial_platform_pm" and any(word in text for word in ("기획", "서비스", "앱", "ux", "핀테크")):
        score += 2
    if job.id == "compliance_internal_control" and any(word in text for word in ("규정", "법", "준법", "감사")):
        score += 2
    if job.id in ("investment_banking", "sales_trading", "institutional_sales", "structured_products") and any(
        word in text for word in ("증권", "ib", "ipo", "트레이딩", "채권", "파생", "기관", "법인", "구조화")
    ):
        score += 3
    if job.id in ("card_product_planning", "card_marketing_crm", "card_credit_strategy", "merchant_payment_partnership") and any(
        word in text for word in ("카드", "결제", "가맹점", "혜택", "마케팅", "한도", "연체", "소비")
    ):
        score += 3
    if job.id in ("insurance_product_actuary", "insurance_underwriting", "insurance_claims", "insurance_asset_management", "insurance_digital_service") and any(
        word in text for word in ("보험", "계리", "언더라이팅", "보상", "손해사정", "보험금", "약관", "청구")
    ):
        score += 3
    return score


def _format_recommendations(ranked: list[tuple[FinanceJob, int]]) -> str:
    lines = [
        "현재 입력 기준으로는 다음 3개 직무가 가장 잘 맞을 가능성이 높습니다.",
        "",
    ]
    for index, (job, score) in enumerate(ranked, start=1):
        lines.extend(
            [
                f"### {index}. {job.title}",
                f"- 추천 이유: {job.summary} 입력 내용과 연결되는 신호가 {max(score, 1)}점으로 잡혔습니다.",
                f"- 필요한 역량: {', '.join(job.skills)}",
                f"- 준비 방향: {job.preparation}",
                f"- 관련 채용공고: {_job_posting_links(job)}",
                "",
            ]
        )
    lines.extend(
        [
            "### 마무리 조언",
            "가장 끌리는 직무 1개를 먼저 고르고, 그 직무와 연결되는 경험 1개를 프로젝트나 자소서 소재로 구체화해보세요.",
        ]
    )
    return "\n".join(lines)


def _job_posting_links(job: FinanceJob) -> str:
    postings = list(_matched_postings(job))
    if len(postings) < 3:
        seen_urls = {posting.url for posting in postings}
        for posting in _fetch_openai_job_postings(job.id, job.title, _posting_terms(job)):
            if posting.url not in seen_urls:
                seen_urls.add(posting.url)
                postings.append(posting)
            if len(postings) >= 3:
                break
    if not postings:
        return (
            "\n  - 현재 확인 가능한 개별 채용공고 중 정확히 매칭되는 공고를 찾지 못했습니다."
        )

    lines = []
    for posting in postings:
        meta = " / ".join(part for part in (posting.source, posting.company, posting.location, posting.deadline) if part)
        lines.append(f"  - [{posting.title}]({posting.url}) - {meta}")
    return "\n" + "\n".join(lines)


def _posting_terms(job: FinanceJob) -> tuple[str, ...]:
    return tuple(dict.fromkeys((job.title, *JOB_SOURCE_TERMS.get(job.id, ()), *job.keywords[:4])))


def _matched_postings(job: FinanceJob) -> list[Posting]:
    terms = _posting_terms(job)
    ranked: list[tuple[int, Posting]] = []
    for posting in _candidate_public_postings(job):
        score = _posting_score(posting, terms)
        if score >= 3 and _posting_has_finance_context(posting, job):
            ranked.append((score, posting))
    ranked.sort(key=lambda item: (-item[0], item[1].deadline or "9999"))
    return [posting for _, posting in ranked[:3]]


def _candidate_public_postings(job: FinanceJob) -> tuple[Posting, ...]:
    postings = list(_fetch_public_postings())
    queries = (job.title, *JOB_SOURCE_TERMS.get(job.id, ())[:2])
    for query in queries:
        postings.extend(_fetch_saramin_postings(query))
    if len(postings) < 8:
        for query in queries:
            postings.extend(_fetch_catch_postings(query))

    seen: set[tuple[str, str]] = set()
    unique: list[Posting] = []
    for posting in postings:
        key = (posting.title, posting.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(posting)
    return tuple(unique)


@lru_cache(maxsize=64)
def _fetch_openai_job_postings(job_id: str, job_title: str, terms: tuple[str, ...]) -> tuple[Posting, ...]:
    if not os.getenv("OPENAI_API_KEY"):
        return ()

    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=OPENAI_JOB_MODEL,
            include=["web_search_call.action.sources"],
            tools=[{"type": "web_search", "search_context_size": "medium"}],
            tool_choice={"type": "web_search"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "You find current Korean finance job postings for job seekers. "
                        "Return only direct, usable hiring notice URLs from official company career pages "
                        "or trusted Korean recruiting services. Never invent URLs. "
                        "If you cannot verify a real posting URL, return an empty postings array."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"직무: {job_title}\n"
                        f"검색 키워드: {', '.join(terms)}\n\n"
                        "현재 열려 있거나 최근 확인 가능한 한국 금융권 채용공고를 최대 3개 찾아주세요. "
                        "은행, 증권사, 카드사, 보험사, 캐피탈, 자산운용사 공고를 우선하고, "
                        "정확히 같은 직무가 없으면 같은 업권의 인턴/신입/채용연계형 공고 중 "
                        "가장 가까운 공고를 골라주세요. url은 실제 접속 가능한 채용공고 상세 페이지나 "
                        "공식 채용 안내 페이지여야 하며, 단순 검색 결과 페이지는 제외하세요."
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "finance_job_postings",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "postings": {
                                "type": "array",
                                "maxItems": 3,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "company": {"type": "string"},
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                        "source": {"type": "string"},
                                        "deadline": {"type": "string"},
                                    },
                                    "required": ["company", "title", "url", "source", "deadline"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["postings"],
                        "additionalProperties": False,
                    },
                }
            },
            max_tool_calls=4,
            max_output_tokens=1200,
            timeout=25,
        )
    except Exception:
        return ()

    try:
        payload = json.loads(response.output_text)
    except (AttributeError, json.JSONDecodeError, TypeError):
        return ()

    postings: list[Posting] = []
    seen_urls: set[str] = set()
    for item in payload.get("postings", []):
        title = str(item.get("title") or "").strip()
        url = _clean_openai_url(str(item.get("url") or "").strip())
        if not title or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        if not _url_looks_like_job_posting(url, title, job_title, terms):
            continue
        seen_urls.add(url)
        postings.append(
            Posting(
                source=str(item.get("source") or "OpenAI 웹검색").strip(),
                company=str(item.get("company") or "").strip(),
                title=title,
                url=url,
                deadline=str(item.get("deadline") or "").strip(),
            )
        )
    return tuple(postings[:3])


def _clean_openai_url(url: str) -> str:
    return url.replace("?utm_source=openai", "").replace("&utm_source=openai", "")


def _url_looks_like_job_posting(url: str, title: str, job_title: str, terms: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    title_text = title.lower()
    url_text = f"{host} {path} {title_text}"
    if not any(hint in url_text for hint in JOB_POSTING_HINTS):
        return False

    try:
        request = Request(url, headers=REQUEST_HEADERS)
        response = urlopen(request, timeout=6)
        content = response.read(120_000).decode("utf-8", "ignore").lower()
    except Exception:
        return False

    if not (200 <= getattr(response, "status", 0) < 400):
        return False

    if any(domain in host for domain in TRUSTED_JOB_DOMAINS):
        return True

    evidence = f"{url_text} {content}"
    relevance_terms = tuple(dict.fromkeys((job_title, *terms, *FINANCE_WORDS)))
    return any(term.lower() in evidence for term in relevance_terms if len(term) >= 2) and any(
        hint in evidence for hint in JOB_POSTING_HINTS
    )


def _posting_score(posting: Posting, terms: tuple[str, ...]) -> int:
    text = f"{posting.company} {posting.title}".lower()
    score = 0
    for term in terms:
        normalized = term.lower().strip()
        if normalized == "ib" and not any(marker in text for marker in ("증권", "투자", "기업금융", "ipo", "m&a", "인수금융", "pf")):
            continue
        if normalized == "crm" and not any(marker in text for marker in ("카드", "결제", "금융", "신용")):
            continue
        if len(normalized) >= 2 and normalized in text:
            score += 3
    if any(hint.lower() in text for hint in FINANCE_COMPANY_HINTS):
        score += 2
    return score


def _posting_has_finance_context(posting: Posting, job: FinanceJob) -> bool:
    text = f"{posting.company} {posting.title}".lower()
    if any(hint.lower() in text for hint in FINANCE_COMPANY_HINTS):
        return True
    context_terms = JOB_CONTEXT_TERMS.get(job.id, (*FINANCE_WORDS, *job.keywords))
    return any(term.lower() in text for term in context_terms if len(term) >= 2)


@lru_cache(maxsize=1)
def _fetch_public_postings() -> tuple[Posting, ...]:
    postings: list[Posting] = []
    postings.extend(_fetch_linkareer_postings())
    postings.extend(_fetch_jasoseol_postings())
    seen: set[tuple[str, str]] = set()
    unique: list[Posting] = []
    for posting in postings:
        key = (posting.title, posting.url)
        if key not in seen:
            seen.add(key)
            unique.append(posting)
    return tuple(unique)


def _fetch_linkareer_postings() -> list[Posting]:
    try:
        request = Request(LINKAREER_RECRUIT_URL, headers=REQUEST_HEADERS)
        html = urlopen(request, timeout=4).read().decode("utf-8", "ignore")
    except Exception:
        return []
    parser = LinkareerParser()
    parser.feed(html)
    return parser.rows


def _fetch_jasoseol_postings() -> list[Posting]:
    try:
        request = Request(JASOSEOL_RECRUIT_URL, headers=REQUEST_HEADERS)
        html = urlopen(request, timeout=4).read().decode("utf-8", "ignore")
    except Exception:
        return []
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not match:
        return []
    try:
        data = json.loads(html_lib.unescape(match.group(1)))
    except json.JSONDecodeError:
        return []

    postings = []
    for item in data.get("props", {}).get("pageProps", {}).get("loadingAdvertises", []):
        tag = str(item.get("tag") or "")
        company = _company_from_jasoseol_tag(tag)
        url = str(item.get("link_url") or JASOSEOL_RECRUIT_URL)
        if not company or not any(hint in company for hint in FINANCE_COMPANY_HINTS):
            continue
        deadline = str(item.get("end_time") or "")[:10]
        postings.append(
            Posting(
                source="자소설닷컴",
                company=company,
                title=f"{company} 채용공고",
                url=url,
                deadline=deadline,
            )
        )
    return postings


@lru_cache(maxsize=48)
def _fetch_catch_postings(query: str) -> tuple[Posting, ...]:
    try:
        url = f"{CATCH_RECRUIT_SEARCH_URL}?SearchText={quote(query)}"
        request = Request(url, headers=REQUEST_HEADERS)
        html = urlopen(request, timeout=5).read().decode("utf-8", "ignore")
    except Exception:
        return ()
    parser = CatchParser()
    parser.feed(html)
    return tuple(parser.rows)


@lru_cache(maxsize=48)
def _fetch_saramin_postings(query: str) -> tuple[Posting, ...]:
    try:
        url = f"{SARAMIN_RECRUIT_SEARCH_URL}?searchword={quote(query)}"
        request = Request(url, headers=REQUEST_HEADERS)
        html = urlopen(request, timeout=5).read().decode("utf-8", "ignore")
    except Exception:
        return ()

    postings: list[Posting] = []
    blocks = re.split(r'<div class="item_recruit"', html)[1:21]
    for block in blocks:
        title_match = re.search(r'<h2 class="job_tit">.*?<a[^>]+title="([^"]+)"[^>]+href="([^"]+)"', block, re.S)
        company_match = re.search(r'<strong class="corp_name">.*?<a[^>]*>(.*?)</a>', block, re.S)
        deadline_match = re.search(r'<span class="date">(.*?)</span>', block, re.S)
        if not title_match or not company_match:
            continue
        title = _clean_html_text(title_match.group(1))
        company = _clean_html_text(company_match.group(1))
        href = html_lib.unescape(title_match.group(2))
        rec_idx_match = re.search(r"rec_idx=(\d+)", href)
        posting_url = (
            f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx_match.group(1)}"
            if rec_idx_match
            else urljoin(SARAMIN_RECRUIT_SEARCH_URL, href)
        )
        deadline = _clean_html_text(deadline_match.group(1)) if deadline_match else ""
        postings.append(
            Posting(
                source="사람인",
                company=company,
                title=title,
                url=posting_url,
                deadline=deadline,
            )
        )
    return tuple(postings)


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<.*?>", " ", html_lib.unescape(value))
    return re.sub(r"\s+", " ", text).strip()


def _company_from_jasoseol_tag(tag: str) -> str:
    parts = [part for part in tag.split("_") if part]
    if len(parts) >= 2:
        return parts[1]
    return ""


def _more_input_message() -> str:
    return (
        "아직 추천하기에는 정보가 조금 부족합니다.\n\n"
        "아래 내용 중 2~3가지를 한 문단으로 더 적어주세요.\n\n"
        "- 전공 또는 학습 배경\n"
        "- 관심 있는 금융 분야: 증권, 카드, 보험, 은행, 투자, 핀테크, 리스크 등\n"
        "- 해본 경험: 프로젝트, 인턴, 상담, 분석, 공모전 등\n"
        "- 보유 역량: SQL, Python, 엑셀, 회계, 커뮤니케이션 등\n"
        "- 선호하는 업무 방식: 분석, 영업, 기획, 심사, 보상, 문서 검토, 리서치 등"
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _priority(job: FinanceJob) -> int:
    return next(index for index, current in enumerate(JOBS) if current.id == job.id)


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');
:root{--blue:#3182f6;--blue-dark:#1b64da;--soft:#e8f3ff;--bg:#f4f7fb;--text:#191f28;--sub:#6b7684;--line:#e5e8eb}
.gradio-container{max-width:1100px!important;margin:auto!important;padding:24px!important;min-height:100vh;background:var(--bg);font-family:"Gowun Dodum","Noto Sans KR",sans-serif!important;color:var(--text)}
.shell{max-width:900px;margin:0 auto}.hero{text-align:center;padding:0 8px 36px}.hero .logo{display:inline-flex;width:60px;height:60px;align-items:center;justify-content:center;border-radius:20px;background:linear-gradient(145deg,#55a3ff,#1671e8);box-shadow:0 12px 24px rgba(49,130,246,.28);color:#fff;font-weight:800;font-size:20px;letter-spacing:0}
.hero h1{font-size:32px;margin:18px 0 8px;letter-spacing:0}.hero p{color:var(--sub);line-height:1.65;margin:0}.card{max-width:760px;margin:16px auto 0;padding:30px!important;border:1px solid #fff!important;border-radius:28px!important;background:#fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
.card .form,.card .block,.card label.container,.card .input-container,.card textarea{width:100%!important;max-width:none!important;min-width:0!important}
.card .auto-margin{margin:0!important}
textarea{min-height:230px!important;border-radius:16px!important;background:#f9fafb!important;border:1px solid var(--line)!important}textarea:focus{border-color:var(--blue)!important;box-shadow:0 0 0 4px rgba(49,130,246,.1)!important}
.primary3d,.secondary3d{width:100%!important;border:0!important;border-radius:16px!important;font-weight:700!important;min-height:48px!important}.primary3d{color:#fff!important;background:linear-gradient(#4593fa,#2378eb)!important;box-shadow:0 6px 0 #155dc1,0 11px 20px rgba(49,130,246,.2)!important}.secondary3d{color:var(--blue-dark)!important;background:linear-gradient(#fff,#edf5ff)!important;box-shadow:0 4px 0 #c5dcf8!important}
.result{max-width:640px;margin:18px auto 0;padding:18px!important;border-radius:24px!important;background:#fff!important;border:1px solid #fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
footer{display:none!important}@media(max-width:700px){.gradio-container{padding:12px!important}.card{padding:20px!important}.hero h1{font-size:27px}.shell{margin-top:0}textarea{min-height:190px!important}}
"""


with gr.Blocks(title="금융권 직무 추천 툴") as demo:
    with gr.Column(elem_classes=["shell"]):
        gr.HTML(
            """
            <section class="hero">
              <div class="logo">FIN</div>
              <h1>금융권 직무 추천</h1>
              <p>나의 관심 분야와 꼭 맞는 금융권 직무 3가지를 골라드려요.<br>입력은 한 문단으로 자유롭게 적어주세요.</p>
            </section>
            """
        )
        with gr.Column(elem_classes=["card"]):
            profile = gr.Textbox(
                label="나의 프로필",
                placeholder=(
                    "예: 경제학과이고 증권사 IB와 카드 데이터 마케팅에 관심이 있습니다. "
                    "SQL과 Python을 공부했고 기업 분석 프로젝트를 해봤습니다."
                ),
                lines=8,
            )
            with gr.Column():
                submit = gr.Button("직무 추천 받기", variant="primary", elem_classes=["primary3d"])
                example = gr.Button("예시 채우기", elem_classes=["secondary3d"])
                reset = gr.Button("비우기", elem_classes=["secondary3d"])
        output = gr.Markdown(visible=False, elem_classes=["result"])

    submit.click(recommend, inputs=profile, outputs=output)
    profile.submit(recommend, inputs=profile, outputs=output)
    example.click(load_example, outputs=profile)
    reset.click(clear, outputs=[profile, output])


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7861"))
    demo.queue(default_concurrency_limit=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        css=CSS,
    )
