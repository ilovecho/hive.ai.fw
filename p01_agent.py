# -*- coding: utf-8 -*-
"""
p01_agent.py — 서비스: Claude 분석 에이전트 관리 (활성/비활성/설정/결과)

에이전트 실행 자체는 p03_ai_agent.py 데몬이 담당하고,
이 서비스는 설정(agent_config 테이블)과 결과(agent_result 테이블)를 관리한다.
데몬은 설정을 DB 에서 읽으므로 화면에서 바꾸면 다음 사이클에 즉시 반영된다.

func: agent_status / agent_enable / agent_disable / agent_config
      / run_agent_now / list_agent_result
"""
import json

from inc.db_system import get_sql, set_sql, get_link
from inc.util_service import service, HiveError, get_param, get_int, now_str
from inc.ai_claude import analyze_recent, DEFAULT_MODEL

set_sql("""
CREATE TABLE IF NOT EXISTS agent_config (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
""")
set_sql("""
CREATE TABLE IF NOT EXISTS agent_result (
    oid           INTEGER PRIMARY KEY AUTOINCREMENT,
    model         TEXT,
    window_min    INTEGER,
    analysis      TEXT NOT NULL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    created       TEXT NOT NULL
)
""")

_DEFAULTS = {
    'enabled': '0',            # 에이전트 활성 여부 (0/1)
    'interval_sec': '300',     # 분석 실행 주기(초)
    'window_min': '60',        # 분석 대상 구간(분)
    'model': DEFAULT_MODEL,    # 사용할 Claude 모델
    'heartbeat': '',           # 데몬이 매 사이클 기록
    'last_run': '',            # 마지막 분석 실행 시각
    'last_error': '',          # 마지막 실행 오류 (성공 시 빈값)
}


def cfg_get(name: str) -> str:
    v = get_link("SELECT value FROM agent_config WHERE name = :name", {'name': name})
    return v if v is not None else _DEFAULTS.get(name, '')


def cfg_set(name: str, value: str) -> None:
    set_sql("INSERT INTO agent_config (name, value) VALUES (:name, :value) "
            "ON CONFLICT(name) DO UPDATE SET value = :value",
            {'name': name, 'value': str(value)})


def run_analysis_and_store() -> dict:
    """분석 1회 실행 + 결과 저장. 서비스(run_agent_now)와 데몬이 공용."""
    window = max(int(cfg_get('window_min') or 60), 1)
    result = analyze_recent(window_min=window, model=cfg_get('model') or None)
    set_sql("""INSERT INTO agent_result
               (model, window_min, analysis, input_tokens, output_tokens, created)
               VALUES (:model, :window, :analysis, :itok, :otok, :created)""",
            {'model': result['model'], 'window': window,
             'analysis': result['analysis'],
             'itok': result['input_tokens'], 'otok': result['output_tokens'],
             'created': now_str()})
    cfg_set('last_run', now_str())
    cfg_set('last_error', '')
    return result


# ============================================================
#  관리 func (보호 — X-HIVE-TOKEN 필요)
# ============================================================
@service('agent_status')
def _agent_status(p: dict) -> dict:
    return {
        'enabled': cfg_get('enabled') == '1',
        'interval_sec': int(cfg_get('interval_sec') or 300),
        'window_min': int(cfg_get('window_min') or 60),
        'model': cfg_get('model'),
        'heartbeat': cfg_get('heartbeat'),   # 비어 있으면 데몬 미기동
        'last_run': cfg_get('last_run'),
        'last_error': cfg_get('last_error'),
        'result_count': get_link("SELECT COUNT(*) FROM agent_result") or 0,
    }


@service('agent_enable')
def _agent_enable(p: dict) -> dict:
    cfg_set('enabled', '1')
    return {'enabled': True}


@service('agent_disable')
def _agent_disable(p: dict) -> dict:
    cfg_set('enabled', '0')
    return {'enabled': False}


@service('agent_config')
def _agent_config(p: dict) -> dict:
    """interval_sec / window_min / model 설정 변경 (보낸 항목만 반영)"""
    if p.get('interval_sec') is not None:
        cfg_set('interval_sec', max(get_int(p, 'interval_sec', 300), 30))
    if p.get('window_min') is not None:
        cfg_set('window_min', max(get_int(p, 'window_min', 60), 1))
    if p.get('model'):
        cfg_set('model', get_param(p, 'model', limit=60))
    return _agent_status(p)


@service('run_agent_now')
def _run_agent_now(p: dict) -> dict:
    """수동으로 즉시 1회 분석 실행 (데몬 없이도 동작 확인 가능)"""
    return run_analysis_and_store()


@service('list_agent_result')
def _list_agent_result(p: dict) -> dict:
    limit = min(max(get_int(p, 'limit', 10), 1), 100)
    rows = get_sql("""
        SELECT oid, model, window_min, analysis, input_tokens, output_tokens, created
        FROM agent_result ORDER BY oid DESC LIMIT %d
    """ % limit)
    return {'list': rows}
