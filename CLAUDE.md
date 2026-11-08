# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 규칙 (반드시 지킬 것)

- `.env`의 키(`DATA_GO_KR_KEY`)는 절대 출력하거나 commit하지 않는다. 화면·로그·다른 파일·대화 어디에도 키 값이나 키가 들어간 요청 URL을 내보내지 않는다. `.env`는 열어 보거나 수정하지 않는다. 코드가 런타임에만 읽는다.
- `air.json` 형식은 바꾸지 않는다: 최상위 `source`, `fetchedAt`, `dataTime`, `stations`. `stations[]` 각 항목은 `sido`, `station`, `pm10`, `pm25`, `khaiGrade`. 선택 필드 `"sample": true`를 넣으면 화면에 ‘샘플 데이터(가상 값)’ 배지가 뜬다.
- 외부 의존성 없음: `fetch_air.py`는 Python 3 표준 라이브러리만 쓰고 pip 설치는 하지 않는다. `index.html`은 외부 라이브러리 없이 HTML·CSS·JS 한 파일이다.

## 명령

```bash
python3 fetch_air.py                           # API 호출 → air.json 생성
python3 -m http.server 8000 --bind 127.0.0.1   # http://localhost:8000
```

테스트·빌드·린트 도구는 없다. JS 문법은 `<script>` 내용을 뽑아 `node --check`로 점검한다.

## 구조

데이터 흐름: 에어코리아 `getCtprvnRltmMesureDnsty` API → `fetch_air.py` → `air.json` → `index.html`(브라우저가 fetch). `index.html`은 `air.json`에 정해진 필드만 읽으므로, 두 파일이 형식으로 묶여 있다.

- `fetch_air.py`
  - `serviceKey`는 `urlencode`로 한 번만 인코딩한다. 키에 `%`가 있으면 먼저 `unquote`한다(이중 인코딩 방지).
  - 먼저 `numOfRows=1`로 응답 구조와 필드명을 확인한 뒤 `numOfRows=1000`으로 전체를 받는다. `totalCount`가 1000을 넘으면 페이지를 넘긴다.
  - 오류 응답(HTTP 403, XML `returnAuthMsg`, JSON `resultCode`)은 `ERROR_KO`/`CODE_KO`로 한국어 안내를 한 뒤 종료한다.
  - 수집에 실패하면 기존 `air.json`을 덮어쓰지 않는다(임시 파일에 쓴 뒤 `os.replace`로 교체).
  - `'-'`, 빈 값, 숫자가 아닌 값은 `null`로 바꾼다.
- `index.html`
  - PM2.5 등급: 좋음 0–15, 보통 16–35, 나쁨 36–75, 매우나쁨 76 이상. 평균은 반올림해서 판정한다.
  - `null`은 ‘점검 중’으로 표시하고 평균에서 뺀다.
  - DOM에는 `textContent`로만 문자열을 넣는다.
- 시도 이름은 API 값을 그대로 쓴다. 현재 `전남광주`가 하나로 나와 시도는 16곳이다.
- 화면 하단의 출처(한국환경공단 에어코리아)와 ‘실시간 자료는 확정 전 자료로 바뀔 수 있습니다’ 문구는 남겨 둔다.
