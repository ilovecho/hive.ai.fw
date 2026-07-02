# -*- coding: utf-8 -*-
"""
p01_device.py — 서비스: IoT 디바이스 등록/승인/제한 관리

디바이스 수명주기:
  register_device (공개, 디바이스가 자가 등록) → state=0 승인대기
  → 관리자 approve_device → state=1 승인(데이터 수신 허용)
  → 필요 시 block_device → state=9 차단

제한 관리:
  config_device 로 디바이스별 최소 전송 주기(push_interval, 초)를 지정하면
  그보다 빠른 push 는 거부된다.

디바이스 인증은 등록 시 제출한 device_key 로 한다 (서버 토큰과 별개).
"""
import datetime

from inc.db_system import get_sql, set_sql
from inc.util_service import service, HiveError, get_param, get_int, now_str

_DDL = """
CREATE TABLE IF NOT EXISTS device (
    oid           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT    NOT NULL UNIQUE,
    device_key    TEXT    NOT NULL,
    name          TEXT,
    model         TEXT,
    state         INTEGER NOT NULL DEFAULT 0,   -- 0=승인대기 1=승인 9=차단
    push_interval INTEGER NOT NULL DEFAULT 0,   -- 최소 전송 주기(초), 0=무제한
    last_seen     TEXT,
    created       TEXT    NOT NULL
)
"""
set_sql(_DDL)

STATE_LABEL = {0: '승인대기', 1: '승인', 9: '차단'}


def get_device(device_id: str):
    rows = get_sql("SELECT * FROM device WHERE device_id = :device_id",
                   {'device_id': device_id})
    return rows[0] if rows else None


def verify_push(device_id: str, device_key: str) -> dict:
    """push_sensor 게이트: 등록·키·승인상태·전송주기 검증. 실패 시 HiveError."""
    row = get_device(device_id)
    if row is None:
        raise HiveError('등록되지 않은 디바이스입니다. 먼저 register_device 를 호출하세요.')
    if not device_key or row['device_key'] != device_key:
        raise HiveError('디바이스 인증 실패: device_key 가 일치하지 않습니다.')
    if row['state'] == 0:
        raise HiveError('승인 대기 중인 디바이스입니다. 관리자 승인 후 전송할 수 있습니다.')
    if row['state'] == 9:
        raise HiveError('차단된 디바이스입니다.')

    # 전송 주기 제한 (제한 관리)
    if row['push_interval'] and row['last_seen']:
        last = datetime.datetime.strptime(row['last_seen'], '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.datetime.now() - last).total_seconds()
        if elapsed < row['push_interval']:
            raise HiveError('전송 주기 제한: %d초 이후 다시 전송하세요.'
                            % int(row['push_interval'] - elapsed))
    return row


def touch_device(device_id: str) -> None:
    set_sql("UPDATE device SET last_seen = :now WHERE device_id = :device_id",
            {'now': now_str(), 'device_id': device_id})


# ============================================================
#  디바이스 측 (공개 func — device_key 로 인증)
# ============================================================
@service('register_device', public=True)
def _register_device(p: dict) -> dict:
    device_id = get_param(p, 'device_id', limit=50)
    device_key = get_param(p, 'device_key', limit=100)
    if not device_id or not device_key:
        raise HiveError('device_id, device_key 는 필수입니다.')

    row = get_device(device_id)
    if row is not None:
        # 재등록(재부팅 등): 키가 맞으면 현재 상태만 알려준다
        if row['device_key'] != device_key:
            raise HiveError('이미 등록된 device_id 입니다 (device_key 불일치).')
        return {'device_id': device_id, 'state': row['state'],
                'state_label': STATE_LABEL.get(row['state'], '?')}

    set_sql("""INSERT INTO device (device_id, device_key, name, model, state, created)
               VALUES (:device_id, :device_key, :name, :model, 0, :created)""",
            {'device_id': device_id, 'device_key': device_key,
             'name': get_param(p, 'name', limit=100),
             'model': get_param(p, 'model', limit=100),
             'created': now_str()})
    return {'device_id': device_id, 'state': 0, 'state_label': '승인대기'}


# ============================================================
#  관리자 측 (보호 func — X-HIVE-TOKEN 필요)
# ============================================================
@service('list_device')
def _list_device(p: dict) -> dict:
    rows = get_sql("""
        SELECT oid, device_id, name, model, state, push_interval, last_seen, created
        FROM device WHERE 1=1
        <c: AND state = :state />
        ORDER BY oid DESC
    """, {'state': get_param(p, 'state')})
    for r in rows:
        r['state_label'] = STATE_LABEL.get(r['state'], '?')
    return {'list': rows}


def _set_state(p: dict, state: int) -> dict:
    device_id = get_param(p, 'device_id', limit=50)
    n = set_sql("UPDATE device SET state = :state WHERE device_id = :device_id",
                {'state': state, 'device_id': device_id})
    if n == 0:
        raise HiveError('디바이스를 찾을 수 없습니다: %s' % device_id)
    return {'device_id': device_id, 'state': state,
            'state_label': STATE_LABEL.get(state, '?')}


@service('approve_device')
def _approve_device(p: dict) -> dict:
    return _set_state(p, 1)


@service('block_device')
def _block_device(p: dict) -> dict:
    return _set_state(p, 9)


@service('config_device')
def _config_device(p: dict) -> dict:
    """전송 주기 제한(초) 설정. 0 = 무제한"""
    device_id = get_param(p, 'device_id', limit=50)
    interval = max(get_int(p, 'push_interval', 0), 0)
    n = set_sql("UPDATE device SET push_interval = :iv WHERE device_id = :device_id",
                {'iv': interval, 'device_id': device_id})
    if n == 0:
        raise HiveError('디바이스를 찾을 수 없습니다: %s' % device_id)
    return {'device_id': device_id, 'push_interval': interval}
