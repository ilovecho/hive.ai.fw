# Hive.AI.FW — 개발 요구사항 정의서

Python 기반 AI·IoT 동반 서비스 계층. Hive.fw의 설계 원칙(단일 진입점, 얇은 레이어,
규약 우선, 무의존, 보안 기본값)을 승계한다. 배경 분석은 [ANALYSIS.md](ANALYSIS.md) 참고.

---

## 1. 기능 요구사항 (FR)

| ID | 요구사항 | 우선순위 | 비고 |
|----|----------|:--:|------|
| FR-01 | **단일 진입점 API 서버**: POST 요청의 `func` 값으로 등록된 서비스 함수를 분기 호출한다 | 필수 | `p00_aiservice.py` |
| FR-02 | **서비스 등록 규약**: `@service('func명')` 데코레이터로 함수를 등록하며, `p01_*.py` 파일 추가만으로 확장된다 | 필수 | Hive.fw `$services[]` 대응 |
| FR-03 | **통일 응답 규약**: 모든 응답은 `{"status":"success"\|"error","data":...}` JSON | 필수 | Hive.fw와 동일 계약 |
| FR-04 | **DB 헬퍼**: `get_sql / set_sql / get_link / get_count / csv_sql` 및 `<c:>` 조건부 SQL 컴파일러 제공 | 필수 | `inc/db_system.py` |
| FR-05 | **IoT 수집 데몬**: 등록된 드라이버를 주기 폴링하여 `sensor_data`에 저장. 드라이버 1개 오류가 전체 루프를 중단시키지 않는다 | 필수 | `p02_collector.py` |
| FR-06 | **드라이버 플러그인 규약**: `SensorDriver` 상속 + `read()` 구현만으로 신규 센서 연결. 시뮬레이션 드라이버 기본 제공 | 필수 | `inc/drivers/` |
| FR-07 | **센서 조회/저장 서비스**: `save_sensor`(외부 푸시 수집), `list_sensor`(기간·장치·지표 필터), `latest_sensor` | 필수 | `p01_sensor.py` |
| FR-08 | **시계열 보존기간 GC**: 보존일수 초과 데이터 주기 삭제 | 권장 | 수집 루프 내 1일 1회 |
| FR-09 | **통계 기반 AI(1단계)**: 이동평균+σ 이상감지(`infer_anomaly`), 최소제곱 추세 예측(`predict_next`) — stdlib만 사용 | 필수 | `p01_infer.py` |
| FR-10 | **모델 저장소**: `models/` 디렉터리 파일 목록 조회(`list_model`), 2단계에서 pkl/tflite 로드 추론 | 권장 | |
| FR-11 | **추론 결과 이력**: 추론 호출 결과를 `ai_result`에 기록 | 권장 | |
| FR-12 | **헬스체크**: `GET /health` — 무인증 상태 확인 | 필수 | systemd/모니터링용 |
| FR-13 | **스키마 자동 생성**: 필요한 테이블은 `CREATE TABLE IF NOT EXISTS`로 서비스가 생성 | 필수 | Hive.fw 패턴 승계 |

## 2. 비기능 요구사항 (NFR)

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-01 | **무의존 코어** | 프레임워크 코어(라우터·DB·수집기·1단계 AI)는 Python 3.9+ stdlib만으로 동작 |
| NFR-02 | **저사양 동작** | Raspberry Pi 3B(1GB RAM)에서 수집기+API 동시 상주 가능 |
| NFR-03 | **보안 기본값** | 기본 `127.0.0.1` 바인딩. 토큰(`HIVE_AI_TOKEN`) 설정 시 `X-HIVE-TOKEN` 헤더를 `hmac.compare_digest`로 검증. 예외 상세는 로그에만, 클라이언트엔 일반 메시지 |
| NFR-04 | **SQL 인젝션 방지** | 모든 값은 named parameter 바인딩. `<c:>`는 줄 포함/제외만 결정 |
| NFR-05 | **동시성** | SQLite `journal_mode=WAL` + `busy_timeout=5000ms`. 쓰기는 수집기 단일 프로세스 원칙 |
| NFR-06 | **운영성** | systemd 유닛 제공(`etc/`). 로그는 stdout(→journald). `HIVE_DEBUG=1`일 때만 trace 로그 |
| NFR-07 | **설정** | 코드 수정 없이 환경변수로 제어: `HIVE_AI_HOST/PORT/TOKEN/DB/INTERVAL/RETENTION_DAYS/HIVE_DEBUG` |
| NFR-08 | **호환성** | Windows(개발)·Linux/Raspberry Pi(운영) 양쪽에서 실행 가능 |

## 3. 인터페이스 계약 (Hive.fw ↔ Hive.AI.FW)

- 전송: `POST http://127.0.0.1:8600/` — `application/x-www-form-urlencoded` 또는 `application/json`
- 요청: `func=<서비스명>` + 서비스별 파라미터
- 인증: 헤더 `X-HIVE-TOKEN: <공유토큰>` (양쪽 환경설정에 동일 값 보관)
- 응답: `{"status":"success","data":{...}}` / 오류 시 `{"status":"error","data":"<안전 메시지>"}` + HTTP 4xx/5xx
- PHP 측 호출은 php-curl 사용(README에 헬퍼 예시)

## 4. 환경 요구사항

| 구분 | 항목 |
|------|------|
| 필수 | Python **3.9+** (Raspberry Pi OS Bullseye 이상 기본 탑재) |
| 필수 | SQLite3 (Python 내장 `sqlite3` 모듈) |
| 선택 | numpy / scikit-learn (2단계 모델 추론) |
| 선택 | tflite-runtime (3단계 엣지 추론) |
| 선택 | paho-mqtt, pyserial, smbus2, gpiozero (실 센서 연동) |
| 운영 | systemd (데몬 상주), 방화벽(외부 바인딩 시) |

## 5. 개발 로드맵

| 단계 | 범위 | 완료 기준 |
|------|------|-----------|
| **M1 스켈레톤** | 라우터·DB 코어·시뮬레이션 수집·통계 AI (본 저장소) | 시뮬 데이터 수집→조회→이상감지 왕복 동작 |
| **M2 실 센서** | GPIO/I2C/MQTT 드라이버, 보존 GC, ai_result 이력 | 실 장치 24h 무중단 수집 |
| **M3 모델 추론** | pkl/tflite 모델 로드·추론 서비스, Hive.fw 관리 화면(w01_ai*.html) | 모델 교체 무중단 반영 |
| **M4 운영 강화** | 백업 스크립트, 요구사항 점검 CLI(check_requirements.py), 대시보드 | 운영 체크리스트 통과 |

---

_Copyright ⓒ2026 AnHive Co., Ltd._
