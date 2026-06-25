from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "raw" / "certs.json"
YEAR = 2026

DATAQ_URL = "https://www.dataq.or.kr/www/accept/schedule.do"
KOFIA_PAGE_URL = "https://license.kofia.or.kr/examInfo/examYearly.do"
KOFIA_API_URL = (
    "https://license.kofia.or.kr/examInfo/ajax/examYearlyMstInfo.do"
)

SOURCE_URLS = {
    "금융투자협회 자격시험센터": KOFIA_PAGE_URL,
    "한국금융연수원": (
        "https://www.kbi.or.kr/platformWeb/Qual.do"
        "?cmd=openPage&pageName=qualTestScheduleList"
    ),
    "한국데이터산업진흥원": DATAQ_URL,
    "Q-Net": "https://www.q-net.or.kr/crf021.do?id=crf02101&scheType=03",
    "KAIT 자격검정": "https://www.ihd.or.kr/guidecert1.do",
    "대한상공회의소 자격평가사업단": (
        "https://license.korcham.net/indexLoad.html"
    ),
    "KPC 자격": (
        "https://license.kpc.or.kr/nasec/rceptexmncnfirm/selectExprschdul.do"
    ),
    "한국정보통신자격협회": "https://www.icqa.or.kr/cn/page/network",
}

