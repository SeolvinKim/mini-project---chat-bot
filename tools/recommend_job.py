"""직무 추천 Tool — 오프라인 규칙 기반 금융권 직무 추천.

공통 계약:
- 외부 노출: NAME(str), run(profile, user_input) -> str 딱 두 개.
- profile은 core.schema.UserProfile(또는 dict). 읽기 전용 — 절대 수정 금지.
- run은 항상 사람이 읽는 문자열 하나를 반환. dict/None/예외를 노출하지 않는다.
- OPENAI_API_KEY 없이도 동작하며, 런타임 외부 HTTP 호출은 하지 않는다.

원본(app/finance_job_recommend.py)의 직무 데이터·점수 로직만 재사용하고,
크롤러/네트워크/Gradio 코드는 모두 제거했다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.schema import UserProfile

NAME = "직무 추천"

MAX_RECOMMENDATIONS = 3


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
    "금융", "은행", "증권", "보험", "투자", "자산", "대출", "여신", "신용", "리스크",
    "핀테크", "주식", "경제", "펀드", "카드", "가맹점", "결제", "보험금", "계리",
    "언더라이팅", "손해사정", "ib", "트레이딩", "채권", "파생", "ipo", "m&a",
)
PROFILE_HINTS = (
    "전공", "학과", "관심", "경험", "프로젝트", "인턴", "역량", "자격증",
    "sql", "python", "파이썬", "엑셀", "상담", "분석", "기획",
)


def _profile_value(profile: Any, field: str) -> Any:
    """UserProfile/dict 모두 안전하게 읽는다. profile은 절대 수정하지 않는다."""
    if isinstance(profile, dict):
        return profile.get(field, "")
    return getattr(profile, field, "")


def _normalize(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _profile_text(profile: Any, user_input: str) -> str:
    """프로필(직무·역량·경험·학력)과 사용자 입력을 하나의 검색 텍스트로 합친다."""
    parts = [
        _profile_value(profile, "target_job"),
        _profile_value(profile, "skills"),
        _profile_value(profile, "experiences"),
        _profile_value(profile, "education"),
        _profile_value(profile, "certs"),
        user_input,
    ]
    return _normalize(parts)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


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


def _priority(job: FinanceJob) -> int:
    return next(index for index, current in enumerate(JOBS) if current.id == job.id)


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


def _format_recommendations(ranked: list[tuple[FinanceJob, int]]) -> str:
    lines = [
        "현재 입력 기준으로는 다음 3개 금융권 직무가 가장 잘 맞을 가능성이 높습니다.",
        "",
    ]
    for index, (job, score) in enumerate(ranked, start=1):
        lines.extend(
            [
                f"### {index}. {job.title}",
                f"- 추천 이유: {job.summary} 입력 내용과 연결되는 신호가 {max(score, 1)}점으로 잡혔습니다.",
                f"- 필요한 역량: {', '.join(job.skills)}",
                f"- 준비 방향: {job.preparation}",
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


def run(profile: UserProfile, user_input: str) -> str:
    """프로필과 사용자 질문을 받아 상위 3개 금융권 직무 추천 문자열을 반환한다."""
    try:
        text = _profile_text(profile, str(user_input or ""))
        if _needs_more_input(text):
            return _more_input_message()

        ranked = sorted(
            ((job, _score(job, text)) for job in JOBS),
            key=lambda item: (-item[1], _priority(item[0])),
        )[:MAX_RECOMMENDATIONS]
        return _format_recommendations(ranked)
    except Exception:
        return (
            "직무를 추천하는 중 문제가 발생했어요. "
            "관심 금융 분야나 보유 역량을 한 문장으로 다시 적어주시겠어요?"
        )
