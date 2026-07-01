# -*- coding: utf-8 -*-
"""
p01_sensor.py — 서비스: 센서 시계열 저장/조회  [Hive.fw s01_memo.php 패턴 대응]

func: save_sensor / list_sensor / latest_sensor
테이블은 CREATE TABLE IF NOT EXISTS 로 자동 생성한다.
"""
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
