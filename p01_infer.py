# -*- coding: utf-8 -*-
"""
p01_infer.py — 서비스: AI 추론 (1단계: stdlib 통계 기반)

func: infer_anomaly / predict_next / list_model

  infer_anomaly : 최근 window 건의 이동평균±sigma·σ 밴드로 최신값 이상 여부 판정
  predict_next  : 최소제곱 직선 적합으로 다음 steps 구간 예측
  list_model    : models/ 디렉터리의 모델 파일 목록 (2단계 pkl/tflite 추론용)

2단계(scikit-learn)·3단계(tflite) 추론은 이 파일에 func 를 추가하는 방식으로 확장한다.
"""
import json
import os
import statistics

from inc.db_system import get_sql, set_sql
from inc.util_service import service, HiveError, get_param, get_int, get_float, now_str

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

_DDL = """
CREATE TABLE IF NOT EXISTS ai_result (
    oid         INTEGER PRIMARY KEY AUTOINCREMENT,
    func        TEXT NOT NULL,
    device_id   TEXT,
    metric      TEXT,
    result_json TEXT NOT NULL,
    created     TEXT NOT NULL
)
"""
set_sql(_DDL)


def _recent_values(p: dict, window: int):
    device_id = get_param(p, 'device_id')
    metric = get_param(p, 'metric')
    if not device_id or not metric:
        raise HiveError('device_id, metric 은 필수입니다.')
    rows = get_sql("""
        SELECT value, created FROM sensor_data
        WHERE device_id = :device_id AND metric = :metric
        ORDER BY oid DESC LIMIT %d
    """ % window, {'device_id': device_id, 'metric': metric})
    if len(rows) < 3:
        raise HiveError('데이터가 부족합니다 (최소 3건 필요, 현재 %d건).' % len(rows))
    rows.reverse()                      # 시간 오름차순
    return device_id, metric, rows


def _log_result(func: str, device_id: str, metric: str, result: dict) -> None:
    set_sql("INSERT INTO ai_result (func, device_id, metric, result_json, created) "
            "VALUES (:func, :device_id, :metric, :result_json, :created)",
            {'func': func, 'device_id': device_id, 'metric': metric,
             'result_json': json.dumps(result, ensure_ascii=False),
             'created': now_str()})


@service('infer_anomaly')
def _infer_anomaly(p: dict) -> dict:
    window = min(max(get_int(p, 'window', 50), 3), 1000)
    sigma = get_float(p, 'sigma') or 3.0
    device_id, metric, rows = _recent_values(p, window)

    values = [r['value'] for r in rows]
    latest = values[-1]
    base = values[:-1]                  # 최신값 제외한 기준 구간
    mean = statistics.fmean(base)
    stdev = statistics.pstdev(base)
    band = sigma * stdev
    is_anomaly = stdev > 0 and abs(latest - mean) > band

    result = {
        'device_id': device_id, 'metric': metric,
        'latest': latest, 'latest_at': rows[-1]['created'],
        'mean': round(mean, 4), 'stdev': round(stdev, 4),
        'threshold': round(band, 4), 'sigma': sigma,
        'window': len(values), 'is_anomaly': is_anomaly,
    }
    _log_result('infer_anomaly', device_id, metric, result)
    return result


@service('predict_next')
def _predict_next(p: dict) -> dict:
    window = min(max(get_int(p, 'window', 50), 3), 1000)
    steps = min(max(get_int(p, 'steps', 5), 1), 100)
    device_id, metric, rows = _recent_values(p, window)

    ys = [r['value'] for r in rows]
    xs = list(range(len(ys)))
    n = len(xs)
    # 최소제곱 직선 적합: y = slope*x + intercept
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = (sxy / sxx) if sxx else 0.0
    intercept = my - slope * mx

    forecast = [round(slope * (n - 1 + i) + intercept, 4)
                for i in range(1, steps + 1)]
    result = {
        'device_id': device_id, 'metric': metric,
        'window': n, 'slope': round(slope, 6), 'intercept': round(intercept, 4),
        'last': ys[-1], 'forecast': forecast,
    }
    _log_result('predict_next', device_id, metric, result)
    return result


@service('list_model')
def _list_model(p: dict) -> dict:
    items = []
    if os.path.isdir(MODELS_DIR):
        for name in sorted(os.listdir(MODELS_DIR)):
            path = os.path.join(MODELS_DIR, name)
            if os.path.isfile(path) and not name.startswith('.'):
                st = os.stat(path)
                items.append({'name': name, 'sizeof': st.st_size,
                              'mtime': int(st.st_mtime)})
    return {'list': items}
