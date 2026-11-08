#!/usr/bin/env python3
"""에어코리아 시도별 실시간 측정정보를 받아 air.json으로 저장합니다.

- Python 3 표준 라이브러리만 사용합니다.
- 인증키는 .env 의 DATA_GO_KR_KEY 에서 읽으며, 키 값과 요청 URL은 출력하지 않습니다.
"""
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
OUT_PATH = BASE_DIR / "air.json"
ENDPOINT = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
TIMEOUT = 30
KST = timezone(timedelta(hours=9))

ERROR_KO = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "등록되지 않은 인증키입니다. 키 값 또는 활용신청 승인 여부를 확인하세요.",
    "SERVICE_ACCESS_DENIED_ERROR": "서비스 접근이 거부되었습니다. 이 API의 활용신청이 승인되었는지 확인하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "일일 호출 한도를 초과했습니다. 내일 다시 시도하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR": "초당 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
    "DEADLINE_HAS_EXPIRED_ERROR": "활용 기간이 만료되었습니다.",
    "UNREGISTERED_IP_ERROR": "등록되지 않은 IP에서 호출했습니다.",
    "NO_OPENAPI_SERVICE_ERROR": "해당 오픈API 서비스가 없거나 폐기되었습니다.",
    "SERVICE_TIMEOUT_ERROR": "서비스 응답 시간이 초과되었습니다.",
    "HTTP_ERROR": "HTTP 오류가 발생했습니다.",
    "APPLICATION_ERROR": "제공기관 서비스 오류입니다.",
    "DB_ERROR": "제공기관 데이터베이스 오류입니다.",
    "NODATA_ERROR": "조회된 데이터가 없습니다.",
    "INVALID_REQUEST_PARAMETER_ERROR": "요청 파라미터가 잘못되었습니다.",
    "NO_MANDATORY_REQUEST_PARAMETERS_ERROR": "필수 요청 파라미터가 없습니다.",
    "UNKNOWN_ERROR": "알 수 없는 오류입니다.",
    "FORBIDDEN": "접근이 거부되었습니다(HTTP 403). 키가 아직 승인·동기화되지 않았거나 활용신청이 필요할 수 있습니다.",
}
CODE_KO = {
    "01": "APPLICATION_ERROR", "02": "DB_ERROR", "03": "NODATA_ERROR", "04": "HTTP_ERROR",
    "05": "SERVICE_TIMEOUT_ERROR", "10": "INVALID_REQUEST_PARAMETER_ERROR",
    "11": "NO_MANDATORY_REQUEST_PARAMETERS_ERROR", "12": "NO_OPENAPI_SERVICE_ERROR",
    "20": "SERVICE_ACCESS_DENIED_ERROR", "22": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
    "30": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "31": "DEADLINE_HAS_EXPIRED_ERROR",
    "32": "UNREGISTERED_IP_ERROR", "99": "UNKNOWN_ERROR",
}


class ApiError(Exception):
    pass


def load_key():
    if not ENV_PATH.exists():
        raise ApiError(".env 파일이 없습니다. DATA_GO_KR_KEY 를 설정하세요.")
    key = None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[7:].strip()
        if name == "DATA_GO_KR_KEY":
            key = value.strip().strip('"').strip("'")
    if not key:
        raise ApiError(".env 에 DATA_GO_KR_KEY 값이 없습니다.")
    if "%" in key:
        key = urllib.parse.unquote(key)
    return key


def explain(name, fallback=""):
    name = (name or "").strip()
    if name in CODE_KO:
        name = CODE_KO[name]
    msg = ERROR_KO.get(name.upper())
    return f"{name}: {msg}" if msg else (f"{name} {fallback}".strip() or "알 수 없는 오류")


