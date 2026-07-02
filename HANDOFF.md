# HANDOFF — 다음 세션 인수인계 문서

새 세션(사람 또는 AI 에이전트)이 이 프로젝트를 이어받기 위한 문서.
**작업 시작 전과 코드 수정 후에 반드시 `python tools/smoke_test.py` 를 실행할 것** (17개 항목 전부 OK 여야 정상).

- 위치: `C:\Users\ilove\Downloads\hive.fw\hive.ai.fw` (git repo, main 브랜치, origin 있음)
- 참조 원본: 같은 상위 폴더의 `hive.fw\` — 경량 PHP+SQLite+바닐라JS 프레임워크. 본 프로젝트는 그 설계 원칙의 Python 승계판
- 주의: 이 작업은 **B48 르완다 TVET 업무와 무관**한 개인 프레임워크 프로젝트

---

## 1. 현재 완료 상태 (2026-07-02 기준)

| 단계 | 내용 | 상태 |
|------|------|:--:|
| M1 스켈레톤 | 라우터(p00)·DB코어(`<c:>` SQL)·시뮬 수집기(p02)·통계 AI(p01_infer) | ✅ |
| 디바이스 수명주기 | 등록→승인대기→승인/차단, device_key 인증, 전송주기 제한 | ✅ |
| 데이터 수신·저장 | push_sensor (3중 게이트: 키·승인·주기) → SQLite(WAL) | ✅ |
| 가상 디바이스 | d01_virtual_device.py (온습도 시뮬레이션 전송) | ✅ |
| 모니터링 화면 | GET /monitor — 디바이스 관리 + 실시간 카드/차트 (순수 JS) | ✅ |
| Claude 분석 에이전트 | inc/ai_claude.py + p03 데몬 + p01_agent 관리 + GET /agent 화면 | ✅ (실 API 호출만 미검증 — 키 필요) |
| 문서 | README / ANALYSIS / REQUIREMENTS / 사용자메뉴얼 / 본 문서 | ✅ |
| 회귀 테스트 | tools/smoke_test.py — 17항목, 과금 없음, 운영 DB 무영향 | ✅ 17/17 |

**미검증 1건**: Claude 실호출. `pip install anthropic` + `ANTHROPIC_API_KEY` 설정 후
`/agent` 화면의 [지금 분석 실행]으로 확인 필요.

## 2. 파일 맵 (수정 시 짝 관계)

```
p00_aiservice.py     라우터. 새 서비스 파일은 SERVICE_FILES 에, 새 화면은 PAGES 에 등록
inc/util_service.py  @service('func명', public=bool) 레지스트리, HiveError, 입력 헬퍼
inc/db_system.py     get_sql/set_sql + <c:> 조건 SQL (Hive.fw PHP 원본과 동일 동작 유지할 것)
inc/ai_claude.py     Claude API 호출 (anthropic SDK, 기본 claude-opus-4-8)
p01_sensor.py        push_sensor(공개) / save/list/latest_sensor
p01_device.py        register(공개)/list/approve/block/config_device + verify_push 게이트
p01_infer.py         infer_anomaly / predict_next / list_model (stdlib 통계)
p01_agent.py         에이전트 설정·결과 관리 + run_analysis_and_store (p03과 공용)
p02_collector.py     서버측 폴링 수집 데몬 (inc/drivers/ 플러그인)
p03_ai_agent.py      Claude 분석 데몬 (agent_config DB 플래그로 무재시작 제어)
d01_virtual_device.py 가상 디바이스 (데모/테스트용)
w01_monitor.html / w01_agent.html   화면 (p00 이 GET 으로 서빙)
tools/smoke_test.py  회귀 테스트 — 코드 수정 후 필수 실행
```

## 3. 지켜야 할 규약 (Hive.fw 승계 — 어기면 일관성 붕괴)

1. **응답은 항상** `{"status":"success"|"error","data":...}`. 서비스 함수는 data 부분만 반환(라우터가 포장).
2. **서비스 추가 3단계**: `p01_xxx.py` 에 `@service('이름')` 함수 작성 → `p00` 의 `SERVICE_FILES` 에 모듈명 추가 → 끝. 라우터 본문은 건드리지 않는다.
3. **SQL 은 named parameter 바인딩만**. 동적 조건은 `<c: AND col = :k />` 사용. 문자열 조립 금지(LIMIT 정수 제외).
4. **공개(public) func 최소화**: 현재 `register_device`, `push_sensor` 뿐. 이들은 device_key 로 자체 인증. 나머지는 전부 X-HIVE-TOKEN 보호.
5. **코어는 stdlib 만**. anthropic 등 외부 패키지는 import 를 함수 안에서 하고 ImportError 를 HiveError 안내로 변환 (inc/ai_claude.py 패턴).
6. **안전 메시지는 HiveError**, 그 외 예외는 라우터가 마스킹. 내부 정보를 클라이언트에 노출하지 않는다.
7. **테이블은 서비스 파일이 `CREATE TABLE IF NOT EXISTS`** 로 소유. 스키마 변경 시 해당 파일에서만.

## 4. 함정과 회피책 (이번 세션에서 실제로 겪은 것)

| 함정 | 증상 | 회피책 |
|------|------|--------|
| Windows 콘솔 cp949 | `UnicodeEncodeError` (—, ℃ 등) | 실행 스크립트 상단의 `sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)` 블록을 새 스크립트에도 복사. print 문자열에 U+2014(—) 같은 특수문자 지양 |
| stdout 버퍼링 | 리다이렉트/서비스 로그가 비어 보임 | 위 reconfigure 가 해결. 데몬 print 에는 flush=True 유지 |
| Git Bash `cd X && cmd &` | cd 가 메인 셸에 적용 안 됨 → 다음 명령이 엉뚱한 경로에서 실행 | 백그라운드 실행은 **절대경로**로: `python "$BASE/스크립트.py" &` |
| `$TMPDIR` 빈 값 | `HIVE_AI_DB=/xxx.db` 가 되어 `unable to open database file` | 테스트 DB 경로는 python `tempfile` 또는 절대경로로 지정 |
| SQLite 파일 잠금 | 서버 살아있는 동안 `rm db/hive_ai.db` 실패 (Device busy) | 프로세스 종료 후 삭제. 테스트는 임시 DB 사용 (smoke_test 패턴) |
| 스레드-로컬 커넥션 | inc/db_system 은 스레드별 커넥션 전제 | 새 데몬/스레드 코드는 커넥션 공유 금지 — 그냥 get_sql/set_sql 만 쓰면 안전 |
| Claude 과금 사고 | 테스트 중 실 API 호출 | smoke_test 는 ANTHROPIC_API_KEY 를 제거하고 서버를 띄움 — 이 패턴 유지 |
| Claude API 파라미터 | temperature/top_p/budget_tokens 는 최신 모델에서 400 | 모델 ID 는 `claude-opus-4-8` 형식 그대로, 샘플링 파라미터 금지. Claude 코드 수정 전 `/claude-api` 스킬(가능하면) 참조 |
| 포트 충돌 | 테스트 서버 기동 실패 | 운영 8600, 수동테스트 8611, smoke_test 8699 로 분리 |
| 승인 전 디바이스 | "전송 거부: 승인 대기"가 오류처럼 보임 | 정상 설계. /monitor 에서 승인하면 해소 |

## 5. 검증 절차 (표준)

```bash
cd C:\Users\ilove\Downloads\hive.fw\hive.ai.fw
python tools/smoke_test.py          # ① 회귀: 17/17 통과 확인 (과금·운영DB 영향 없음)

