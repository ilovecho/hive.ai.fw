# -*- coding: utf-8 -*-
"""
inc/db_system.py — SQLite 기반 DB 공통 모듈 (Hive.fw inc_db_system.php 포팅)

설정 (환경변수로 제어, 미설정 시 기본값):
  HIVE_AI_DB = /path/to/hive_ai.db   (기본: <프로젝트>/db/hive_ai.db)

파라미터 키는 Hive.fw 규약(':key')과 Python 스타일('key') 모두 허용한다.
"""
import csv
import io
import math
import os
import re
import sqlite3
import threading

from inc.util_service import trace_log, HiveError

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('HIVE_AI_DB', os.path.join(_BASE_DIR, 'db', 'hive_ai.db'))

# ============================================================
#  DB 커넥션 (스레드별 싱글톤 — ThreadingHTTPServer 대응)
# ============================================================
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn

    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.isdir(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA busy_timeout = 5000')
    _local.conn = conn
    return conn


# ============================================================
#  <c: AND col = :param /> 조건부 SQL 템플릿
#
#  줄 안의 :param 값이 모두 None/'' 이면 그 줄 전체를 제거하고
#  파라미터도 정리, 하나라도 값이 있으면 태그만 벗겨 포함한다.
# ============================================================
_COND_RE = re.compile(r'<[Cc]:(?P<cond>.*?)/>')
_KEY_RE = re.compile(r':(\w+)')


def _normalize_params(params: dict) -> dict:
    """':key' / 'key' 혼용 키를 'key' 로 통일"""
    return {(k[1:] if isinstance(k, str) and k.startswith(':') else k): v
            for k, v in (params or {}).items()}


def compile_sql_template(sql: str, params: dict) -> tuple:
    params = _normalize_params(params)
    out_lines = []
    for line in sql.splitlines():
        m = _COND_RE.search(line)
        if not m:
            out_lines.append(line)
            continue

        cond = m.group('cond')
        keys = list(dict.fromkeys(_KEY_RE.findall(cond)))
        has_value = any(params.get(k) not in (None, '') for k in keys)

        if not has_value:
            for k in keys:
                params.pop(k, None)     # 미사용 파라미터 제거
            continue                    # 조건절 제거
        out_lines.append(cond)          # 태그 제거 후 조건만 포함
    return '\n'.join(out_lines), params


# ============================================================
#  공개 API
# ============================================================
def _db_error(e: Exception, compiled: str, kind: str) -> HiveError:
    trace_log('[DB][%s] %s\nSQL: %s' % (kind, e, compiled), force=True)
    msg = str(e).lower()
    if 'readonly' in msg or 'unable to open' in msg or 'disk i/o' in msg:
        return HiveError('데이터베이스에 쓸 수 없습니다. db 디렉터리와 DB 파일의 쓰기 권한을 확인하세요.')
    return HiveError('데이터베이스 처리 중 오류가 발생했습니다.')


def get_sql(sql: str, params: dict = None) -> list:
    """SELECT → 행 배열(list[dict])"""
    compiled, params = compile_sql_template(sql, params or {})
    try:
        cur = get_connection().execute(compiled, params)
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error as e:
        raise _db_error(e, compiled, 'SELECT')


def set_sql(sql: str, params: dict = None) -> int:
    """INSERT / UPDATE / DELETE → 영향 행 수"""
    compiled, params = compile_sql_template(sql, params or {})
    conn = get_connection()
    try:
        cur = conn.execute(compiled, params)
        conn.commit()
        return cur.rowcount
    except sqlite3.Error as e:
        conn.rollback()
        raise _db_error(e, compiled, 'SET')


def get_link(sql: str, params: dict = None):
    """첫 행 첫 열 단일 값 반환"""
    rows = get_sql(sql, params)
    if not rows:
        return None
    first = rows[0]
    return next(iter(first.values())) if first else None


def get_count(sql: str, params: dict, lines: int) -> int:
    """전체 페이지 수 반환 (페이징용)"""
    total = get_link('SELECT COUNT(*) AS cnt FROM (%s) t' % sql, params) or 0
    return math.ceil(int(total) / lines) if lines > 0 else 0


def csv_sql(sql: str, params: dict = None, delim: str = ',') -> str:
    """SELECT 결과를 CSV 문자열로 반환"""
    rows = get_sql(sql, params)
    if not rows:
        return ''
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator='\n')
    w.writerow(rows[0].keys())
    for row in rows:
        w.writerow(row.values())
    return buf.getvalue()