def error_from_body(body):
    """오류 응답 본문(XML 또는 JSON)에서 오류 이름을 찾아 한국어로 설명."""
    for tag in ("returnAuthMsg", "errMsg", "resultMsg"):
        m = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", body)
        if m and m.group(1).strip() not in ("NORMAL SERVICE.", "NORMAL_CODE"):
            return explain(m.group(1))
    m = re.search(r"<returnReasonCode>\s*(\d+)\s*</returnReasonCode>", body)
    if m:
        return explain(m.group(1))
    try:
        data = json.loads(body)
        header = data.get("response", {}).get("header", {})
        if header:
            return explain(header.get("resultCode", ""), header.get("resultMsg", ""))
    except (ValueError, AttributeError):
        pass
    text = body.strip()
    if text.lower().startswith("forbidden"):
        return explain("FORBIDDEN")
    return None


def call(num_rows, page_no=1):
    query = urllib.parse.urlencode({
        "serviceKey": load_key(), "returnType": "json", "numOfRows": num_rows,
        "pageNo": page_no, "sidoName": "전국", "ver": "1.0",
    })
    req = urllib.request.Request(f"{ENDPOINT}?{query}", headers={"User-Agent": "air-now/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        reason = error_from_body(body) or (explain("FORBIDDEN") if e.code == 403 else "")
        raise ApiError(f"HTTP {e.code} 오류 — {reason or '응답 본문에 오류 이름이 없습니다.'}") from None
    except (socket.timeout, TimeoutError):
        raise ApiError(f"응답 시간 초과({TIMEOUT}초). 네트워크 상태를 확인하세요.") from None
    except urllib.error.URLError as e:
        raise ApiError(f"네트워크 오류: {type(e.reason).__name__}") from None

    try:
        data = json.loads(body)
    except ValueError:
        raise ApiError("JSON이 아닌 응답 — " + (error_from_body(body) or "응답 형식을 확인할 수 없습니다.")) from None

    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        raise ApiError("API 오류 — " + explain(header.get("resultCode", ""), header.get("resultMsg", "")))
    return data["response"]["body"]


def to_num(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f != f:  # NaN
        return None
    return int(f) if f.is_integer() else f


def main():
    # 1단계: 1건만 받아 실제 구조·필드명 확인
    probe = call(1)
    items = probe.get("items") or []
    total = int(probe.get("totalCount") or 0)
    if not items:
        raise ApiError("응답에 items가 없습니다.")
    fields = sorted(items[0].keys())
    print(f"[1단계] 응답 구조 확인: totalCount={total}")
    print(f"        필드: {', '.join(fields)}")
    required = {"sidoName", "stationName", "pm10Value", "pm25Value", "khaiGrade", "dataTime"}
    missing = required - set(fields)
    if missing:
        raise ApiError(f"예상한 필드가 없습니다: {', '.join(sorted(missing))}")

    # 2단계: 전체 수집
    rows, page = [], 1
    while True:
        body = call(1000, page)
        got = body.get("items") or []
        rows.extend(got)
        if not got or len(rows) >= total:
            break
        page += 1
    print(f"[2단계] 전체 수집: {len(rows)}건 ({page}페이지)")

    stations = [{
        "sido": (r.get("sidoName") or "").strip(),
        "station": (r.get("stationName") or "").strip(),
        "pm10": to_num(r.get("pm10Value")),
        "pm25": to_num(r.get("pm25Value")),
        "khaiGrade": to_num(r.get("khaiGrade")),
    } for r in rows]

    times = [r.get("dataTime") for r in rows if r.get("dataTime")]
    data_time = Counter(times).most_common(1)[0][0] if times else None

    out = {
        "source": "한국환경공단 에어코리아",
        "fetchedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "dataTime": data_time,
        "stations": stations,
    }
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, OUT_PATH)

    sidos = {s["sido"] for s in stations}
    nulls = sum(1 for s in stations if s["pm25"] is None)
    print(f"저장 완료: air.json — 측정소 {len(stations)}곳, 시도 {len(sidos)}곳, PM2.5 null {nulls}건, 측정 시각 {data_time}")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(f"[오류] {e}", file=sys.stderr)
        if OUT_PATH.exists():
            print("기존 air.json은 그대로 유지했습니다.", file=sys.stderr)
        sys.exit(1)
