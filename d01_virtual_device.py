# -*- coding: utf-8 -*-
"""
d01_virtual_device.py — 가상 IoT 디바이스 (온습도 실시간 측정·전송)

실제 하드웨어 없이 디바이스 수명주기 전체를 시연한다:
  1) 기동 시 register_device 로 자가 등록 (최초 state=승인대기)
  2) 주기적으로 온도·습도를 측정(시뮬레이션)해 push_sensor 로 전송
  3) 승인 전이면 서버가 거부 → 대기하며 재시도, 관리자 승인 후 자동으로 전송 시작
  4) 차단/주기제한 응답도 그대로 표시

환경변수:
  HIVE_AI_SERVER  기본 http://127.0.0.1:8600/
  VD_ID           디바이스 ID (기본 vdev01)
  VD_KEY          디바이스 키 (기본 vdev01-secret)
  VD_INTERVAL     측정·전송 주기 초 (기본 5)

실행: python d01_virtual_device.py
"""
import json
import math
import os
import random
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 콘솔/리다이렉트에서도 UTF-8 + 즉시 출력 보장
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

SERVER = os.environ.get('HIVE_AI_SERVER', 'http://127.0.0.1:8600/')
DEVICE_ID = os.environ.get('VD_ID', 'vdev01')
DEVICE_KEY = os.environ.get('VD_KEY', 'vdev01-secret')
INTERVAL = max(int(os.environ.get('VD_INTERVAL', '5')), 1)


def call(func: str, **params) -> dict:
    """서버 func 호출 → {status, data}. 통신 실패도 error 응답으로 정규화."""
    params['func'] = func
    body = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(SERVER, data=body, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except ValueError:
            return {'status': 'error', 'data': 'HTTP %d' % e.code}
    except (urllib.error.URLError, OSError) as e:
        return {'status': 'error', 'data': '서버 연결 실패: %s' % e}


def measure() -> dict:
    """온습도 측정 시뮬레이션: 1시간 주기 사인파 + 노이즈"""
    phase = (time.time() % 3600) / 3600 * 2 * math.pi
    return {
        'temperature': round(24.0 + 4.0 * math.sin(phase) + random.gauss(0, 0.4), 2),
        'humidity': round(55.0 + 12.0 * math.cos(phase) + random.gauss(0, 1.2), 2),
    }


_running = True


def _stop(signum, frame):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print('[%s] 가상 디바이스 기동: 서버 %s, 주기 %d초' % (DEVICE_ID, SERVER, INTERVAL), flush=True)
    r = call('register_device', device_id=DEVICE_ID, device_key=DEVICE_KEY,
             name='가상 온습도 센서', model='VirtualDHT-1')
    print('[%s] 등록: %s' % (DEVICE_ID, r.get('data')))

    while _running:
        data = measure()
        r = call('push_sensor', device_id=DEVICE_ID, device_key=DEVICE_KEY,
                 data=json.dumps(data))
        if r.get('status') == 'success':
            print('[%s] 전송 OK  temp=%.2fC humi=%.2f%%'
                  % (DEVICE_ID, data['temperature'], data['humidity']), flush=True)
        else:
            print('[%s] 전송 거부: %s' % (DEVICE_ID, r.get('data')))

        for _ in range(INTERVAL * 10):
            if not _running:
                break
            time.sleep(0.1)
    print('[%s] 종료' % DEVICE_ID, flush=True)


if __name__ == '__main__':
    main()