CERTIFICATE_METADATA = [
    {
        "certificate_id": "invest_manager",
        "certificate_name": "투자자산운용사",
        "aliases": ["투운사"],
        "category": "금융",
        "related_jobs": ["증권", "자산운용", "PB", "WM"],
        "keywords": ["투자", "증권", "펀드", "자산운용", "포트폴리오"],
        "description": "집합투자재산과 투자일임재산을 운용하는 금융투자 전문 자격입니다.",
        "source_name": "금융투자협회 자격시험센터",
    },
    {
        "certificate_id": "financial_analyst",
        "certificate_name": "금융투자분석사",
        "aliases": ["금투분"],
        "category": "금융",
        "related_jobs": ["애널리스트", "리서치", "투자분석"],
        "keywords": ["기업분석", "산업분석", "주식", "리서치", "투자"],
        "description": "금융투자상품과 기업가치를 분석하는 직무와 관련된 자격입니다.",
        "source_name": "금융투자협회 자격시험센터",
    },
    {
        "certificate_id": "financial_risk_manager",
        "certificate_name": "재무위험관리사",
        "aliases": ["국내 FRM", "재무위험"],
        "category": "금융",
        "related_jobs": ["리스크관리", "신용위험", "시장위험"],
        "keywords": ["리스크", "위험관리", "신용", "재무", "시장위험"],
        "description": "금융기관의 시장·신용·운영 위험을 관리하는 직무와 관련된 자격입니다.",
        "source_name": "금융투자협회 자격시험센터",
    },
    {
        "certificate_id": "credit_analyst",
        "certificate_name": "신용분석사",
        "aliases": [],
        "category": "금융",
        "related_jobs": ["은행 여신", "기업신용", "재무분석"],
        "keywords": ["은행", "여신", "대출", "신용", "재무제표"],
        "description": "기업의 회계·재무 상태를 분석해 신용을 판단하는 자격입니다.",
        "source_name": "한국금융연수원",
    },
    {
        "certificate_id": "asset_manager_fp",
        "certificate_name": "자산관리사(FP)",
        "aliases": ["은행 FP", "FP"],
        "category": "금융",
        "related_jobs": ["은행", "PB", "WM", "금융영업"],
        "keywords": ["은행", "자산관리", "고객", "상담", "PB", "WM"],
        "description": "고객의 재무상태를 분석하고 종합자산관리 상담을 수행하는 자격입니다.",
        "source_name": "한국금융연수원",
    },
    {
        "certificate_id": "foreign_exchange",
        "certificate_name": "외환전문역",
        "aliases": ["외전역"],
        "category": "금융",
        "related_jobs": ["은행 외환", "국제금융", "무역금융"],
        "keywords": ["외환", "국제금융", "무역", "환율", "은행"],
        "description": "외환 거래와 외국환 법규 실무를 다루는 은행권 자격입니다.",
        "source_name": "한국금융연수원",
    },
    {
        "certificate_id": "bank_teller",
        "certificate_name": "은행텔러",
        "aliases": ["텔러"],
        "category": "금융",
        "related_jobs": ["은행 창구", "수신", "금융서비스"],
        "keywords": ["은행", "창구", "고객", "수신", "금융영업"],
        "description": "은행 창구 업무와 금융상품 상담의 기초 역량을 다루는 자격입니다.",
        "source_name": "한국금융연수원",
    },
    {
        "certificate_id": "financial_dt",
        "certificate_name": "KBI 금융DT 테스트",
        "aliases": ["금융DT", "KBI DT"],
        "category": "디지털",
        "related_jobs": ["디지털 금융", "핀테크", "은행 IT"],
        "keywords": ["핀테크", "디지털", "은행 IT", "데이터", "플랫폼"],
        "description": "금융의 디지털 전환과 데이터 활용 역량을 확인하는 평가입니다.",
        "source_name": "한국금융연수원",
    },
    {
        "certificate_id": "adsp",
        "certificate_name": "데이터분석 준전문가",
        "aliases": ["ADsP", "데이터분석준전문가"],
        "category": "데이터",
        "related_jobs": ["데이터 분석", "BI", "데이터 기획"],
        "keywords": ["데이터", "분석", "통계", "BI", "기획"],
        "description": "데이터 이해와 분석 기획·방법론의 기초 역량을 확인하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "adp",
        "certificate_name": "데이터분석 전문가",
        "aliases": ["ADP", "데이터분석전문가"],
        "category": "데이터",
        "related_jobs": ["데이터 사이언티스트", "고급 데이터 분석"],
        "keywords": ["데이터", "분석", "통계", "머신러닝", "사이언스"],
        "description": "데이터 분석 전 과정의 고급 전문 역량을 평가하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "sqld",
        "certificate_name": "SQL 개발자",
        "aliases": ["SQLD", "SQL 디벨로퍼"],
        "category": "데이터",
        "related_jobs": ["데이터 분석", "데이터 엔지니어", "DB 개발"],
        "keywords": ["SQL", "데이터", "DB", "데이터베이스", "분석"],
        "description": "데이터 모델과 SQL 활용 능력을 확인하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "sqlp",
        "certificate_name": "SQL 전문가",
        "aliases": ["SQLP"],
        "category": "데이터",
        "related_jobs": ["DBA", "데이터 아키텍트", "DB 성능"],
        "keywords": ["SQL", "DBA", "데이터베이스", "튜닝", "성능"],
        "description": "고급 SQL과 데이터베이스 성능 최적화 역량을 평가하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "bigdata_engineer",
        "certificate_name": "빅데이터분석기사",
        "aliases": ["빅분기"],
        "category": "데이터",
        "related_jobs": ["데이터 분석", "데이터 사이언스", "빅데이터"],
        "keywords": ["빅데이터", "데이터", "분석", "통계", "머신러닝"],
        "description": "빅데이터 분석 기획부터 결과 해석까지 평가하는 국가기술자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "dasp",
        "certificate_name": "데이터아키텍처 준전문가",
        "aliases": ["DAsP"],
        "category": "데이터",
        "related_jobs": ["데이터 모델러", "DB 설계", "데이터 엔지니어"],
        "keywords": ["데이터아키텍처", "모델링", "DB", "설계", "데이터"],
        "description": "데이터 요건 분석과 모델링의 기초 역량을 확인하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "dap",
        "certificate_name": "데이터아키텍처 전문가",
        "aliases": ["DAP"],
        "category": "데이터",
        "related_jobs": ["데이터 아키텍트", "데이터 모델러"],
        "keywords": ["데이터아키텍처", "모델링", "DB", "설계", "거버넌스"],
        "description": "전사 데이터 아키텍처와 모델링 전문 역량을 평가하는 자격입니다.",
        "source_name": "한국데이터산업진흥원",
    },
    {
        "certificate_id": "information_processing_engineer",
        "certificate_name": "정보처리기사",
        "aliases": ["정처기"],
        "category": "IT",
        "related_jobs": ["백엔드 개발", "시스템", "금융 IT"],
        "keywords": ["개발", "백엔드", "소프트웨어", "시스템", "IT"],
        "description": "소프트웨어 설계·개발·데이터베이스·정보시스템 역량을 다루는 국가기술자격입니다.",
        "source_name": "Q-Net",
    },
    {
        "certificate_id": "linux_master",
        "certificate_name": "리눅스마스터",
        "aliases": ["리마"],
        "category": "IT",
        "related_jobs": ["서버", "인프라", "클라우드"],
        "keywords": ["리눅스", "서버", "인프라", "클라우드", "시스템"],
        "description": "리눅스 기반 시스템의 운영과 관리 역량을 평가하는 자격입니다.",
        "source_name": "KAIT 자격검정",
    },
    {
        "certificate_id": "network_manager",
        "certificate_name": "네트워크관리사",
        "aliases": ["네관사"],
        "category": "IT",
        "related_jobs": ["네트워크", "인프라", "시스템 운영"],
        "keywords": ["네트워크", "인프라", "서버", "통신", "보안"],
        "description": "네트워크 구축과 유지관리 능력을 평가하는 자격입니다.",
        "source_name": "한국정보통신자격협회",
    },
    {
        "certificate_id": "computer_literacy",
        "certificate_name": "컴퓨터활용능력",
        "aliases": ["컴활"],
        "category": "사무·ERP",
        "related_jobs": ["사무", "경영지원", "데이터 처리"],
        "keywords": ["엑셀", "스프레드시트", "사무", "행정", "경영지원"],
        "description": "스프레드시트와 데이터베이스 활용 능력을 평가하는 국가기술자격입니다.",
        "source_name": "대한상공회의소 자격평가사업단",
    },
    {
        "certificate_id": "erp_manager",
        "certificate_name": "ERP정보관리사",
        "aliases": ["ERP"],
        "category": "사무·ERP",
        "related_jobs": ["회계", "인사", "생산", "물류"],
        "keywords": ["ERP", "회계", "인사", "생산", "물류"],
        "description": "기업의 회계·인사·생산·물류 ERP 활용 역량을 평가하는 자격입니다.",
        "source_name": "KPC 자격",
    },
]

