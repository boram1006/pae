# 협력사 현황 취합 자동화

매일 반복되는 **알바 취합 파일 → 최종 완성 파일 반영** 업무를 자동화하는
로컬 데스크톱 앱입니다.

> **이 앱은 브라우저 웹앱이 아닙니다.**
> PySide6 기반 로컬 데스크톱 앱으로, 파일 업로드 없이
> 내 PC의 파일을 QFileDialog로 직접 선택합니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 키값 매칭 | 협력사 키값(기본: A열) 기준 VLOOKUP 스타일 매칭 |
| 날짜 필터 | 특정 독려일에 해당하는 행만 선택적으로 반영 |
| Feedback 검증 | 정답지 기반 rapidfuzz 유사도 + 규칙 기반 이상 탐지 |
| Feedback 수정 | 검증 탭에서 드롭다운으로 직접 수정, 전체 결과 탭에 즉시 반영 |
| Feedback 관리 | `config/feedback_master.json` 기반 마스터 목록 UI 관리 |
| 서식 보존 저장 | openpyxl로 원본 workbook 구조(필터·병합·숨김 등) 유지한 채 저장 |

---

## 설치

Python **3.10 이상** 권장.

```bash
pip install -r requirements.txt
```

---

## 실행

```bash
python app.py
```

앱은 로컬 데스크톱 창으로 열립니다. 브라우저가 열리지 않습니다.

---

## 테스트

```bash
pytest          # 간략 출력
pytest -v       # 상세 출력
```

현재 테스트 파일 4개 / 65개 테스트 전부 통과.

| 테스트 파일 | 내용 |
|---|---|
| `test_matcher.py` | 키값 매칭, 날짜 필터, Feedback 필드, parse_date |
| `test_validator.py` | 검증 상태 분류, validate_all, 탭 필터 기준 |
| `test_feedback_manager.py` | JSON 로드/저장, active 필터, 미등록 값 탐지 |
| `test_feedback_sync.py` | 드롭다운 변경 → 전체 결과 탭 즉시 동기화 (offscreen Qt) |

---

## 화면 구성 (3탭)

### 탭 1 — 취합 설정

설정을 마치고 **취합 실행** 버튼을 누르면 백그라운드 스레드로 매칭과 검증이 실행됩니다.

| 섹션 | 설명 |
|---|---|
| 파일 선택 | 최종 완성 파일 / 알바 취합 파일 / 정답지 파일(선택) |
| 시트 선택 | 각 파일의 시트를 콤보박스로 선택 |
| 숨김 컬럼/행 안내 | 선택한 시트의 숨김 열·행 목록 자동 감지 후 표시 |
| 컬럼 매핑 설정 | 키값·독려여부 등 컬럼 문자를 화면에서 직접 수정 |
| 정답지 컬럼 설정 | 정답지 파일 선택 시에만 표시 |
| 업데이트 기준 날짜 | 특정 독려일만 반영하는 날짜 필터 옵션 |
| 취합 실행 버튼 | 매칭 + 검증 실행 |

### 탭 2 — 결과 확인

| 섹션 | 설명 |
|---|---|
| 요약 카드 | 전체 키 수, 매칭 성공/미매칭/날짜 필터 제외, 검증 결과 통계 |
| 날짜 필터 정보 | 필터 기준 날짜, 통과 건수, 제외 건수 표시 |
| 검증 디버그 정보 | 정답지 사용 여부, 기준 데이터 수, 상태별 건수 |
| 매칭 성공 탭 | 키값이 양쪽 파일에서 일치한 행 |
| 미매칭 탭 | 최종 파일에는 있지만 알바 파일에 없는 키 |
| 중복 키 탭 | 알바 파일에서 같은 키가 2회 이상 등장한 경우 (첫 번째 값 사용) |
| 알바만 존재 탭 | 알바 파일에는 있지만 최종 파일에 없는 키 |
| 날짜 필터 제외 탭 | 키는 매칭됐으나 독려일이 선택 날짜와 다른 행 |
| Feedback 확인 필요 탭 | 누락 의심·확인 필요·상세내용 부족·미검증 행, 드롭다운 수정 가능 |
| 전체 결과 탭 | 모든 행 + 최종 Feedback + 수정됨 컬럼 |
| 완성본 엑셀 저장 버튼 | QFileDialog로 저장 위치·파일명 선택 |

