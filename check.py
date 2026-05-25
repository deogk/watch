#!/usr/bin/env python3
"""
페이지의 특정 항목 상태 확인 + 디스코드 알림 (1회 실행용)
------------------------------------------------------------------
스케줄러(GitHub Actions 등)에서 주기적으로 호출되는 것을 전제로,
'한 번 확인하고 종료'하는 구조입니다.

상태를 세 가지로 구분합니다:
  - OPEN     : 항목이 열림(선택 가능)  -> 디스코드 알림
  - CLOSED   : 여전히 비활성(선택 불가) -> 로그만 남김
  - UNKNOWN  : 페이지 구조가 예상과 달라 판단 불가 -> 디스코드 경고
               (스크립트가 조용히 고장나서 알림을 놓치는 상황을 방지)

판정 방식:
  대상 항목의 체크박스는 비활성일 때
      <input name="..." type="checkbox" disabled="disabled">
  형태다. 비활성이면 disabled 속성이 있고, 열리면 사라진다.
  -> 이 체크박스의 disabled 유무를 1차 신호로 사용 (가장 견고함).
  -> 만약 그 체크박스를 못 찾으면 비활성 표시 텍스트로 보조 판정.

설정값(URL, 체크박스 이름, 표시 텍스트)은 환경변수로 넘길 수 있고,
없으면 아래 기본값을 사용합니다. 디스코드 웹훅 URL은 반드시
환경변수 WEBHOOK_URL 로 전달하세요. (코드에 직접 넣지 말 것)

필요 패키지:
    pip install requests beautifulsoup4
"""

import os
import sys
import requests
from bs4 import BeautifulSoup

# ---- 설정 (환경변수로 덮어쓸 수 있음) ----
TARGET_URL = os.environ.get("TARGET_URL", "https://icml.cc/Register/view-registration")
CHECKBOX_NAME = os.environ.get("TARGET_NAME", "Conference Sessions")
CLOSED_MARKER = os.environ.get("CLOSED_MARKER", "sold out").lower()
WEBHOOK = os.environ.get("WEBHOOK_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

OPEN = "OPEN"
CLOSED = "CLOSED"
UNKNOWN = "UNKNOWN"


def detect_status(html: str) -> str:
    """대상 항목이 선택 가능(OPEN)한지 판정한다."""
    soup = BeautifulSoup(html, "html.parser")

    # ---- 1차 신호: 대상 체크박스의 disabled 속성 ----
    box = soup.find("input", {"type": "checkbox", "name": CHECKBOX_NAME})
    if box is not None:
        return CLOSED if box.has_attr("disabled") else OPEN

    # ---- 체크박스를 못 찾음: 보조 신호(텍스트)로 판정 ----
    # 'choose sessions' ~ 'extras' 구간으로 범위를 좁혀,
    # 페이지 곳곳에 같은 단어가 있어도 속지 않도록 한다.
    low = soup.get_text(" ", strip=True).lower()
    start = low.find("choose sessions")
    if start == -1:
        return UNKNOWN
    end = low.find("extras", start)
    if end == -1:
        end = start + 400
    region = low[start:end]

    ci = region.find("conference")
    if ci == -1:
        return UNKNOWN

    # 대상 '자신의' 마커 영역(직전 항목 끝 ~ 대상 시작)만 검사
    ti = region.rfind("tutorials", 0, ci)
    gap = region[ti + len("tutorials"):ci] if ti != -1 else region[max(0, ci - 18):ci]
    return CLOSED if CLOSED_MARKER in gap else OPEN


def send_discord(message: str):
    if not WEBHOOK:
        print("경고: WEBHOOK_URL 이 설정되지 않았습니다.", file=sys.stderr)
        return
    resp = requests.post(WEBHOOK, json={"content": message}, timeout=30)
    resp.raise_for_status()
    print("디스코드 알림 전송 완료.")


def main():
    # 네트워크/HTTP 오류는 일부러 잡지 않는다.
    #  -> 실패 시 Actions 가 '실패'로 표시하고 기본적으로 메일 알림을 보내므로
    #     조용한 미감시 상태를 피할 수 있다.
    resp = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    status = detect_status(resp.text)

    if status == OPEN:
        print("대상 항목: 열림(OPEN) 감지!")
        send_discord(
            "@here 🎉 **확인 중이던 항목이 열렸을 수 있습니다!**\n"
            f"지금 바로 확인하세요 👉 {TARGET_URL}"
        )
    elif status == CLOSED:
        print("대상 항목: 여전히 비활성(CLOSED)")
    else:  # UNKNOWN
        print("대상 항목: 판단 불가(UNKNOWN) - 페이지 구조가 바뀌었을 수 있음", file=sys.stderr)
        send_discord(
            "⚠️ **감시 스크립트 주의**: 항목 상태를 판단하지 못했습니다.\n"
            f"페이지 구조가 바뀌었을 수 있으니 직접 확인하고, 필요하면 스크립트를 점검하세요 👉 {TARGET_URL}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
