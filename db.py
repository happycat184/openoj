"""OpenOJ 数据层：SQLite 初始化、示例数据与查询封装。"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("OPENOJ_DB", os.path.join(BASE_DIR, "openoj.db"))

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    input_format    TEXT NOT NULL DEFAULT '',
    output_format   TEXT NOT NULL DEFAULT '',
    sample_input    TEXT NOT NULL DEFAULT '',
    sample_output   TEXT NOT NULL DEFAULT '',
    hint            TEXT NOT NULL DEFAULT '',
    time_limit_ms   INTEGER NOT NULL DEFAULT 1000,
    memory_limit_kb INTEGER NOT NULL DEFAULT 65536,
    is_visible      INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_cases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    case_no    INTEGER NOT NULL,
    input_data TEXT NOT NULL DEFAULT '',
    output_data TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_test_cases_problem ON test_cases(problem_id, case_no);

CREATE TABLE IF NOT EXISTS submissions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id     INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    language       TEXT NOT NULL,
    source_code    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    time_ms        REAL NOT NULL DEFAULT 0,
    memory_kb      REAL NOT NULL DEFAULT 0,
    compile_output TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    judged_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_submissions_problem ON submissions(problem_id);
CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_at);

CREATE TABLE IF NOT EXISTS submission_cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    case_no       INTEGER NOT NULL,
    status        TEXT NOT NULL,
    time_ms       REAL NOT NULL DEFAULT 0,
    memory_kb     REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_submission_cases_sub ON submission_cases(submission_id, case_no);
"""

SEED_PROBLEMS = [
    {
        "title": "A+B Problem",
        "description": (
            "输入两个整数 a 和 b，输出它们的和。\n\n"
            "这是一道用于熟悉 OpenOJ 提交方式的入门题，支持 C、C++ 与 Python。"
        ),
        "input_format": "一行，包含两个整数 a 和 b，以空格分隔。|a|, |b| ≤ 2×10^9。",
        "output_format": "输出一个整数，表示 a + b 的值。",
        "sample_input": "1 2\n",
        "sample_output": "3\n",
        "hint": "两数之和可能超过 32 位有符号整数范围，请使用 64 位整数（C/C++ 可使用 long long）。",
        "time_limit_ms": 1000,
        "memory_limit_kb": 65536,
        "tests": [
            ("1 2\n", "3\n"),
            ("-5 7\n", "2\n"),
            ("2000000000 2000000000\n", "4000000000\n"),
            ("0 0\n", "0\n"),
        ],
    },
    {
        "title": "斐波那契数列",
        "description": (
            "斐波那契数列定义如下：F(1) = 1，F(2) = 1，"
            "当 n ≥ 3 时，F(n) = F(n-1) + F(n-2)。\n\n"
            "给定 n，求 F(n)。"
        ),
        "input_format": "一个整数 n（1 ≤ n ≤ 50）。",
        "output_format": "输出 F(n)。",
        "sample_input": "10\n",
        "sample_output": "55\n",
        "hint": "n = 50 时结果超过 32 位整数范围，请使用 64 位整数。",
        "time_limit_ms": 1000,
        "memory_limit_kb": 65536,
        "tests": [
            ("1\n", "1\n"),
            ("2\n", "1\n"),
            ("3\n", "2\n"),
            ("10\n", "55\n"),
            ("50\n", "12586269025\n"),
        ],
    },
    {
        "title": "回文串判断",
        "description": (
            "给定一个由大小写字母和数字组成的字符串（不含空格），判断它是否为回文串。\n\n"
            "回文串是指正读和反读都相同的字符串，例如 level、12321。"
        ),
        "input_format": "一行字符串 s（1 ≤ |s| ≤ 1000）。",
        "output_format": "如果是回文串，输出 YES；否则输出 NO。",
        "sample_input": "level\n",
        "sample_output": "YES\n",
        "hint": "注意区分大小写，例如 Level 不是回文串。",
        "time_limit_ms": 1000,
        "memory_limit_kb": 65536,
        "tests": [
            ("level\n", "YES\n"),
            ("OpenOJ\n", "NO\n"),
            ("12321\n", "YES\n"),
            ("a\n", "YES\n"),
            ("abba\n", "YES\n"),
            ("abc\n", "NO\n"),
        ],
    },
    {
        "title": "最大子段和",
        "description": (
            "给定一个由 n 个整数组成的序列，求其连续子段的最大和。\n\n"
            "子段不能为空，且必须由序列中连续的一段元素组成。"
        ),
        "input_format": (
            "第一行一个整数 n（1 ≤ n ≤ 100000）。\n"
            "第二行包含 n 个整数，以空格分隔，每个整数的绝对值不超过 10^4。"
        ),
        "output_format": "输出一个整数，表示最大子段和。",
        "sample_input": "5\n-2 1 -3 4 -1\n",
        "sample_output": "4\n",
        "hint": "所有数都为负数时，答案是最小的那个负数。",
        "time_limit_ms": 1000,
        "memory_limit_kb": 65536,
        "tests": [
            ("5\n-2 1 -3 4 -1\n", "4\n"),
            ("5\n1 2 3 4 5\n", "15\n"),
            ("6\n-1 -2 -3 -4 -5 -6\n", "-1\n"),
            ("8\n-2 -3 4 -1 -2 1 5 -3\n", "7\n"),
        ],
    },
]


