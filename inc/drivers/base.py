# -*- coding: utf-8 -*-
"""
inc/drivers/base.py — 센서 드라이버 플러그인 규약

새 센서를 붙이려면 SensorDriver 를 상속하고 read() 만 구현한다.
read() 는 [(metric, value), ...] 목록을 반환하며, 예외를 던지면
수집기가 해당 장치만 건너뛰고 루프를 계속한다.

확장 예:
  GPIO   → gpiozero  (class DhtDriver(SensorDriver): ...)
  I2C    → smbus2
  Serial → pyserial (Modbus RTU 등)
  MQTT   → paho-mqtt (구독형은 read() 대신 내부 캐시 반환)
"""


class SensorDriver:
    def __init__(self, device_id: str):
        self.device_id = device_id

    def read(self) -> list:
        """[(metric: str, value: float), ...] 반환"""
        raise NotImplementedError
