# Hive.AI.FW — Python 기반 AI·IoT 지원 분석 (재정리)

Hive.fw(경량 PHP + SQLite + 순수 JS 웹 프레임워크)를 참조 모델로 하여,
**AI 추론과 IoT 데이터 수집을 Python으로 지원**하기 위한 분석을 재정리한 문서.

> 개발 요구사항은 [REQUIREMENTS.md](REQUIREMENTS.md), 빠른 시작은 [README.md](README.md) 참고.

---

## 1. 배경과 문제 정의

Hive.fw는 업무 화면(CRUD)·인증·첨부 관리에 최적화된 웹 프레임워크다.
그러나 다음 워크로드는 PHP 웹 요청 모델(요청-응답 단위 실행)과 맞지 않는다.

| 워크로드 | PHP(Hive.fw)의 한계 | 필요한 실행 모델 |
|----------|--------------------|-----------------|
| **IoT 센서 수집** | 상시 실행 프로세스 없음. GPIO/I2C/시리얼 라이브러리 빈약 | 상주 데몬(폴링 루프 / 이벤트 구독) |
| **시계열 축적·집계** | cron+PHP로 가능하나 관리 어려움 | 수집기와 저장을 한 프로세스에서 |
| **AI 추론** | ML 생태계 부재 | numpy·scikit-learn·tflite 등 Python 생태계 |
| **주기 배치(모델 재학습 등)** | 웹 요청 수명에 갇힘 | 스케줄러/장기 실행 프로세스 |

→ **결론: Hive.fw는 그대로 두고, Python 동반(companion) 서비스 계층을 신설한다.**
이 계층을 **Hive.AI.FW**로 명명한다.

---

## 2. 왜 Python인가

| 판단 기준 | 근거 |
|-----------|------|
| **저사양 서버 적합** | Raspberry Pi OS에 Python 3 기본 탑재 — Hive.fw의 "무의존·저사양" 원칙과 일치 |
| **IoT 생태계** | gpiozero / RPi.GPIO(GPIO), smbus2(I2C), pyserial(RS-232/485), paho-mqtt(MQTT) |
| **AI 생태계** | numpy, pandas, scikit-learn, tflite-runtime(경량 엣지 추론), onnxruntime |
| **stdlib만으로 코어 구동** | `http.server`, `sqlite3`, `json`, `statistics` — 외부 패키지 0개로 프레임워크 코어 동작 가능 |
| **상주 프로세스** | systemd 서비스로 수집 데몬·API 서버 상시 운영 |

---

## 3. 역할 분담 (Hive.fw ↔ Hive.AI.FW)

```
[브라우저]
   │  HTML/JS (anhive.base.js)
   ▼
[Hive.fw / PHP]  ── 화면·인증·CSRF·업무 CRUD ──  db/hive.db (업무 DB)
   │
   │  HTTP JSON (php-curl, 내부망, 토큰 인증)
   ▼
[Hive.AI.FW / Python]
   ├─ p00_aiservice.py   API 서버 (func 분기, {status,data} 응답)
   ├─ p02_collector.py   IoT 수집 데몬 (드라이버 플러그인)
   └─ db/hive_ai.db      센서 시계열·추론 결과 (WAL 모드)
        ▲
        │  GPIO / I2C / Serial / MQTT / 시뮬레이션
   [센서·장치]
```

- **Hive.fw**: 사용자 접점 전담. 브라우저는 Python 서버에 직접 접근하지 않는다.
- **Hive.AI.FW**: 수집·저장·추론 전담. 기본 `127.0.0.1` 바인딩 + 공유 토큰으로 내부 호출만 허용.
- **DB 분리**: 업무 DB(`hive.db`)와 시계열 DB(`hive_ai.db`)를 분리해 SQLite 잠금 경합을 차단.
  PHP가 시계열을 읽을 일은 HTTP API로 해결(직접 파일 공유 금지).

---

## 4. Hive.fw 설계 원칙의 승계 매핑