# ② 수동 확인이 필요할 때 (터미널 3개)
python p00_aiservice.py             #    서버 (HIVE_AI_TOKEN 설정 권장)
python d01_virtual_device.py        #    가상 디바이스
python p03_ai_agent.py              #    에이전트 (Claude 검증 시 ANTHROPIC_API_KEY 필요)
# 브라우저: http://127.0.0.1:8600/monitor , /agent
```

## 6. 다음 작업 후보 (우선순위 제안)

1. **Claude 실호출 검증** — API 키 설정 후 run_agent_now 1회, 응답 품질/프롬프트 튜닝
2. **M2 실 센서 드라이버** — inc/drivers/ 에 gpiozero(DHT22)·smbus2(I2C)·paho-mqtt 드라이버 추가 (base.SensorDriver 상속, p02 load_drivers 에 등록)
3. 디바이스 삭제/키 재발급 func, 모니터 차트 다중 지표 표시
4. 분석 결과를 Hive.fw(PHP) 화면에서 보여주는 프록시 서비스(s01_ai.php) — README 의 PHP 연동 예 참고
5. check_requirements.py (Hive.fw 의 check_requirements.php 대응)

---

## 7. 다음 세션 시작 프롬프트 (복사해서 사용)

아래 블록을 새 세션 첫 메시지로 붙여넣고, 마지막 줄에 그날의 작업 지시를 채운다.

```
Hive.AI.FW 프로젝트 작업을 이어서 진행한다. (주의: B48 르완다 TVET 업무와 무관)

[컨텍스트]
- 프로젝트: C:\Users\ilove\Downloads\hive.fw\hive.ai.fw (git repo)
- 시작 전에 HANDOFF.md 를 먼저 읽고 규약(3장)과 함정 회피책(4장)을 따를 것
- 참조 원본 프레임워크: C:\Users\ilove\Downloads\hive.fw\hive.fw (PHP Hive.fw)

[작업 규칙]
1. 작업 시작 시와 코드 수정 후 python tools/smoke_test.py 실행 — 17/17 통과 필수
2. 새 서비스는 @service 데코레이터 + p00 SERVICE_FILES 등록 방식만 사용
3. 응답 규약 {status,data}, <c:> 조건 SQL, HiveError 안전 메시지 규약 유지
4. 코어는 Python stdlib 만, 외부 패키지는 함수 내 import + ImportError 안내
5. Claude API 코드를 수정할 때는 claude-api 스킬을 먼저 로드하고, 모델 기본값은
   claude-opus-4-8, 샘플링 파라미터(temperature 등) 금지
6. 테스트로 실 Claude 호출(과금) 금지 — smoke_test 의 키 제거 패턴 유지
7. git 커밋은 내가 요청할 때만

[오늘 작업]
(여기에 지시 입력 — 예: "HANDOFF.md 6장 후보 1번: Claude 실호출 검증과 프롬프트 튜닝을 진행해줘")
```

_Copyright ⓒ2026 AnHive Co., Ltd._
