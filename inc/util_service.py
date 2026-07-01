# -*- coding: utf-8 -*-
"""
inc/util_service.py — 서비스 공통 유틸 (Hive.fw inc_util_service.php 대응)

- 서비스 레지스트리: @service('func명') 데코레이터로 등록 (Hive.fw $services[] 대응)
- HiveError: 클라이언트에 그대로 노출해도 안전한 예외 (그 외 예외는 마스킹)
- 입력 헬퍼: get_param / get_int / get_float
- 로깅: trace_log (HIVE_DEBUG=1 일 때만 출력)
"""
import datetime
import os
import sys

HIVE_DEBUG = os.environ.get('HIVE_DEBUG', '') in ('1', 'true', 'True')

# ============================================================
#  서비스 레지스트리
# ============================================================
SERVICES = {}          # func명 → 함수
PUBLIC_FUNCS = set()   # 토큰 검증 면제 func


def service(name: str, public: bool = False):
    """서비스 함수 등록 데코레이터.

    @service('list_sensor')
    def _list_sensor(p: dict) -> dict:
        return {'list': [...]}          # data 부분만 반환하면 라우터가 포장
    """
    def _wrap(fn):
        SERVICES[name] = fn
        if public:
            PUBLIC_FUNCS.add(name)
        return fn
    return _wrap


class HiveError(RuntimeError):
    """사용자에게 노출 가능한 안전 메시지 예외 (Hive.fw RuntimeException 대응)"""
    pass


# ============================================================
#  입력 헬퍼 — payload(dict) 에서 정규화 추출
# ============================================================
def get_param(payload: dict, key: str, default: str = '', limit: int = 200) -> str:
    v = payload.get(key, default)
    if v is None:
        return default
    return str(v).strip()[:limit]


def get_int(payload: dict, key: str, default: int = 0) -> int:
    try:
        return int(float(payload.get(key, default)))
    except (TypeError, ValueError):
        return default


def get_float(payload: dict, key: str, default: float = None):
    try:
        return float(payload.get(key))
    except (TypeError, ValueError):
        return default


# ============================================================
#  로깅 / 시각
# ============================================================
def now_str() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def trace_log(msg: str, force: bool = False) -> None:
    if HIVE_DEBUG or force:
        print('[%s] %s' % (now_str(), msg), file=sys.stderr, flush=True)
