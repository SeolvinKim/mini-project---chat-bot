# Tool 4 — 자격증 추천 및 시험 일정

취업준비 챗봇의 자격증 전용 기능입니다. 공통 Gradio UI, 프로필 온보딩, 공용 LLM·Chroma 설정과 Render 배포 파일은 `main` 브랜치에서 관리합니다.

## 담당 파일

```text
tools/spec_recommend.py
ingest/certs/build_certs_data.py
ingest/certs/index_certs.py
data/raw/certs.json
data/raw/language_tests.json
tests/test_spec_recommend.py
```

## 공통 Tool 계약

```python
from tools.spec_recommend import NAME, run

result = run(profile, "SQLD 올해 시험 일정 알려줘")
```

- `NAME = "자격증 추천"`
- `run(profile, user_input) -> str`
- 공통 `UserProfile`을 읽기만 하고 수정하지 않습니다.
- Chroma 컬렉션 이름은 `certs`입니다.

## 제공 기능

- 희망 직무 기반 자격증 최대 3개 추천
- 추가 추천 및 보유 자격증 제외
- SQLD, ADsP, 투운사, 정처기 등 약칭 인식
- TOEIC, TOEIC Speaking(토스), OPIc, TEPS, G-TELP
- TOEFL, IELTS, JLPT, JPT, SJPT, HSK, HSKK, TSC, FLEX
- DELF·DALF, Goethe-Zertifikat, DELE, TOPIK 등 어학시험 검색
- 최근 추천 항목과 후속 질문 연결
- `그 자격증`, `3`, `3번`, `세 번째`, 자격증명만 입력하는 짧은 후속 답변 처리
- 여러 추천 중 일정 선택을 요청한 상태를 사용자 세션별로 유지
- 올해 예정 시험과 종료 시험 구분
- 접수 기간, 시험일, 합격자 발표일 표시
- 공식 출처와 데이터 기준일 표시
- RAG 실패 시 키워드 기반 추천으로 폴백

## 공식 일정 데이터 갱신

`main` 브랜치와 병합한 환경에서 실행합니다.

```powershell
uv run python ingest/certs/build_certs_data.py
```

데이터자격시험과 금융투자협회의 공개 연간 일정을 수집하여 `data/raw/certs.json`에 저장합니다. 배포 앱에서는 실시간 크롤링하지 않습니다.

어학시험은 공식 시험기관별 일정 구조가 서로 다르고 일부 시험은 센터별 수시
시행이므로 `data/raw/language_tests.json`에서 별도로 관리합니다. 고정 일정이
없는 시험은 공식 접수 페이지와 `수시 시행` 안내를 제공합니다.

## Chroma 인덱싱

```powershell
uv run python ingest/certs/index_certs.py
```

공통 `core/vectorstore.py`를 이용해 `certs` 컬렉션에 자격증 설명을 적재합니다.

## 테스트

`main` 브랜치의 공통 개발 환경과 병합한 뒤 실행합니다.

```powershell
uv run pytest tests/test_spec_recommend.py -q
```
