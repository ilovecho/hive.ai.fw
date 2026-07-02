# -*- coding: utf-8 -*-
"""
p01_sensor.py — 서비스: 센서 시계열 저장/조회  [Hive.fw s01_memo.php 패턴 대응]

func: push_sensor(디바이스 푸시, 공개+device_key 인증) / save_sensor / list_sensor / latest_sensor
테이블은 CREATE TABLE IF NOT EXISTS 로 자동 생성한다.
"""
import json

from inc.db_system import get_sql, set_sql
from inc.util_service import service, HiveError, get_param, get_int, get_float, now_str

_DDL = """
CREATE TABLE IF NOT EXISTS sensor_data (
    oid       INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT    NOT NULL,
    metric    TEXT    NOT NULL,
    value     REAL    NOT NULL,
    created   TEXT    NOT NULL
)
"""
_IDX = ('CREATE INDEX IF NOT EXISTS ix_sensor_dmc '
        'ON sensor_data(device_id, metric, created)')


def ensure_schema() -> None:
    set_sql(_DDL)
    set_sql(_IDX)


ensure_schema()


@service('push_sensor', public=True)
def _push_sensor(p: dict) -> dict:
    """IoT 디바이스의 데이터 수신 경로 (device_key 인증 + 승인/제한 게이트).

    data 파라미터에 JSON 으로 여러 지표를 한 번에 보낸다:
      func=push_sensor&device_id=vd01&device_key=...&data={"temperature":25.3,"humidity":60.1}
    """
    from p01_device import verify_push, touch_device   # 순환 import 방지

    device_id = get_param(p, 'device_id', limit=50)
    verify_push(device_id, get_param(p, 'device_key', limit=100))

    try:
        data = json.loads(p.get('data') or '{}')
        assert isinstance(data, dict) and data
    except (ValueError, AssertionError):
        raise HiveError('data 는 {"지표명": 숫자값} 형식의 JSON 이어야 합니다.')

    ts = get_param(p, 'ts') or now_str()
    saved = 0
    for metric, value in data.items():
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise HiveError('지표 %s 의 값이 숫자가 아닙니다.' % str(metric)[:30])
        set_sql("INSERT INTO sensor_data (device_id, metric, value, created) "
                "VALUES (:device_id, :metric, :value, :created)",
                {'device_id': device_id, 'metric': str(metric)[:50],
                 'value': value, 'created': ts})
        saved += 1
    touch_device(device_id)
    return {'saved': saved}


@service('save_sensor')
def _save_sensor(p: dict) -> dict:
    """외부 장치가 HTTP 로 직접 푸시하는 수집 경로 (폴링 수집은 p02_collector)"""
    device_id = get_param(p, 'device_id', limit=50)
    metric = get_param(p, 'metric', limit=50)
    value = get_float(p, 'value')
    if not device_id or not metric or value is None:
        raise HiveError('device_id, metric, value(숫자)는 필수입니다.')

    set_sql("INSERT INTO sensor_data (device_id, metric, value, created) "
            "VALUES (:device_id, :metric, :value, :created)",
            {'device_id': device_id, 'metric': metric,
             'value': value, 'created': get_param(p, 'ts') or now_str()})
    return {'saved': 1}


@service('list_sensor')
def _list_sensor(p: dict) -> dict:
    limit = min(max(get_int(p, 'limit', 100), 1), 1000)
    rows = get_sql("""
        SELECT oid, device_id, metric, value, created
        FROM sensor_data WHERE 1=1
        <c: AND device_id = :device_id />
        <c: AND metric = :metric />
        <c: AND created >= :date_from />
        <c: AND created <= :date_to />
        ORDER BY oid DESC LIMIT %d
    """ % limit, {
        'device_id': get_param(p, 'device_id'),
        'metric': get_param(p, 'metric'),
        'date_from': get_param(p, 'date_from'),
        'date_to': get_param(p, 'date_to'),
    })
    return {'list': rows}


@service('latest_sensor')
def _latest_sensor(p: dict) -> dict:
    """장치·지표별 최신 1건씩"""
    rows = get_sql("""
        SELECT device_id, metric, value, MAX(created) AS created
        FROM sensor_data WHERE 1=1
        <c: AND device_id = :device_id />
        GROUP BY device_id, metric
        ORDER BY device_id, metric
    """, {'device_id': get_param(p, 'device_id')})
    return {'list': rows}
