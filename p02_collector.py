# -*- coding: utf-8 -*-
"""
p02_collector.py — IoT 수집 데몬

등록된 드라이버를 주기 폴링하여 sensor_data 에 저장한다.
드라이버 1개의 오류는 해당 장치만 건너뛰고 루프를 계속한다.
1일 1회 보존기간(HIVE_AI_RETENTION_DAYS) 초과 데이터를 GC 한다.

환경변수:
  HIVE_AI_INTERVAL        수집 주기(초, 기본 10)
  HIVE_AI_RETENTION_DAYS  보존일수(기본 90, 0이면 GC 안 함)

실행: python p02_collector.py
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inc.db_system import set_sql
from inc.util_service import trace_log, now_str
from inc.drivers.sim import SimDriver
from p01_sensor import ensure_schema

INTERVAL = max(int(os.environ.get('HIVE_AI_INTERVAL', '10')), 1)
RETENTION_DAYS = int(os.environ.get('HIVE_AI_RETENTION_DAYS', '90'))


def load_drivers() -> list:
    """수집 대상 드라이버 등록 — 실 센서 추가 시 이 목록에 꽂는다.

    예) from inc.drivers.dht22 import Dht22Driver
        return [SimDriver('sim01'), Dht22Driver('room1', pin=4)]
    """
    return [SimDriver('sim01')]


def collect_once(drivers: list) -> int:
    saved = 0
    ts = now_str()
    for drv in drivers:
        try:
            for metric, value in drv.read():
                set_sql("INSERT INTO sensor_data (device_id, metric, value, created) "
                        "VALUES (:device_id, :metric, :value, :created)",
                        {'device_id': drv.device_id, 'metric': metric,
                         'value': float(value), 'created': ts})
                saved += 1
        except Exception as e:
            trace_log('[COLLECT][%s] 건너뜀: %s' % (drv.device_id, e), force=True)
    return saved


def gc_old_data() -> None:
    if RETENTION_DAYS <= 0:
        return
    n = set_sql("DELETE FROM sensor_data WHERE created < datetime('now', 'localtime', :off)",
                {'off': '-%d days' % RETENTION_DAYS})
    if n:
        trace_log('[GC] %d행 삭제 (보존 %d일 초과)' % (n, RETENTION_DAYS), force=True)


_running = True


def _stop(signum, frame):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    ensure_schema()
    drivers = load_drivers()
    print('Hive.AI.FW 수집기 시작: %d개 장치, 주기 %d초' % (len(drivers), INTERVAL))

    last_gc_day = ''
    while _running:
        saved = collect_once(drivers)
        trace_log('[COLLECT] %d건 저장' % saved)

        today = now_str()[:10]
        if today != last_gc_day:
            gc_old_data()
            last_gc_day = today

        for _ in range(INTERVAL * 10):      # 종료 신호에 빠르게 반응
            if not _running:
                break
            time.sleep(0.1)
    print('수집기를 종료합니다.')


if __name__ == '__main__':
    main()
