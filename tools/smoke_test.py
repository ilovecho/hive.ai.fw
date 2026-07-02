# -*- coding: utf-8 -*-
"""
tools/smoke_test.py — Hive.AI.FW 자가 회귀 테스트

임시 포트(8699)·임시 DB 로 서버를 직접 띄워 전체 수명주기를 검증한다.
운영 DB(db/hive_ai.db)와 실행 중인 서버에 영향을 주지 않으며,
ANTHROPIC_API_KEY 를 제거한 환경으로 실행하므로 Claude 과금이 발생하지 않는다.

사용: python tools/smoke_test.py     (코드 수정 후 반드시 실행 — 전부 OK 여야 함)
종료코드: 0=전체 통과, 1=실패 있음
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get('SMOKE_PORT', '8699'))
TOKEN = 'smoke-test-token'
URL = 'http://127.0.0.1:%d/' % PORT

_checks = []


def call(func: str, token: str = None, **params) -> dict:
    """func 호출 → {status, data} (HTTP 오류 응답도 파싱해 반환)"""
    params['func'] = func
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(params).encode(),
                                 method='POST')
    if token:
        req.add_header('X-HIVE-TOKEN', token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


def get(path: str) -> int:
    """GET 경로 → HTTP 상태코드"""
    try:
        with urllib.request.urlopen(URL.rstrip('/') + path, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check(name: str, cond: bool, detail=None) -> None:
    _checks.append((name, bool(cond)))
    print(('OK   ' if cond else 'FAIL ') + name
          + ('' if cond else '  → %s' % (detail,)))


def wait_server(proc) -> bool:
    for _ in range(40):
        if proc.poll() is not None:
            return False
        try:
            if get('/health') == 200:
                return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def run_checks():
    # --- 디바이스 수명주기 ---
    r = call('register_device', device_id='smoke01', device_key='k1',
             name='스모크', model='SMK-1')
    check('디바이스 등록 → 승인대기', r['status'] == 'success' and r['data']['state'] == 0, r)

    r = call('push_sensor', device_id='smoke01', device_key='k1',
             data='{"temperature":25.0,"humidity":60.0}')
    check('승인 전 push 거부', r['status'] == 'error' and '승인 대기' in r['data'], r)

    r = call('approve_device', token=TOKEN, device_id='smoke01')
    check('승인', r['status'] == 'success' and r['data']['state'] == 1, r)

    r = call('push_sensor', device_id='smoke01', device_key='k1',
             data='{"temperature":25.0,"humidity":60.0}')
    check('승인 후 push 저장(2지표)', r['status'] == 'success' and r['data']['saved'] == 2, r)

    r = call('push_sensor', device_id='smoke01', device_key='WRONG', data='{"t":1}')
    check('잘못된 device_key 거부', r['status'] == 'error' and '인증 실패' in r['data'], r)

    call('config_device', token=TOKEN, device_id='smoke01', push_interval=60)
    r = call('push_sensor', device_id='smoke01', device_key='k1', data='{"temperature":25.1}')
    check('전송주기 제한 거부', r['status'] == 'error' and '주기 제한' in r['data'], r)
    call('config_device', token=TOKEN, device_id='smoke01', push_interval=0)

    call('block_device', token=TOKEN, device_id='smoke01')
    r = call('push_sensor', device_id='smoke01', device_key='k1', data='{"temperature":25.2}')
    check('차단 거부', r['status'] == 'error' and '차단' in r['data'], r)
    call('approve_device', token=TOKEN, device_id='smoke01')

    # --- 수집·조회·추론 ---
    call('push_sensor', device_id='smoke01', device_key='k1', data='{"temperature":25.05}')
    call('push_sensor', device_id='smoke01', device_key='k1', data='{"temperature":99.9}')

    r = call('latest_sensor', token=TOKEN)
    check('latest_sensor(2지표)', r['status'] == 'success' and len(r['data']['list']) == 2, r)

    r = call('list_sensor', token=TOKEN, device_id='smoke01', metric='temperature')
    check('list_sensor 필터', r['status'] == 'success' and len(r['data']['list']) >= 3, r)

    r = call('infer_anomaly', token=TOKEN, device_id='smoke01',
             metric='temperature', window=10)
    check('infer_anomaly(99.9 이상값)', r['status'] == 'success'
          and r['data']['is_anomaly'] is True, r)

    # --- 인증 게이트 / 화면 ---
    r = call('list_sensor')   # 토큰 없이 보호 func
    check('보호 func 무토큰 거부(401)', r['status'] == 'error' and '인증' in str(r['data']), r)
    r = call('no_such_func', token=TOKEN)
    check('알 수 없는 func 거부(400)', r['status'] == 'error', r)
    check('GET /monitor = 200', get('/monitor') == 200)
    check('GET /agent = 200', get('/agent') == 200)

    # --- 에이전트 관리 (키 없는 환경 → 안전 오류 경로만) ---
    r = call('agent_status', token=TOKEN)
    check('agent_status', r['status'] == 'success' and 'enabled' in r['data'], r)
    r = call('agent_enable', token=TOKEN)
    check('agent_enable', r['status'] == 'success' and r['data']['enabled'] is True, r)
    call('agent_disable', token=TOKEN)
    r = call('run_agent_now', token=TOKEN)
    check('run_agent_now 안전 오류(키/패키지 없음)', r['status'] == 'error'
          and ('ANTHROPIC_API_KEY' in r['data'] or 'anthropic' in r['data']), r)


def main():
    tmp = tempfile.mkdtemp(prefix='hive_smoke_')
    env = dict(os.environ,
               HIVE_AI_PORT=str(PORT), HIVE_AI_TOKEN=TOKEN,
               HIVE_AI_DB=os.path.join(tmp, 'smoke.db'),
               PYTHONIOENCODING='utf-8')
    env.pop('ANTHROPIC_API_KEY', None)   # 실 API 호출(과금) 방지

    proc = subprocess.Popen([sys.executable, os.path.join(BASE, 'p00_aiservice.py')],
                            cwd=BASE, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        if not wait_server(proc):
            print('FAIL 테스트 서버 기동 실패 (포트 %d 충돌 여부 확인)' % PORT)
            sys.exit(1)
        run_checks()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in _checks if not ok]
    print('\n결과: %d/%d 통과' % (len(_checks) - len(failed), len(_checks)))
    if failed:
        print('실패 항목: ' + ', '.join(failed))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