def init_db():
    """建表、写入默认管理员与示例题目。可重复调用。"""
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)

        admin = conn.execute(
            "SELECT id FROM users WHERE username = ?", (DEFAULT_ADMIN_USERNAME,)
        ).fetchone()
        if admin is None:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD), now_str()),
            )

        has_problem = conn.execute("SELECT COUNT(*) AS c FROM problems").fetchone()["c"]
        if has_problem == 0:
            for item in SEED_PROBLEMS:
                stamp = now_str()
                cur = conn.execute(
                    """
                    INSERT INTO problems
                        (title, description, input_format, output_format, sample_input,
                         sample_output, hint, time_limit_ms, memory_limit_kb, is_visible,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        item["title"],
                        item["description"],
                        item["input_format"],
                        item["output_format"],
                        item["sample_input"],
                        item["sample_output"],
                        item["hint"],
                        item["time_limit_ms"],
                        item["memory_limit_kb"],
                        stamp,
                        stamp,
                    ),
                )
                pid = cur.lastrowid
                for index, (input_data, output_data) in enumerate(item["tests"], start=1):
                    conn.execute(
                        "INSERT INTO test_cases (problem_id, case_no, input_data, output_data) VALUES (?, ?, ?, ?)",
                        (pid, index, input_data, output_data),
                    )


# ---------------------------------------------------------------- users

def get_user(uid):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def get_user_by_username(username):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def create_user(username, password_hash, role="user"):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, now_str()),
        )
        return cur.lastrowid


def update_user_password(uid, password_hash):
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, uid))


def set_user_role(uid, role):
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, uid))


def count_admins(exclude_uid=None):
    with get_conn() as conn:
        if exclude_uid is None:
            row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND id != ?", (exclude_uid,)
            ).fetchone()
        return row["c"]


def list_users_with_stats():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT u.id, u.username, u.role, u.created_at,
                   (SELECT COUNT(DISTINCT s.problem_id) FROM submissions s
                     WHERE s.user_id = u.id AND s.status = 'AC') AS solved,
                   (SELECT COUNT(*) FROM submissions s WHERE s.user_id = u.id) AS total
            FROM users u
            ORDER BY u.id ASC
            """
        ).fetchall()


# ---------------------------------------------------------------- problems

def get_problem(pid):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()


def list_problems(include_hidden=False):
    where = "" if include_hidden else "WHERE p.is_visible = 1"
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT p.*,
                   (SELECT COUNT(*) FROM submissions s WHERE s.problem_id = p.id) AS submission_count,
                   (SELECT COUNT(*) FROM submissions s WHERE s.problem_id = p.id AND s.status = 'AC') AS ac_count,
                   (SELECT COUNT(*) FROM test_cases t WHERE t.problem_id = p.id) AS case_count
            FROM problems p
            {where}
            ORDER BY p.id ASC
            """
        ).fetchall()


def problem_stats(pid):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM submissions WHERE problem_id = ?) AS submission_count,
                (SELECT COUNT(*) FROM submissions WHERE problem_id = ? AND status = 'AC') AS ac_count,
                (SELECT COUNT(*) FROM test_cases WHERE problem_id = ?) AS case_count
            """,
            (pid, pid, pid),
        ).fetchone()
    return dict(row)


def create_problem(data):
    stamp = now_str()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO problems
                (title, description, input_format, output_format, sample_input,
                 sample_output, hint, time_limit_ms, memory_limit_kb, is_visible,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"],
                data["description"],
                data["input_format"],
                data["output_format"],
                data["sample_input"],
                data["sample_output"],
                data["hint"],
                data["time_limit_ms"],
                data["memory_limit_kb"],
                data["is_visible"],
                stamp,
                stamp,
            ),
        )
        return cur.lastrowid


def import_problems(items):
    """在一个事务中导入题目及其测试点，失败时全部回滚。"""
    stamp = now_str()
    with get_conn() as conn:
        for item in items:
            cur = conn.execute(
                """
                INSERT INTO problems
                    (title, description, input_format, output_format, sample_input,
                     sample_output, hint, time_limit_ms, memory_limit_kb, is_visible,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["title"],
                    item["description"],
                    item["input_format"],
                    item["output_format"],
                    item["sample_input"],
                    item["sample_output"],
                    item["hint"],
                    item["time_limit_ms"],
                    item["memory_limit_kb"],
                    item["is_visible"],
                    stamp,
                    stamp,
                ),
            )
            pid = cur.lastrowid
            for index, case in enumerate(item["test_cases"], start=1):
                conn.execute(
                    """
                    INSERT INTO test_cases (problem_id, case_no, input_data, output_data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (pid, index, case["input"], case["output"]),
                )
    return len(items)


def update_problem(pid, data):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE problems SET
                title = ?, description = ?, input_format = ?, output_format = ?,
                sample_input = ?, sample_output = ?, hint = ?,
                time_limit_ms = ?, memory_limit_kb = ?, is_visible = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["description"],
                data["input_format"],
                data["output_format"],
                data["sample_input"],
                data["sample_output"],
                data["hint"],
                data["time_limit_ms"],
                data["memory_limit_kb"],
                data["is_visible"],
                now_str(),
                pid,
            ),
        )


