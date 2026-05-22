# 협력사 현황 취합 자동화

## 개요

이 앱은 **브라우저에서 실행되는 웹앱이 아니라 로컬 데스크톱 앱**입니다.
파일 업로드 방식이 아니라 **로컬 파일 선택 방식**으로 동작합니다.

매일 반복되는 "알바 취합 파일 → 최종 완성 파일 반영" 업무를 자동화합니다.

- 최종 파일과 알바 취합 파일을 **협력사 키값(기본: A열) 기준**으로 VLOOKUP 스타일로 매칭
- 지정된 컬럼(기본: CR~CX)의 값을 최종 파일에 채워 넣음
- 5월 정답지 기준으로 **협력사 Feedback 적정성 검증** (rapidfuzz 유사도)
- **openpyxl로 원본 workbook을 유지**하여 기존 필터·서식·병합·숨김 상태 보존
- **숨김 컬럼/숨김 행도 읽기 대상에 포함** (openpyxl 직접 사용)

---

## 설치

```bash
pip install -r requirements.txt
```

Python 3.10 이상 권장.

---

## 실행

```bash
python app.py
```

---

## 테스트

```bash
pytest
```

또는 상세 출력:

```bash
pytest -v
```

---

## exe 빌드 (Windows)

```bash
pyinstaller --onefile --windowed app.py
```

- `dist/app.exe` 가 생성됩니다.
- 추가 데이터 파일이 필요하면 `--add-data` 옵션을 사용하세요.

---

## 화면 구성

| 영역 | 설명 |
|---|---|
| 파일 선택 | QFileDialog로 로컬 .xlsx/.xlsm 파일 선택 |
| 시트 선택 | 콤보박스로 시트 선택, 기본값=첫 번째 시트 |
| 숨김 정보 | 선택한 시트의 숨김 컬럼/행 목록 안내 |
| 컬럼 매핑 | 키값·독려여부 등 컬럼 문자 직접 수정 가능 |
| 정답지 컬럼 설정 | 정답지 파일 선택 시 표시 |
| 취합 실행 | 백그라운드 스레드로 매칭 + 검증 수행 |
| 결과 요약 | 카드 형태로 주요 통계 표시 |
| 결과 탭 | 매칭 성공 / 미매칭 / 중복 / 알바만 / Feedback 확인 / 전체 |
| 완성본 저장 | QFileDialog로 저장 위치·파일명 선택 |

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

파일마다 컬럼 위치가 다를 수 있어 UI에서 직접 수정 가능합니다.

---

## 숨김 열 / 숨김 행 처리

- openpyxl로 파일을 읽기 때문에 **숨김 컬럼과 숨김 행도 데이터 처리 대상에 포함**됩니다.
- 앱은 숨김 상태를 변경하지 않으며, 원본 엑셀 구조를 최대한 유지합니다.

---

## 엑셀 저장 방식

- `pandas`로 새 엑셀을 만들지 않습니다.
- `openpyxl`로 **원본 workbook을 복사한 뒤 필요한 셀 값만 수정**하여 저장합니다.
- 기존 필터, 서식, 열 너비, 병합 셀, 숨김 상태, 수식이 최대한 유지됩니다.
- 저장 파일명 기본값: `원본파일명_completed_YYYYMMDD_HHMM.xlsx`

---

## 검증 결과 주의사항

검증 결과는 **확정 판단이 아니라 담당자 확인 보조용**입니다.
rapidfuzz 유사도 기반이므로 참고 자료로만 활용하세요.

---

## 프로젝트 구조

```
partner-status-automation/
├── app.py                  # PySide6 메인 UI
├── requirements.txt
├── README.md
├── src/
│   ├── utils.py            # ColumnConfig, 공통 유틸
│   ├── excel_io.py         # openpyxl 읽기/쓰기, 숨김 감지
│   ├── matcher.py          # 키값 매칭 로직
│   └── validator.py        # Feedback 검증 (rapidfuzz)
├── outputs/                # 저장 결과 기본 위치
├── samples/                # 샘플 데이터
└── tests/
    ├── test_matcher.py
    └── test_validator.py
```