### 탭 3 — Feedback 관리

Feedback 드롭다운에 표시할 값 목록을 관리합니다.

- 마스터 목록 조회·라벨 수정·활성/비활성 전환·신규 추가
- **삭제 없음** — 비활성화(active=false)로만 처리해 과거 데이터 보존
- 취합 실행 후 파일에서 발견된 미등록 Feedback 값 자동 표시
- **저장(JSON)** 버튼으로 `config/feedback_master.json`에 반영

---

## 컬럼 매핑 기본값

| 항목 | 기본 컬럼 |
|---|---|
| 키값 | A |
| 독려여부 | CR |
| 독려방식 | CS |
| 독려일 | CT |
| 협력사 Feedback | CU |
| 상세내용(필요시) | CV |
| 견적회신여부 | CW |
| 회신일 | CX |

파일마다 컬럼 위치가 다를 수 있어 **취합 설정 탭에서 직접 수정 가능**합니다.

---

## 날짜 필터

취합 설정 탭의 **업데이트 기준 날짜** 섹션에서 설정합니다.

- 체크박스 OFF(기본): 날짜 관계없이 전체 매칭 데이터를 최종 파일에 반영합니다.
- 체크박스 ON: 알바 파일의 **독려일 컬럼**이 선택한 날짜와 일치하는 행만 반영합니다.

아래 날짜 형식을 모두 인식합니다.

```
2026-05-23    2026.05.23    2026/05/23
5/23          05/23
Excel 날짜 타입 (datetime / date)
```

연도 없는 형식(`5/23`)은 현재 연도로 해석합니다.

날짜가 일치하지 않는 행은 **날짜 필터 제외 탭**에서 별도 확인할 수 있으며,
최종 파일에는 반영되지 않습니다.

---

## Feedback 값 관리 — original / final

| 필드 | 설명 |
|---|---|
| `original_feedback` | 알바 파일에서 읽어 온 원래 값. 변경되지 않음. |
| `final_feedback` | 최종 엑셀에 저장될 값. 초기값은 original과 동일. |
| `feedback_changed` | 사용자가 수정해 둘이 달라지면 True. |

**Feedback 확인 필요 탭**에서 드롭다운으로 값을 바꾸면

1. `MatchedRow.final_feedback` 가 즉시 업데이트됩니다.
2. **전체 결과 탭**의 "최종 Feedback" 및 "수정됨" 컬럼이 즉시 갱신됩니다.
3. **완성본 저장** 시 `final_feedback` 이 협력사 Feedback 컬럼에 기록됩니다.
4. 원본 알바 파일은 수정되지 않습니다.

드롭다운 선택지는 `config/feedback_master.json`의 active 항목 +
파일에서 발견된 값으로 구성됩니다.

---

## Feedback 마스터 (`config/feedback_master.json`)

```json
{
  "version": 1,
  "items": [
    {
      "id": "CALL_DONE",
      "label": "통화완료",
      "active": true,
      "aliases": ["통화 완료", "연락 완료"],
      "sort_order": 10
    }
  ]
}
```

- `active: false` 로 설정하면 드롭다운에서 숨겨지지만 데이터는 보존됩니다.
- `aliases` 는 파일에서 발견된 값이 마스터에 있는지 판단할 때 사용됩니다.
- UI의 **저장(JSON)** 버튼으로만 파일에 반영됩니다.
- 앱 실행 중 JSON 파일을 직접 편집해도 재실행 전까지는 반영되지 않습니다.

---

## 숨김 열 / 숨김 행 처리

- openpyxl로 읽기 때문에 **숨김 컬럼과 숨김 행도 데이터 처리 대상에 포함**됩니다.
- 앱은 숨김 상태를 변경하지 않으며, 원본 엑셀 구조를 유지합니다.
- 취합 설정 탭에서 파일·시트를 선택하면 숨김 컬럼·행 목록을 안내 영역에 표시합니다.

