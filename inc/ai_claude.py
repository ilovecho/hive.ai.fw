# -*- coding: utf-8 -*-
"""
inc/ai_claude.py — Claude API 로 수집 정보를 분석하는 모듈

공식 anthropic SDK 사용 (선택 의존성: pip install anthropic).
API 키는 환경변수 ANTHROPIC_API_KEY 로 설정한다.

  analyze_recent(window_min, model) → {'model', 'analysis', 'input_tokens', 'output_tokens'}
"""
import os

from inc.db_system import get_sql
from inc.util_service import HiveError, trace_log

DEFAULT_MODEL = os.environ.get('HIVE_AI_MODEL', 'claude-opus-4-8')

# 시스템 프롬프트는 고정 문자열로 유지한다 (프롬프트 캐시 프리픽스 보존)
_SYSTEM = (
    'You are an IoT telemetry analyst for the Hive.AI.FW monitoring system. '
    'You receive aggregated sensor statistics and recent readings. '
    'Respond in Korean. Structure: 1) 요약(2~3문장) 2) 지표별 상태 평가 '
    '3) 이상 징후 또는 주의사항 4) 권장 조치(없으면 "없음"). '
    'Be specific with numbers. Keep the whole response under 400 words.'
)


def _collect_stats(window_min: int) -> str:
    """최근 window_min 분의 데이터를 통계 + 최근 표본으로 요약해 프롬프트 본문 생성"""
    stats = get_sql("""
        SELECT device_id, metric, COUNT(*) AS cnt,
               ROUND(AVG(value),2) AS avg, ROUND(MIN(value),2) AS min,
               ROUND(MAX(value),2) AS max
        FROM sensor_data
        WHERE created >= datetime('now', 'localtime', :off)
        GROUP BY device_id, metric ORDER BY device_id, metric
    """, {'off': '-%d minutes' % window_min})
    if not stats:
        raise HiveError('최근 %d분간 수집된 데이터가 없습니다.' % window_min)

    recent = get_sql("""
        SELECT device_id, metric, value, created FROM sensor_data
        ORDER BY oid DESC LIMIT 30
    """)
    recent.reverse()

    lines = ['[최근 %d분 통계]' % window_min]
    for s in stats:
        lines.append('%s/%s: 건수=%d 평균=%s 최소=%s 최대=%s'
                     % (s['device_id'], s['metric'], s['cnt'],
                        s['avg'], s['min'], s['max']))
    lines.append('')
    lines.append('[최근 표본 30건 (시간 오름차순)]')
    for r in recent:
        lines.append('%s %s/%s=%s' % (r['created'], r['device_id'],
                                      r['metric'], r['value']))
    return '\n'.join(lines)


def analyze_recent(window_min: int = 60, model: str = None) -> dict:
    """최근 수집 데이터를 Claude 에 보내 분석 결과를 수신한다."""
    try:
        import anthropic
    except ImportError:
        raise HiveError('anthropic 패키지가 없습니다. "pip install anthropic" 후 사용하세요.')

    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise HiveError('ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.')

    model = model or DEFAULT_MODEL
    body = _collect_stats(window_min)

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,   # 분석 요약은 짧은 출력으로 비용 상한
            system=_SYSTEM,
            messages=[{'role': 'user',
                       'content': '다음 IoT 수집 데이터를 분석해 주세요.\n\n' + body}],
        )
    except anthropic.AuthenticationError:
        raise HiveError('Claude API 인증 실패: ANTHROPIC_API_KEY 를 확인하세요.')
    except anthropic.NotFoundError:
        raise HiveError('모델을 찾을 수 없습니다: %s' % model)
    except anthropic.RateLimitError:
        raise HiveError('Claude API 사용량 제한(429)입니다. 잠시 후 다시 시도하세요.')
    except anthropic.APIStatusError as e:
        trace_log('[CLAUDE] APIStatusError %s: %s' % (e.status_code, e.message), force=True)
        raise HiveError('Claude API 오류(HTTP %s)가 발생했습니다.' % e.status_code)
    except anthropic.APIConnectionError:
        raise HiveError('Claude API 에 연결할 수 없습니다. 네트워크를 확인하세요.')

    if response.stop_reason == 'refusal':
        raise HiveError('Claude 가 이 요청의 처리를 거절했습니다.')

    text = '\n'.join(b.text for b in response.content if b.type == 'text').strip()
    if not text:
        raise HiveError('Claude 응답에 텍스트가 없습니다.')

    return {
        'model': response.model,
        'analysis': text,
        'input_tokens': response.usage.input_tokens,
        'output_tokens': response.usage.output_tokens,
    }