| Hive.fw 원칙 | Hive.AI.FW 구현 |
|--------------|-----------------|
| **단일 진입점** (`s00_s2service.php`, `func` 분기) | `p00_aiservice.py` — POST 단일 엔드포인트, `func` 값으로 등록 서비스 분기 |
| **얇은 레이어** (라우터→서비스 함수→DB 헬퍼) | 라우터 → `@service` 등록 함수 → `get_sql/set_sql`. 프레임워크/ORM 없음 |
| **규약 우선** (`$services['func']`, `{status,data}`, `<c:>` SQL) | `@service('func')` 데코레이터, 동일 `{status,data}` 응답, `<c:>` 조건 SQL 포팅 |
| **무의존** | 코어는 Python stdlib만 사용. AI/IoT 라이브러리는 **선택적 플러그인** |
| **보안 기본값** | 기본 loopback 바인딩, `X-HIVE-TOKEN` 공유 토큰(`hmac.compare_digest`), prepared statement, 예외 메시지 마스킹 |

파일 명명도 승계: `s00_/s01_` → `p00_`(라우터) / `p01_`(서비스) / `p02_`(데몬), `inc/`(공통 모듈).

---

## 5. 데이터 모델

```sql
-- 센서 시계열 (수집기·API가 CREATE TABLE IF NOT EXISTS 로 자동 생성)
sensor_data(oid PK, device_id, metric, value REAL, created)
  INDEX (device_id, metric, created)

-- AI 모델 메타 (models/ 디렉터리 파일 기준, 조회 서비스 제공)
-- 추론 결과 이력
ai_result(oid PK, func, device_id, metric, result_json, created)
```

- 시계열은 **append-only** — UPDATE 없음, 보존기간 초과분 주기 삭제(GC)만 수행.
- SQLite는 `journal_mode=WAL` + `busy_timeout`으로 수집기(쓰기)·API(읽기) 동시성 확보.

---

## 6. AI 지원 범위 (단계적)

| 단계 | 내용 | 의존성 |
|------|------|--------|
| **1단계 (코어)** | 통계 기반: 이동평균·표준편차(σ) 이상감지, 최소제곱 추세 예측 | stdlib `statistics`만 |
| **2단계** | scikit-learn 모델(회귀/분류) — `models/*.pkl` 로드 후 추론 | numpy, scikit-learn |
| **3단계** | tflite-runtime 엣지 추론(이미지/음향 등) | tflite-runtime |

모델 파일은 `models/` 디렉터리에 두고 서비스가 파일명으로 참조 — Hive.fw의
`document/`(콘텐츠 저장소) 패턴과 동일하게 "디렉터리 = 저장소" 규약.

---

## 7. IoT 지원 범위

- **드라이버 플러그인 규약**: `inc/drivers/base.py`의 `SensorDriver`를 상속,
  `read() → [(metric, value), ...]`만 구현하면 수집기에 꽂힌다.
- 기본 제공: `SimDriver`(시뮬레이션 — 하드웨어 없이 전체 파이프라인 검증).
- 확장 예: GPIO(gpiozero), I2C(smbus2), Modbus/시리얼(pyserial), MQTT 구독(paho-mqtt).
- 수집 주기는 환경변수(`HIVE_AI_INTERVAL`)로 제어, 드라이버 예외는 해당 장치만 건너뛰고 루프 지속.

---

## 8. 위험·제약 사항

| 위험 | 대응 |
|------|------|
| SQLite 동시 쓰기 한계 | WAL 모드 + 단일 쓰기 프로세스(수집기) 원칙. 대량 유입 시 배치 INSERT |
| 저사양 보드의 추론 성능 | 1단계 통계 기법 우선, 무거운 모델은 tflite 양자화 모델만 |
| Python 서버 노출 | 기본 loopback. 외부 바인딩 시 토큰 필수 + 방화벽. TLS는 역프록시(Apache)에 위임 |
| 시계열 무한 증가 | 보존기간 GC(요구사항 FR-08) |
| PHP↔Python 규약 불일치 | 응답 `{status,data}` 규약을 동일하게 강제, 본 문서와 README에 계약 명시 |

---

_Copyright ⓒ2026 AnHive Co., Ltd. — 기술 설계 개념._