---

## 엑셀 저장 방식

- `pandas` 로 새 엑셀을 만들지 않습니다.
- `openpyxl` 로 **원본 workbook을 복사한 뒤 지정 셀 값만 수정**하여 저장합니다.
- 기존 필터, 서식, 열 너비, 병합 셀, 숨김 상태, 수식이 최대한 유지됩니다.
- 원본 최종 파일을 직접 덮어쓰지 않습니다.
- 기본 저장 파일명: `원본파일명_completed_YYYYMMDD_HHMM.xlsx`

---

## 검증 결과 안내

검증 결과는 **확정 판단이 아니라 담당자 확인 보조용**입니다.

| 상태 | 의미 |
|---|---|
| 정상 | 정답지 유사 사례와 Feedback이 일치 |
| 확인 필요 | 유사 사례는 있으나 Feedback이 다름 |
| 누락 의심 | 상세내용은 있는데 Feedback이 비어 있음 |
| 상세내용 부족 | Feedback은 있으나 상세내용이 너무 짧음 |
| 미입력 | 상세내용도 Feedback도 비어 있음 |
| 미검증 | 정답지 없음 또는 유사 사례를 찾기 어려움 |

정답지 파일 없이 실행하면 규칙 기반(누락 의심·미입력 등)만 적용되고
유사도 비교는 수행되지 않습니다.

---

## exe 빌드 (Windows)

> Windows PC에서 빌드해야 Windows용 `.exe` 가 생성됩니다.
> 현재 환경이 Linux라면 Linux 바이너리가 생성됩니다.

### 기본 빌드

```bash
pyinstaller --onefile --windowed app.py
```

### 주의: config 폴더 포함

`config/feedback_master.json` 은 런타임에 읽고 쓰는 파일입니다.
`--onefile` 빌드 시 반드시 `--add-data` 로 포함해야 합니다.

**Windows:**
```bash
pyinstaller --onefile --windowed ^
  --add-data "config;config" ^
  app.py
```

**macOS / Linux:**
```bash
pyinstaller --onefile --windowed \
  --add-data "config:config" \
  app.py
```

빌드 후 `dist/app.exe` (또는 `dist/app`) 가 생성됩니다.

> `--onefile` 빌드에서 `feedback_master.json` 경로는 `sys._MEIPASS` 기반으로
> 자동 해결되도록 `app.py` 내 `_FEEDBACK_MASTER_PATH` 가 설정되어 있습니다.
> 단, JSON 저장(쓰기)은 실행 파일 옆 `config/` 디렉터리에 별도로 이루어집니다.

---

## 프로젝트 구조

```
partner-status-automation/
├── app.py                      # PySide6 메인 UI (3탭 구조)
├── requirements.txt
├── README.md
├── config/
│   └── feedback_master.json    # Feedback 마스터 (UI에서 관리)
├── src/
│   ├── utils.py                # ColumnConfig, parse_date, 공통 유틸
│   ├── excel_io.py             # openpyxl 읽기/쓰기, 숨김 감지
│   ├── matcher.py              # 키값 매칭, 날짜 필터, Feedback 필드
│   ├── validator.py            # Feedback 검증 (rapidfuzz + 규칙 기반)
│   └── feedback_manager.py     # Feedback 마스터 JSON 로드·저장·관리
├── outputs/                    # 저장 결과 기본 위치
├── samples/                    # 샘플 데이터
└── tests/
    ├── test_matcher.py         # 매칭, 날짜 필터, parse_date
    ├── test_validator.py       # 검증 상태 분류
    ├── test_feedback_manager.py
    └── test_feedback_sync.py   # UI 동기화 (offscreen Qt)
```

---

## 의존성

```
PySide6>=6.6.0
openpyxl>=3.1.0
pandas>=2.0.0
rapidfuzz>=3.5.0
pytest>=7.4.0
pyinstaller>=6.0.0
```
