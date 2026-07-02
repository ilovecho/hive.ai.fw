# -*- coding: utf-8 -*-
"""
p00_aiservice.py — Hive.AI.FW 라우터(진입점)  [Hive.fw s00_s2service.php 대응]

모든 요청은 POST / 한 곳으로 들어와 'func' 값으로 등록 서비스에 분기한다.

  요청  : POST /  (application/x-www-form-urlencoded 또는 application/json)
          func=<서비스명> + 서비스별 파라미터
  인증  : HIVE_AI_TOKEN 설정 시 X-HIVE-TOKEN 헤더 필수 (public func 제외)
  응답  : {"status": "success"|"error", "data": ...}
  헬스  : GET /health (무인증)
  화면  : GET /monitor (모니터링), GET /agent (에이전트 관리) — 토큰은 화면에서 입력

환경변수:
  HIVE_AI_HOST  기본 127.0.0.1   (외부 노출 시 반드시 토큰+방화벽)
  HIVE_AI_PORT  기본 8600
  HIVE_AI_TOKEN 공유 토큰 (미설정 + loopback 이 아니면 기동 거부)

실행: python p00_aiservice.py
"""
import hmac
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Windows 콘솔/리다이렉트에서도 UTF-8 + 즉시 출력 보장
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inc.util_service import SERVICES, PUBLIC_FUNCS, HiveError, trace_log

# 서비스 파일 로딩 — 여기 추가하면 자동 등록 (Hive.fw $serviceFiles 대응)
SERVICE_FILES = ['p01_sensor', 'p01_infer', 'p01_device', 'p01_agent']
for _mod in SERVICE_FILES:
    __import__(_mod)

# GET 으로 서빙하는 관리 화면 (Hive.fw w01_*.html 대응)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES = {
    '/monitor': 'w01_monitor.html',
    '/agent': 'w01_agent.html',
}

HOST = os.environ.get('HIVE_AI_HOST', '127.0.0.1')
PORT = int(os.environ.get('HIVE_AI_PORT', '8600'))
TOKEN = os.environ.get('HIVE_AI_TOKEN', '')


class Handler(BaseHTTPRequestHandler):
    server_version = 'HiveAI/0.1'

    # ---- 응답 규약: {status, data} ----
    def _reply(self, data, status='success', http_code=200):
        body = json.dumps({'status': status, 'data': data},
                          ensure_ascii=False).encode('utf-8')
        self.send_response(http_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            self._reply({'service': 'hive.ai.fw', 'funcs': sorted(SERVICES)})
        elif self.path in PAGES:
            self._serve_page(PAGES[self.path])
        else:
            self._reply('not found', 'error', 404)

    def _serve_page(self, filename: str):
        path = os.path.join(BASE_DIR, filename)
        try:
            with open(path, 'rb') as f:
                body = f.read()
        except OSError:
            self._reply('화면 파일이 없습니다: %s' % filename, 'error', 404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            payload = self._parse_body()
        except Exception:
            self._reply('요청 본문을 해석할 수 없습니다.', 'error', 400)
            return

        func = str(payload.get('func', ''))
        fn = SERVICES.get(func)
        if fn is None:
            self._reply('알 수 없는 func 입니다: %s' % func[:50], 'error', 400)
            return

        # 인증 게이트: 토큰 설정 시 public 외 모든 func 검증
        if TOKEN and func not in PUBLIC_FUNCS:
            sent = self.headers.get('X-HIVE-TOKEN', '')
            if not hmac.compare_digest(sent, TOKEN):
                self._reply('인증이 필요합니다.', 'error', 401)
                return

        try:
            self._reply(fn(payload))
        except HiveError as e:            # 안전 메시지는 그대로 노출
            self._reply(str(e), 'error', 400)
        except Exception as e:            # 그 외는 마스킹 (내부정보 비노출)
            trace_log('[ROUTER][%s] %s: %s' % (func, type(e).__name__, e), force=True)
            self._reply('서비스 처리 중 오류가 발생했습니다.', 'error', 500)

    # ---- 본문 파싱: urlencoded / JSON ----
    def _parse_body(self) -> dict:
        length = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(length) if length else b''
        ctype = (self.headers.get('Content-Type') or '').lower()
        if 'application/json' in ctype:
            data = json.loads(raw.decode('utf-8') or '{}')
            return data if isinstance(data, dict) else {}
        pairs = urllib.parse.parse_qsl(raw.decode('utf-8'), keep_blank_values=True)
        return dict(pairs)

    def log_message(self, fmt, *args):
        trace_log('[HTTP] ' + fmt % args)


def main():
    if not TOKEN and HOST not in ('127.0.0.1', 'localhost', '::1'):
        print('오류: 외부 바인딩(%s)에는 HIVE_AI_TOKEN 설정이 필수입니다.' % HOST, flush=True)
        sys.exit(1)

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print('Hive.AI.FW 서비스 시작: http://%s:%d/  (funcs: %s)'
          % (HOST, PORT, ', '.join(sorted(SERVICES))))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n종료합니다.', flush=True)
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