def delete_problem(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM problems WHERE id = ?", (pid,))


def list_test_cases(pid):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM test_cases WHERE problem_id = ? ORDER BY case_no ASC", (pid,)
        ).fetchall()


def replace_test_cases(pid, rows):
    """rows: [(input_data, output_data), ...]，按顺序重排为 1..n。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM test_cases WHERE problem_id = ?", (pid,))
        for index, (input_data, output_data) in enumerate(rows, start=1):
            conn.execute(
                "INSERT INTO test_cases (problem_id, case_no, input_data, output_data) VALUES (?, ?, ?, ?)",
                (pid, index, input_data, output_data),
            )


# ---------------------------------------------------------------- submissions

def create_submission(user_id, problem_id, language, source_code):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO submissions
                (user_id, problem_id, language, source_code, status, time_ms, memory_kb,
                 compile_output, created_at)
            VALUES (?, ?, ?, ?, 'PENDING', 0, 0, '', ?)
            """,
            (user_id, problem_id, language, source_code, now_str()),
        )
        return cur.lastrowid


def get_submission(sid):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT s.*, u.username, p.title AS problem_title,
                   p.time_limit_ms, p.memory_limit_kb
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            JOIN problems p ON p.id = s.problem_id
            WHERE s.id = ?
            """,
            (sid,),
        ).fetchone()


def list_submissions(page=1, per_page=20, problem_id=None, user_id=None):
    conditions = []
    params = []
    if problem_id is not None:
        conditions.append("s.problem_id = ?")
        params.append(problem_id)
    if user_id is not None:
        conditions.append("s.user_id = ?")
        params.append(user_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM submissions s {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT s.*, u.username, p.title AS problem_title
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            JOIN problems p ON p.id = s.problem_id
            {where}
            ORDER BY s.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, (page - 1) * per_page],
        ).fetchall()
    return rows, total


def get_submission_cases(sid):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM submission_cases WHERE submission_id = ? ORDER BY case_no ASC", (sid,)
        ).fetchall()


def user_problem_statuses(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT problem_id, status FROM submissions WHERE user_id = ?", (user_id,)
        ).fetchall()
    solved = set()
    attempted = set()
    for row in rows:
        attempted.add(row["problem_id"])
        if row["status"] == "AC":
            solved.add(row["problem_id"])
    return solved, attempted


def user_stats(user_id):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT problem_id) AS attempted,
                   COUNT(DISTINCT CASE WHEN status = 'AC' THEN problem_id END) AS solved,
                   SUM(CASE WHEN status = 'AC' THEN 1 ELSE 0 END) AS ac_total
            FROM submissions WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return {
        "total": row["total"] or 0,
        "attempted": row["attempted"] or 0,
        "solved": row["solved"] or 0,
        "ac_total": row["ac_total"] or 0,
    }


def solved_problems(user_id):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.title, MIN(s.created_at) AS solved_at
            FROM submissions s
            JOIN problems p ON p.id = s.problem_id
            WHERE s.user_id = ? AND s.status = 'AC'
            GROUP BY p.id, p.title
            ORDER BY solved_at ASC
            """,
            (user_id,),
        ).fetchall()


def leaderboard():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT u.id, u.username, u.role, u.created_at,
                   (SELECT COUNT(DISTINCT s.problem_id) FROM submissions s
                     WHERE s.user_id = u.id AND s.status = 'AC') AS solved,
                   (SELECT COUNT(*) FROM submissions s WHERE s.user_id = u.id) AS total,
                   (SELECT COUNT(*) FROM submissions s
                     WHERE s.user_id = u.id AND s.status = 'AC') AS ac_total
            FROM users u
            ORDER BY solved DESC, total ASC, u.username ASC
            """
        ).fetchall()


def site_stats():
    with get_conn() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        problems = conn.execute(
            "SELECT COUNT(*) AS c FROM problems WHERE is_visible = 1"
        ).fetchone()["c"]
        submissions = conn.execute("SELECT COUNT(*) AS c FROM submissions").fetchone()["c"]
        all_problems = conn.execute("SELECT COUNT(*) AS c FROM problems").fetchone()["c"]
    return {
        "users": users,
        "problems": problems,
        "all_problems": all_problems,
        "submissions": submissions,
    }


def recover_stale_submissions():
    """服务停止时仍在评测中的提交，启动后标记为未知错误。"""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE submissions
            SET status = 'ULE', judged_at = ?,
                compile_output = CASE WHEN compile_output = ''
                    THEN '评测进程被中断（服务重启）。' ELSE compile_output END
            WHERE status IN ('PENDING', 'JUDGING')
            """,
            (now_str(),),
        )
