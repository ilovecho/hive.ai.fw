# -*- coding: utf-8 -*-
"""
p03_ai_agent.py — Claude 분석 에이전트 데몬

agent_config(DB) 의 enabled 플래그를 매 사이클 확인하므로,
관리 화면(w01_agent.html)이나 agent_enable/agent_disable func 로
데몬 재시작 없이 활성/비활성을 제어할 수 있다.

동작:
  - 10초마다 깨어나 heartbeat 기록
  - enabled=1 이고 interval_sec 경과 시 → 수집 데이터를 Claude 로 분석,
    결과를 agent_result 에 저장 (p01_agent.run_analysis_and_store 공용)
  - 오류(키 미설정, 데이터 없음, API 오류 등)는 last_error 에 기록하고 루프 지속

필요: pip install anthropic + 환경변수 ANTHROPIC_API_KEY

실행: python p03_ai_agent.py
"""
import datetime
import os
import signal
import sys
import time

# Windows 콘솔/리다이렉트에서도 UTF-8 + 즉시 출력 보장
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inc.util_service import trace_log, now_str, HiveError
from p01_agent import cfg_get, cfg_set, run_analysis_and_store

TICK_SEC = 10

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def _interval_elapsed() -> bool:
    last = cfg_get('last_run')
    if not last:
        return True
    interval = max(int(cfg_get('interval_sec') or 300), 30)
    last_dt = datetime.datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
    return (datetime.datetime.now() - last_dt).total_seconds() >= interval


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print('Hive.AI.FW Claude 분석 에이전트 시작 (enabled=%s, interval=%ss, model=%s)'
          % (cfg_get('enabled'), cfg_get('interval_sec'), cfg_get('model')))

    while _running:
        cfg_set('heartbeat', now_str())

        if cfg_get('enabled') == '1' and _interval_elapsed():
            try:
                result = run_analysis_and_store()
                print('[%s] 분석 완료 (model=%s, in=%d, out=%d 토큰)'
                      % (now_str(), result['model'],
                         result['input_tokens'], result['output_tokens']))
            except HiveError as e:
                cfg_set('last_error', str(e))
                cfg_set('last_run', now_str())   # 오류도 주기 소모 (연속 재시도 방지)
                trace_log('[AGENT] %s' % e, force=True)
            except Exception as e:
                cfg_set('last_error', '내부 오류: %s' % type(e).__name__)
                cfg_set('last_run', now_str())
                trace_log('[AGENT] %s: %s' % (type(e).__name__, e), force=True)

        for _ in range(TICK_SEC * 10):
            if not _running:
                break
            time.sleep(0.1)

    cfg_set('heartbeat', '')
    print('에이전트를 종료합니다.', flush=True)


if __name__ == '__main__':
    main()
