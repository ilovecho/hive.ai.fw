# -*- coding: utf-8 -*-
"""
inc/drivers/sim.py — 시뮬레이션 드라이버

하드웨어 없이 수집→저장→조회→추론 전체 파이프라인을 검증하기 위한 기본 드라이버.
온도(25±3℃ 사인파+노이즈)·습도(60±10%)를 생성한다.
"""
import math
import random
import time

from inc.drivers.base import SensorDriver


class SimDriver(SensorDriver):
    PERIOD_SEC = 3600  # 1시간 주기 사인파

    def read(self) -> list:
        phase = (time.time() % self.PERIOD_SEC) / self.PERIOD_SEC * 2 * math.pi
        temp = 25.0 + 3.0 * math.sin(phase) + random.gauss(0, 0.3)
        humi = 60.0 + 10.0 * math.cos(phase) + random.gauss(0, 1.0)
        return [
            ('temperature', round(temp, 2)),
            ('humidity', round(humi, 2)),
        ]
