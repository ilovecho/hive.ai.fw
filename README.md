# Hive.AI.FW — Python 기반 AI·IoT 동반 서비스 계층

Copyright ⓒ2026 AnHive Co., Ltd. All Rights Reserved.

Hive.fw(PHP+SQLite+순수JS)의 설계 원칙을 승계한 **Python AI·IoT 프레임워크**.
코어는 Python 3.9+ **표준 라이브러리만으로 동작**하며, Raspberry Pi 등 저사양 서버를 지향한다.

> 배경 분석은 [ANALYSIS.md](ANALYSIS.md), 요구사항은 [REQUIREMENTS.md](REQUIREMENTS.md) 참고.

---

## 디렉터리 구조

```
hive.ai.fw/
├── p00_aiservice.py       # 라우터(진입점): POST 단일 엔드포인트, func 분기  [≒ s00_s2service.php]
├── p01_sensor.py          # 서비스: 센서 시계열 저장/조회                    [≒ s01_memo.php]
├── p01_infer.py           # 서비스: AI 추론 (이상감지/추세예측/모델목록)
├── p02_collector.py       # 데몬: IoT 수집 루프 (드라이버 폴링 + 보존 GC)
│
├── inc/
│   ├── db_system.py       # DB 코어: get_sql/set_sql, <c:> 조건 SQL          [≒ inc_db_system.php]
│   ├── util_service.py    # 유틸: @service 레지스트리, 입력 헬퍼, trace_log  [≒ inc_util_service.php]
│   └── drivers/
│       ├── base.py        # SensorDriver 플러그인 규약
│       └── sim.py         # 시뮬레이션 드라이버 (하드웨어 없이 검증)
│
├── models/                # AI 모델 저장소 (pkl/tflite — 디렉터리=저장소 규약)
├── db/                    # SQLite hive_ai.db (자동 생성, WAL 모드)
└── etc/                   # systemd 유닛 샘플 (api / collector)
```

---

## 빠른 시작 (의존성 설치 불필요)

```bash
# 터미널 1: API 서버 (기본 127.0.0.1:8600)
python p00_aiservice.py

# 터미널 2: 수집 데몬 (시뮬레이션 센서, 10초 주기)
python p02_collector.py
```

동작 확인:

```bash
curl http://127.0.0.1:8600/health

# 최신 센서값
curl -d 'func=latest_sensor' http://127.0.0.1:8600/

# 이상감지 (수집 데이터 3건 이상 쌓인 뒤)
curl -d 'func=infer_anomaly&device_id=sim01&metric=temperature&window=50&sigma=3' \
     http://127.0.0.1:8600/

# 추세 예측
curl -d 'func=predict_next&device_id=sim01&metric=temperature&steps=5' \
     http://127.0.0.1:8600/
```

응답 규약(Hive.fw와 동일): `{ "status": "success"|"error", "data": ... }`

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HIVE_AI_HOST` | `127.0.0.1` | 바인딩 주소. 외부 노출 시 토큰 필수 |
| `HIVE_AI_PORT` | `8600` | API 포트 |
| `HIVE_AI_TOKEN` | (없음) | 공유 토큰. 설정 시 `X-HIVE-TOKEN` 헤더 검증 |
| `HIVE_AI_DB` | `db/hive_ai.db` | SQLite 경로 |
| `HIVE_AI_INTERVAL` | `10` | 수집 주기(초) |
| `HIVE_AI_RETENTION_DAYS` | `90` | 시계열 보존일수 (0=GC 안 함) |
| `HIVE_DEBUG` | (off) | `1`이면 trace 로그 출력 |

---

## func 레퍼런스

| func | 파일 | 설명 |
|------|------|------|
| `save_sensor` | p01_sensor | 센서값 1건 저장 (`device_id, metric, value[, ts]`) — 장치 푸시용 |
| `list_sensor` | p01_sensor | 목록 조회. `<c:>` 필터: `device_id, metric, date_from, date_to, limit` |
| `latest_sensor` | p01_sensor | 장치·지표별 최신 1건 |
| `infer_anomaly` | p01_infer | 이동평균±σ 이상감지 (`device_id, metric[, window, sigma]`) |
| `predict_next` | p01_infer | 최소제곱 추세 예측 (`device_id, metric[, window, steps]`) |
| `list_model` | p01_infer | `models/` 모델 파일 목록 |
| (GET) `/health` | p00 | 무인증 헬스체크 |

---

## 새 기능 추가 (Hive.fw와 동일한 3단계)

1. `p01_xxx.py` 작성:
   ```python
   from inc.db_system import get_sql
   from inc.util_service import service, get_param

   @service('list_xxx')
   def _list_xxx(p: dict) -> dict:
       rows = get_sql("SELECT ... WHERE 1=1 <c: AND col = :k />",
                      {'k': get_param(p, 'k')})
       return {'list': rows}          # 라우터가 {status,data}로 포장
   ```
2. `p00_aiservice.py`의 `SERVICE_FILES`에 `'p01_xxx'` 추가.
3. 호출: `curl -d 'func=list_xxx&k=...' http://127.0.0.1:8600/`

새 센서는 `inc/drivers/`에 `SensorDriver` 상속 클래스를 만들고
`p02_collector.py`의 `load_drivers()`에 추가한다.

---

## Hive.fw(PHP)에서 호출하기

php-curl 로 내부 호출한다 (브라우저 → Python 직접 호출 금지).

```php
function hive_ai(string $func, array $param = []): array
{
    $param['func'] = $func;
    $ch = curl_init('http://127.0.0.1:8600/');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query($param),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 5,
        CURLOPT_HTTPHEADER     => ['X-HIVE-TOKEN: ' . HIVE_AI_TOKEN],
    ]);
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp ?: '{"status":"error","data":"AI 서비스 통신 실패"}', true);
}

// s01_ai.php 서비스 예: 브라우저 → Hive.fw → Hive.AI.FW 프록시
$services['ai_anomaly'] = '_ai_anomaly';
function _ai_anomaly(): void {
    $r = hive_ai('infer_anomaly', [
        'device_id' => get_POST('device_id', ''),
        'metric'    => get_POST('metric', ''),
    ]);
    outputJSON($r['data'], $r['status'] === 'success' ? 'success' : 'error');
}
```

---

## 운영 (Raspberry Pi / systemd)

```bash
sudo cp -r hive.ai.fw /opt/hive.ai.fw
sudo cp /opt/hive.ai.fw/etc/hive-ai-*.service /etc/systemd/system/
# 유닛 파일의 HIVE_AI_TOKEN 값을 변경한 뒤:
sudo systemctl daemon-reload
sudo systemctl enable --now hive-ai-api hive-ai-collector
```

백업: `cp db/hive_ai.db ~/hive_ai.db.$(date +%F).bak` (WAL 파일 포함 시 서비스 정지 후 복사 권장)

## 보안 수칙

- 기본 **loopback 바인딩** — 외부 바인딩 시 `HIVE_AI_TOKEN` 없이는 기동이 거부된다.
- 모든 SQL 값은 named parameter 바인딩(인젝션 안전). `<c:>`는 줄 포함/제외만 결정.
- 예외 상세는 서버 로그에만 남고 클라이언트엔 일반 메시지만 반환(`HiveError`만 노출).
- TLS·외부 인증이 필요하면 Apache/Nginx 역프록시 뒤에 배치한다.