DATAQ_NAME_MAP = {
    "빅데이터 분석기사": "bigdata_engineer",
    "데이터분석 전문가": "adp",
    "데이터분석 준전문가": "adsp",
    "SQL 전문가": "sqlp",
    "SQL 개발자": "sqld",
    "데이터아키텍처 전문가": "dap",
    "데이터아키텍처 준전문가": "dasp",
}

KOFIA_NAME_MAP = {
    "투자자산운용사": "invest_manager",
    "금융투자분석사": "financial_analyst",
    "재무위험관리사": "financial_risk_manager",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _single_date(value: str, year: int) -> str | None:
    value = re.sub(r"\([^)]*\)", "", value).strip()
    if not value or value == "-":
        return None
    match = re.search(r"(\d{1,2})\.(\d{1,2})", value)
    if not match:
        return None
    month, day = map(int, match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _date_range(value: str, year: int) -> tuple[str | None, str | None]:
    value = _clean(value)
    if not value or value == "-":
        return None, None
    parts = re.split(r"\s*[~～]\s*", value)
    if len(parts) != 2:
        parsed = _single_date(value, year)
        return parsed, parsed

    start_match = re.search(r"(\d{1,2})\.(\d{1,2})", parts[0])
    if not start_match:
        return None, None
    start_month, start_day = map(int, start_match.groups())

    end_full = re.search(r"(\d{1,2})\.(\d{1,2})", parts[1])
    if end_full:
        end_month, end_day = map(int, end_full.groups())
    else:
        end_day_match = re.search(r"(\d{1,2})", parts[1])
        if not end_day_match:
            return None, None
        end_month, end_day = start_month, int(end_day_match.group(1))

    return (
        f"{year:04d}-{start_month:02d}-{start_day:02d}",
        f"{year:04d}-{end_month:02d}-{end_day:02d}",
    )


def fetch_dataq_schedules() -> dict[str, list[dict[str, object]]]:
    response = requests.get(
        DATAQ_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.select_one("table.table_schdule_all")
    if table is None:
        raise RuntimeError("데이터자격시험 일정표를 찾지 못했습니다.")

    schedules: dict[str, list[dict[str, object]]] = {
        certificate_id: [] for certificate_id in DATAQ_NAME_MAP.values()
    }
    current_name = ""
    current_round = ""

    for row in table.select("tbody tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all("td", recursive=False)]
        if not cells:
            continue

        first = cells[0]
        matched_name = next(
            (name for name in DATAQ_NAME_MAP if first.startswith(name)),
            None,
        )
        if matched_name:
            current_name = matched_name
            current_round = ""
            cells = cells[1:]
            if not cells:
                continue

        if not current_name or len(cells) < 7:
            continue

        if len(cells) >= 8:
            round_name, phase = cells[0], cells[1]
            current_round = round_name
            receipt, exam_date, result_date = cells[2], cells[4], cells[6]
        else:
            round_name, phase = current_round, cells[0]
            receipt, exam_date, result_date = cells[1], cells[3], cells[5]

        if not round_name:
            continue
        application_start, application_end = _date_range(receipt, YEAR)
        phase_suffix = f" {phase}" if phase not in {"", "-"} else ""
        certificate_id = DATAQ_NAME_MAP[current_name]
        schedules[certificate_id].append(
            {
                "year": YEAR,
                "round": f"{round_name}{phase_suffix}",
                "application_start": application_start,
                "application_end": application_end,
                "exam_date": _single_date(exam_date, YEAR),
                "result_date": _single_date(result_date, YEAR),
            }
        )
    return schedules


def _compact_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value[:8]
    if not re.fullmatch(r"\d{8}", value):
        return None
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def fetch_kofia_schedules() -> dict[str, list[dict[str, object]]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Referer": KOFIA_PAGE_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    session.get(KOFIA_PAGE_URL, timeout=30).raise_for_status()
    response = session.post(
        KOFIA_API_URL,
        data={"rcptSttType": "ALL", "licenseCd": "ALL"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("examSchedList", [])
    schedules: dict[str, list[dict[str, object]]] = {
        certificate_id: [] for certificate_id in KOFIA_NAME_MAP.values()
    }
    for item in items:
        certificate_id = KOFIA_NAME_MAP.get(item.get("koreanExamNm"))
        if not certificate_id:
            continue
        schedules[certificate_id].append(
            {
                "year": YEAR,
                "round": f"제{item.get('timeCnt')}회",
                "application_start": _compact_date(item.get("receiptSrtDtTm")),
                "application_end": _compact_date(item.get("receiptEndDtTm")),
                "exam_date": _compact_date(item.get("examinationDt")),
                "result_date": _compact_date(item.get("successAnnDt")),
            }
        )
    return schedules


def build_payload() -> dict[str, object]:
    collected: dict[str, list[dict[str, object]]] = {}
    errors: list[str] = []

    for collector in (fetch_dataq_schedules, fetch_kofia_schedules):
        try:
            result = collector()
            for certificate_id, schedules in result.items():
                collected.setdefault(certificate_id, []).extend(schedules)
        except Exception as error:
            errors.append(f"{collector.__name__}: {error}")

    certificates = []
    for metadata in CERTIFICATE_METADATA:
        source_name = metadata["source_name"]
        certificates.append(
            {
                **metadata,
                "source_url": SOURCE_URLS[source_name],
                "exams": sorted(
                    collected.get(metadata["certificate_id"], []),
                    key=lambda item: (
                        item.get("exam_date") or "9999-12-31",
                        item.get("round") or "",
                    ),
                ),
            }
        )

    return {
        "schema_version": 1,
        "year": YEAR,
        "last_updated": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(
            timespec="seconds"
        ),
        "collection_errors": errors,
        "certificates": certificates,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    schedule_count = sum(
        len(certificate["exams"]) for certificate in payload["certificates"]
    )
    print(
        f"{len(payload['certificates'])}개 자격증, "
        f"{schedule_count}개 일정을 {OUTPUT_PATH}에 저장했습니다."
    )
    for error in payload["collection_errors"]:
        print(f"경고: {error}")


if __name__ == "__main__":
    main()
