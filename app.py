"""OpenOJ — 基于 Flask 的在线评测系统。

启动：python app.py
默认地址：http://127.0.0.1:5000
"""

import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markdown_it import MarkdownIt
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

import db
import judge

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "OPENOJ_SECRET_KEY", "openoj-local-dev-secret-change-me"
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["PER_PAGE"] = 20
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

DIFFICULTIES = {
    "入门": {"slug": "entry", "order": 1},
    "简单": {"slug": "easy", "order": 2},
    "中等": {"slug": "medium", "order": 3},
    "困难": {"slug": "hard", "order": 4},
}
DIFFICULTY_NAMES = list(DIFFICULTIES)
DEFAULT_DIFFICULTY = "简单"

_markdown = MarkdownIt(
    "commonmark",
    {"html": False, "breaks": True, "linkify": False, "typographer": False},
)
_markdown.enable("table")
_markdown.enable("strikethrough")


def render_markdown(text):
    return Markup(_markdown.render(text or ""))


app.jinja_env.filters["markdown"] = render_markdown
app.jinja_env.filters["difficulty_slug"] = lambda value: DIFFICULTIES.get(
    value, DIFFICULTIES[DEFAULT_DIFFICULTY]
)["slug"]


def _detect_version(command, prefix):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
            creationflags=judge.CREATE_NO_WINDOW,
        )
        text = (result.stdout or b"").decode("utf-8", "replace").strip()
        first = text.splitlines()[0].strip() if text else ""
        return f"{prefix} {first}" if first else prefix
    except Exception:
        return prefix


LANGUAGE_INFO = {
    "c": {
        "label": "C",
        "runtime": _detect_version(["gcc", "-dumpversion"], "GCC"),
    },
    "cpp": {
        "label": "C++",
        "runtime": _detect_version(["g++", "-dumpversion"], "G++"),
    },
    "python": {
        "label": "Python",
        "runtime": "Python %d.%d.%d" % sys.version_info[:3],
    },
}

VERDICTS = {
    "AC": {"label": "通过", "en": "Accepted", "color": "green"},
    "WA": {"label": "答案错误", "en": "Wrong Answer", "color": "red"},
    "TLE": {"label": "超时", "en": "Time Limit Exceeded", "color": "black"},
    "MLE": {"label": "超内存", "en": "Memory Limit Exceeded", "color": "black"},
    "ULE": {"label": "未知错误", "en": "Unknown Error", "color": "black"},
    "CE": {"label": "编译错误", "en": "Compilation Error", "color": "black"},
    "PENDING": {"label": "等待评测", "en": "Pending", "color": "muted"},
    "JUDGING": {"label": "评测中", "en": "Judging", "color": "muted"},
}

PROBLEM_DEFAULTS = {
    "bank_id": None,
    "title": "",
    "difficulty": DEFAULT_DIFFICULTY,
    "description": "",
    "input_format": "",
    "output_format": "",
    "sample_input": "",
    "sample_output": "",
    "hint": "",
    "time_limit_ms": 1000,
    "memory_limit_kb": 65536,
    "is_visible": 1,
}

BANK_DEFAULTS = {
    "name": "",
    "description": "",
}


# ---------------------------------------------------------------- helpers

def _csrf_token():
    return session.get("csrf_token", "")


@app.before_request
def _prepare_session():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = db.get_user(user_id)
        if user is None:
            session.pop("user_id", None)
        else:
            g.user = user


@app.before_request
def _check_csrf():
    if request.method == "POST":
        expected = session.get("csrf_token")
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not submitted or not secrets.compare_digest(expected, submitted):
            abort(400, description="表单已过期，请刷新页面后重试。")


@app.context_processor
def _inject_globals():
    return {
        "verdicts": VERDICTS,
        "languages": LANGUAGE_INFO,
        "difficulties": DIFFICULTIES,
        "difficulty_names": DIFFICULTY_NAMES,
        "default_difficulty": DEFAULT_DIFFICULTY,
        "discussion_kinds": DISCUSSION_KINDS,
        "csrf_token": _csrf_token,
    }


@app.after_request
def _security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("请先登录后再进行操作。", "error")
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=target))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("请先登录后再进行操作。", "error")
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _safe_next(target):
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _parse_positive_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum or number > maximum:
        return default
    return number


def _read_upload(file_storage):
    data = file_storage.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        abort(400, description="测试点文件过大（上限 4 MB）。")
    return data.decode("utf-8", "replace")


def _problem_form_data():
    """从表单读取并校验题目字段，返回 (data, errors)。"""
    raw = {
        "bank_id": request.form.get("bank_id", "").strip(),
        "title": request.form.get("title", "").strip(),
        "difficulty": request.form.get("difficulty", DEFAULT_DIFFICULTY).strip(),
        "description": request.form.get("description", ""),
        "input_format": request.form.get("input_format", ""),
        "output_format": request.form.get("output_format", ""),
        "sample_input": request.form.get("sample_input", ""),
        "sample_output": request.form.get("sample_output", ""),
        "hint": request.form.get("hint", ""),
        "time_limit_ms": request.form.get("time_limit_ms", "").strip(),
        "memory_limit_kb": request.form.get("memory_limit_kb", "").strip(),
        "is_visible": 1 if request.form.get("is_visible") else 0,
    }
    errors = []

    try:
        bank_id = int(raw["bank_id"])
    except (TypeError, ValueError):
        bank_id = None
    if bank_id is None or db.get_bank(bank_id) is None:
        errors.append("请选择有效的目标题库。")
        bank_id = None

    if not raw["title"]:
        errors.append("题目标题不能为空。")
    elif len(raw["title"]) > 200:
        errors.append("题目标题不能超过 200 个字符。")

    if raw["difficulty"] not in DIFFICULTIES:
        errors.append("请选择有效的题目难度。")
        raw["difficulty"] = DEFAULT_DIFFICULTY

    time_limit = _parse_positive_int(raw["time_limit_ms"], 1000, 100, 60000)
    if str(time_limit) != raw["time_limit_ms"]:
        errors.append("时间限制需为 100–60000 之间的整数（毫秒）。")
    memory_limit = _parse_positive_int(raw["memory_limit_kb"], 65536, 1024, 1048576)
    if str(memory_limit) != raw["memory_limit_kb"]:
        errors.append("内存限制需为 1024–1048576 之间的整数（KB）。")

    data = dict(raw)
    data["bank_id"] = bank_id
    data["time_limit_ms"] = time_limit
    data["memory_limit_kb"] = memory_limit
    return data, errors


def _bank_form_data():
    """从表单读取并校验题库字段，返回 (data, errors)。"""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    errors = []
    if not name:
        errors.append("题库名称不能为空。")
    elif len(name) > 100:
        errors.append("题库名称不能超过 100 个字符。")
    if len(description) > 2000:
        errors.append("题库简介不能超过 2000 个字符。")
    return {"name": name, "description": description}, errors


MAX_IMPORT_PROBLEMS = 500
MAX_IMPORT_TEST_CASES = 10000
MAX_IMPORT_BYTES = 8 * 1024 * 1024

IMPORT_SAMPLE = {
    "format": "openoj-problem-bank",
    "version": 1,
    "problems": [
        {
            "title": "导入示例：A+B",
            "difficulty": "入门",
            "description": "输入两个整数 a 和 b，输出它们的和。",
            "input_format": "一行，包含两个整数 a 和 b，以空格分隔。",
            "output_format": "输出一个整数，表示 a + b。",
            "sample_input": "1 2\n",
            "sample_output": "3\n",
            "hint": "两数之和可能超过 32 位整数范围。",
            "time_limit_ms": 1000,
            "memory_limit_kb": 65536,
            "is_visible": True,
            "test_cases": [
                {"input": "1 2\n", "output": "3\n"},
                {"input": "-5 7\n", "output": "2\n"},
            ],
        },
        {
            "title": "导入示例：回文串判断",
            "difficulty": "简单",
            "description": "给定一个不含空格的字符串，判断它是否为回文串。",
            "input_format": "一行字符串 s（1 ≤ |s| ≤ 1000）。",
            "output_format": "是回文串输出 YES，否则输出 NO。",
            "sample_input": "level\n",
            "sample_output": "YES\n",
            "hint": "",
            "time_limit_ms": 1000,
            "memory_limit_kb": 65536,
            "is_visible": True,
            "test_cases": [
                {"input": "level\n", "output": "YES\n"},
                {"input": "OpenOJ\n", "output": "NO\n"},
            ],
        },
    ],
}


def _parse_import_problem(raw, number, errors):
    if not isinstance(raw, dict):
        errors.append(f"第 {number} 道题：必须是一个 JSON 对象。")
        return None

    title_value = raw.get("title")
    title = title_value.strip() if isinstance(title_value, str) else ""
    label = f"第 {number} 道题" + (f"「{title}」" if title else "")
    if not title:
        errors.append(f"{label}：缺少 title 或标题为空。")
    elif len(title) > 200:
        errors.append(f"{label}：title 不能超过 200 个字符。")

    def text_field(key, default=""):
        value = raw.get(key, default)
        if value is None:
            return default
        if not isinstance(value, str):
            errors.append(f"{label}：{key} 必须是字符串。")
            return default
        return value

    description = text_field("description")
    input_format = text_field("input_format")
    output_format = text_field("output_format")
    sample_input = text_field("sample_input")
    sample_output = text_field("sample_output")
    hint = text_field("hint")

    time_limit = raw.get("time_limit_ms", 1000)
    if (
        isinstance(time_limit, bool)
        or not isinstance(time_limit, int)
        or not 100 <= time_limit <= 60000
    ):
        errors.append(f"{label}：time_limit_ms 需为 100–60000 的整数。")
        time_limit = 1000

    memory_limit = raw.get("memory_limit_kb", 65536)
    if (
        isinstance(memory_limit, bool)
        or not isinstance(memory_limit, int)
        or not 1024 <= memory_limit <= 1048576
    ):
        errors.append(f"{label}：memory_limit_kb 需为 1024–1048576 的整数。")
        memory_limit = 65536

    visible_value = raw.get("is_visible", True)
    if isinstance(visible_value, bool):
        is_visible = 1 if visible_value else 0
    elif visible_value in (0, 1):
        is_visible = int(visible_value)
    else:
        errors.append(f"{label}：is_visible 必须是布尔值或 0/1。")
        is_visible = 1

    difficulty_value = raw.get("difficulty", DEFAULT_DIFFICULTY)
    if not isinstance(difficulty_value, str):
        errors.append(f"{label}：difficulty 必须是字符串。")
        difficulty = DEFAULT_DIFFICULTY
    else:
        aliases = {
            "beginner": "入门", "easy": "简单", "medium": "中等", "hard": "困难",
            "入门": "入门", "简单": "简单", "中等": "中等", "困难": "困难",
        }
        difficulty = aliases.get(difficulty_value.strip().lower(), difficulty_value.strip())
        if difficulty not in DIFFICULTIES:
            errors.append(f"{label}：difficulty 必须是 入门/简单/中等/困难 之一。")
            difficulty = DEFAULT_DIFFICULTY

    cases_value = raw.get("test_cases")
    test_cases = []
    if not isinstance(cases_value, list) or not cases_value:
        errors.append(f"{label}：test_cases 必须是非空数组。")
    elif len(cases_value) > MAX_IMPORT_TEST_CASES:
        errors.append(
            f"{label}：单个题目最多支持 {MAX_IMPORT_TEST_CASES} 个测试点。"
        )
    else:
        for case_number, case in enumerate(cases_value, start=1):
            where = f"{label} 第 {case_number} 个测试点"
            if not isinstance(case, dict):
                errors.append(f"{where}：必须是一个 JSON 对象。")
                continue
            input_data = case["input"] if "input" in case else case.get("input_data")
            output_data = case["output"] if "output" in case else case.get("output_data")
            if not isinstance(input_data, str):
                errors.append(f"{where}：input 必须是字符串。")
                continue
            if not isinstance(output_data, str):
                errors.append(f"{where}：output 必须是字符串。")
                continue
            test_cases.append({"input": input_data, "output": output_data})

    return {
        "title": title,
        "difficulty": difficulty,
        "description": description,
        "input_format": input_format,
        "output_format": output_format,
        "sample_input": sample_input,
        "sample_output": sample_output,
        "hint": hint,
        "time_limit_ms": time_limit,
        "memory_limit_kb": memory_limit,
        "is_visible": is_visible,
        "test_cases": test_cases,
    }


def _parse_problem_bank(payload):
    errors = []
    if isinstance(payload, dict):
        if "problems" in payload:
            raw_problems = payload["problems"]
        elif "title" in payload:
            raw_problems = [payload]
        else:
            return [], ["JSON 根对象必须包含 problems 数组，或本身是一道题目。"]
    elif isinstance(payload, list):
        raw_problems = payload
    else:
        return [], ["JSON 根必须是题目对象、题目数组，或包含 problems 数组的对象。"]

    if not isinstance(raw_problems, list):
        return [], ["problems 必须是数组。"]
    if not raw_problems:
        return [], ["题库为空，没有可导入的题目。"]
    if len(raw_problems) > MAX_IMPORT_PROBLEMS:
        return [], [f"一次最多导入 {MAX_IMPORT_PROBLEMS} 道题目。"]

    items = []
    for index, raw in enumerate(raw_problems, start=1):
        item = _parse_import_problem(raw, index, errors)
        if item is not None:
            items.append(item)
    return items, errors


# ---------------------------------------------------------------- public pages

def _decorate_problem_rows(problems):
    solved, attempted = set(), set()
    if g.user is not None:
        solved, attempted = db.user_problem_statuses(g.user["id"])

    rows = []
    for problem in problems:
        item = dict(problem)
        item["ac_rate"] = (
            item["ac_count"] / item["submission_count"] * 100
            if item["submission_count"]
            else None
        )
        if item["id"] in solved:
            item["user_status"] = "solved"
        elif item["id"] in attempted:
            item["user_status"] = "attempted"
        else:
            item["user_status"] = None
        rows.append(item)
    return rows


def _problem_rows(bank_id=None):
    return _decorate_problem_rows(
        db.list_problems(include_hidden=False, bank_id=bank_id)
    )


@app.route("/")
def index():
    banks = db.list_banks()
    progress = db.user_bank_progress(g.user["id"]) if g.user is not None else {}

    bank_rows = []
    for bank_row in banks:
        item = dict(bank_row)
        user_progress = progress.get(bank_row["id"], {})
        item["solved"] = user_progress.get("solved", 0)
        item["attempted"] = user_progress.get("attempted", 0)
        bank_rows.append(item)

    random_rows = _decorate_problem_rows(db.random_problems(limit=10))
    return render_template(
        "index.html",
        banks=bank_rows,
        random_problems=random_rows,
        stats=db.site_stats(),
    )


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()[:100]
    if not query:
        return redirect(url_for("index"))

    difficulty = request.args.get("difficulty", "").strip()
    if difficulty not in DIFFICULTIES:
        difficulty = ""
    selected_bank_id = request.args.get("bank", type=int)
    selected_bank = db.get_bank(selected_bank_id) if selected_bank_id is not None else None
    if selected_bank is None:
        selected_bank_id = None

    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = app.config["PER_PAGE"]

    def fetch(target_page):
        return db.search_problems(
            query,
            page=target_page,
            per_page=per_page,
            difficulty=difficulty or None,
            bank_id=selected_bank_id,
        )

    rows, total = fetch(page)
    pages = max(1, math.ceil(total / per_page))
    if page > pages:
        page = pages
        rows, total = fetch(page)

    return render_template(
        "search.html",
        query=query,
        problems=_decorate_problem_rows(rows),
        total=total,
        page=page,
        pages=pages,
        banks=db.list_banks(),
        selected_bank=selected_bank,
        selected_difficulty=difficulty,
    )


@app.route("/bank/<int:bid>")
def bank(bid):
    bank_row = db.get_bank(bid)
    if bank_row is None:
        abort(404)

    difficulty = request.args.get("difficulty", "").strip()
    if difficulty not in DIFFICULTIES:
        difficulty = ""
    status = request.args.get("status", "").strip()
    if status not in ("solved", "attempted", "unsolved") or g.user is None:
        status = ""

    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = app.config["PER_PAGE"]

    def fetch(target_page):
        return db.query_problems(
            include_hidden=False,
            bank_id=bid,
            difficulty=difficulty or None,
            status=status or None,
            user_id=g.user["id"] if g.user is not None else None,
            page=target_page,
            per_page=per_page,
        )

    rows, total = fetch(page)
    pages = max(1, math.ceil(total / per_page))
    if page > pages:
        page = pages
        rows, total = fetch(page)

    return render_template(
        "bank.html",
        bank=bank_row,
        problems=_decorate_problem_rows(rows),
        total=total,
        page=page,
        pages=pages,
        selected_difficulty=difficulty,
        selected_status=status,
    )


@app.route("/problem/<int:pid>")
def problem(pid):
    row = db.get_problem(pid)
    if row is None:
        abort(404)
    if not row["is_visible"] and (g.user is None or g.user["role"] != "admin"):
        abort(404)

    stats = db.problem_stats(pid)
    ac_rate = (
        stats["ac_count"] / stats["submission_count"] * 100
        if stats["submission_count"]
        else None
    )
    return render_template(
        "problem.html",
        problem=row,
        stats=stats,
        ac_rate=ac_rate,
        discussion_count=db.discussion_count(pid),
        is_admin_view=bool(g.user is not None and g.user["role"] == "admin" and not row["is_visible"]),
    )


@app.route("/problem/<int:pid>/ide")
@login_required
def problem_ide(pid):
    row = db.get_problem(pid)
    if row is None:
        abort(404)
    if not row["is_visible"] and g.user["role"] != "admin":
        abort(404)

    stats = db.problem_stats(pid)
    ac_rate = (
        stats["ac_count"] / stats["submission_count"] * 100
        if stats["submission_count"]
        else None
    )
    return render_template("ide.html", problem=row, stats=stats, ac_rate=ac_rate)


DISCUSSION_KINDS = {"solution": "题解", "discussion": "讨论"}
DISCUSSION_TITLE_LIMIT = 120
DISCUSSION_CONTENT_LIMIT = 20000


def _visible_problem_or_404(pid):
    row = db.get_problem(pid)
    if row is None:
        abort(404)
    if not row["is_visible"] and (g.user is None or g.user["role"] != "admin"):
        abort(404)
    return row


def _discussion_or_404(did):
    discussion = db.get_discussion(did)
    if discussion is None:
        abort(404)
    _visible_problem_or_404(discussion["problem_id"])
    return discussion


@app.route("/problem/<int:pid>/discussions")
def discussions(pid):
    problem_row = _visible_problem_or_404(pid)
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = app.config["PER_PAGE"]
    rows, total = db.list_discussions(pid, page=page, per_page=per_page)
    pages = max(1, math.ceil(total / per_page))
    if page > pages:
        page = pages
        rows, total = db.list_discussions(pid, page=page, per_page=per_page)
    return render_template(
        "discussions.html",
        problem=problem_row,
        discussions=rows,
        total=total,
        page=page,
        pages=pages,
    )


@app.route("/problem/<int:pid>/discussions/new", methods=["GET", "POST"])
@login_required
def discussion_new(pid):
    problem_row = _visible_problem_or_404(pid)
    form_data = {"kind": "discussion", "title": "", "content": ""}
    if request.method == "POST":
        form_data = {
            "kind": request.form.get("kind", "discussion").strip(),
            "title": request.form.get("title", "").strip(),
            "content": request.form.get("content", "").strip(),
        }
        errors = []
        if form_data["kind"] not in DISCUSSION_KINDS:
            errors.append("请选择发布类型。")
        if not form_data["title"]:
            errors.append("标题不能为空。")
        elif len(form_data["title"]) > DISCUSSION_TITLE_LIMIT:
            errors.append(f"标题不能超过 {DISCUSSION_TITLE_LIMIT} 个字符。")
        if not form_data["content"]:
            errors.append("内容不能为空。")
        elif len(form_data["content"]) > DISCUSSION_CONTENT_LIMIT:
            errors.append(f"内容不能超过 {DISCUSSION_CONTENT_LIMIT} 个字符。")
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            did = db.create_discussion(
                pid, g.user["id"], form_data["kind"],
                form_data["title"], form_data["content"],
            )
            flash("发布成功。", "success")
            return redirect(url_for("discussion_detail", did=did))
    return render_template("discussion_form.html", problem=problem_row, form=form_data)


@app.route("/discussion/<int:did>")
def discussion_detail(did):
    discussion = _discussion_or_404(did)
    problem_row = db.get_problem(discussion["problem_id"])
    replies = db.list_replies(did)
    return render_template(
        "discussion.html",
        discussion=discussion,
        problem=problem_row,
        replies=replies,
        can_manage=bool(
            g.user is not None
            and (g.user["id"] == discussion["user_id"] or g.user["role"] == "admin")
        ),
    )


@app.route("/discussion/<int:did>/reply", methods=["POST"])
@login_required
def discussion_reply(did):
    discussion = _discussion_or_404(did)
    content = request.form.get("content", "").strip()
    if not content:
        flash("回复内容不能为空。", "error")
    elif len(content) > DISCUSSION_CONTENT_LIMIT:
        flash(f"回复不能超过 {DISCUSSION_CONTENT_LIMIT} 个字符。", "error")
    else:
        reply_id = db.create_reply(did, g.user["id"], content)
        flash("回复成功。", "success")
        return redirect(url_for("discussion_detail", did=did, _anchor=f"reply-{reply_id}"))
    return redirect(url_for("discussion_detail", did=did))


@app.route("/discussion/<int:did>/delete", methods=["POST"])
@login_required
def discussion_delete(did):
    discussion = _discussion_or_404(did)
    if g.user["id"] != discussion["user_id"] and g.user["role"] != "admin":
        abort(403)
    problem_id = discussion["problem_id"]
    db.delete_discussion(did)
    flash("主题已删除。", "success")
    return redirect(url_for("discussions", pid=problem_id))


@app.route("/discussion/reply/<int:rid>/delete", methods=["POST"])
@login_required
def discussion_reply_delete(rid):
    reply = db.get_reply(rid)
    if reply is None:
        abort(404)
    discussion = _discussion_or_404(reply["discussion_id"])
    if g.user["id"] != reply["user_id"] and g.user["role"] != "admin":
        abort(403)
    db.delete_reply(rid)
    flash("回复已删除。", "success")
    return redirect(url_for("discussion_detail", did=discussion["id"]))


@app.route("/submit", methods=["POST"])
@login_required
def submit():
    try:
        problem_id = int(request.form.get("problem_id", ""))
    except (TypeError, ValueError):
        abort(400, description="无效的题目编号。")

    target = db.get_problem(problem_id)
    if target is None or (
        not target["is_visible"] and g.user["role"] != "admin"
    ):
        abort(404)

    def fail(message):
        flash(message, "error")
        if request.form.get("source") == "ide":
            return redirect(url_for("problem_ide", pid=problem_id))
        return redirect(url_for("problem", pid=problem_id))

    if db.problem_stats(problem_id)["case_count"] == 0:
        return fail("该题目尚未配置测试点，暂时无法提交。")

    language = request.form.get("language", "").strip()
    if language not in LANGUAGE_INFO:
        return fail("请选择受支持的编程语言。")

    source = request.form.get("code", "")
    if not source.strip():
        return fail("代码不能为空。")
    if len(source) > 200 * 1024:
        return fail("代码长度超过限制（200 KB）。")

    submission_id = db.create_submission(g.user["id"], problem_id, language, source)
    judge.start_judge(submission_id)
    return redirect(url_for("submission", sid=submission_id))


@app.route("/submission/<int:sid>")
def submission(sid):
    row = db.get_submission(sid)
    if row is None:
        abort(404)
    cases = db.get_submission_cases(sid)
    return render_template("submission.html", submission=row, cases=cases)


@app.route("/api/submission/<int:sid>")
def api_submission(sid):
    row = db.get_submission(sid)
    if row is None:
        abort(404)
    cases = db.get_submission_cases(sid)
    return jsonify(
        {
            "id": row["id"],
            "status": row["status"],
            "finished": row["status"] not in ("PENDING", "JUDGING"),
            "time_ms": row["time_ms"],
            "memory_kb": row["memory_kb"],
            "cases": [
                {
                    "case_no": case["case_no"],
                    "status": case["status"],
                    "time_ms": case["time_ms"],
                    "memory_kb": case["memory_kb"],
                }
                for case in cases
            ],
        }
    )


@app.route("/submissions")
def submissions():
    page = max(1, request.args.get("page", 1, type=int) or 1)
    problem_id = request.args.get("problem", type=int)
    problem_row = db.get_problem(problem_id) if problem_id is not None else None

    username = request.args.get("user", "").strip()
    user_row = None
    if username:
        user_row = db.get_user_by_username(username)
        if user_row is None:
            abort(404)

    def fetch(target_page):
        return db.list_submissions(
            page=target_page,
            per_page=app.config["PER_PAGE"],
            problem_id=problem_id,
            user_id=user_row["id"] if user_row else None,
        )

    rows, total = fetch(page)
    pages = max(1, math.ceil(total / app.config["PER_PAGE"]))
    if page > pages:
        page = pages
        rows, total = fetch(page)

    return render_template(
        "submissions.html",
        submissions=rows,
        total=total,
        page=page,
        pages=pages,
        problem=problem_row,
        filter_user=user_row,
    )


@app.route("/user/<username>")
def user_profile(username):
    user = db.get_user_by_username(username)
    if user is None:
        abort(404)

    stats = db.user_stats(user["id"])
    solved = db.solved_problems(user["id"])
    rows, total = db.list_submissions(page=1, per_page=10, user_id=user["id"])
    ac_rate = stats["ac_total"] / stats["total"] * 100 if stats["total"] else None

    return render_template(
        "profile.html",
        profile_user=user,
        stats=stats,
        solved=solved,
        submissions=rows,
        total_submissions=total,
        ac_rate=ac_rate,
        is_self=bool(g.user is not None and g.user["id"] == user["id"]),
    )


@app.route("/profile")
@login_required
def profile():
    return redirect(url_for("user_profile", username=g.user["username"]))


@app.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not check_password_hash(g.user["password_hash"], current):
        flash("当前密码不正确。", "error")
    elif len(new_password) < 6:
        flash("新密码至少需要 6 个字符。", "error")
    elif new_password != confirm:
        flash("两次输入的新密码不一致。", "error")
    else:
        db.update_user_password(g.user["id"], generate_password_hash(new_password))
        flash("密码已更新。", "success")
    return redirect(url_for("user_profile", username=g.user["username"]))


@app.route("/leaderboard")
def leaderboard():
    rows = db.leaderboard()
    return render_template("leaderboard.html", rows=rows)


# ---------------------------------------------------------------- auth

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("index"))

    next_url = request.args.get("next") or request.form.get("next") or ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)
        if user is not None and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_hex(16)
            flash(f"欢迎回来，{user['username']}。", "success")
            target = _safe_next(next_url)
            return redirect(target or url_for("index"))
        flash("用户名或密码错误。", "error")

    return render_template("login.html", next_url=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if not USERNAME_RE.match(username):
            errors.append("用户名需为 3–20 位字母、数字或下划线。")
        if len(password) < 6:
            errors.append("密码至少需要 6 个字符。")
        if password != confirm:
            errors.append("两次输入的密码不一致。")

        if not errors:
            try:
                user_id = db.create_user(username, generate_password_hash(password))
            except sqlite3.IntegrityError:
                errors.append("该用户名已被占用。")
            else:
                session.clear()
                session["user_id"] = user_id
                session["csrf_token"] = secrets.token_hex(16)
                flash(f"注册成功，欢迎加入 OpenOJ，{username}。", "success")
                return redirect(url_for("index"))

        for error in errors:
            flash(error, "error")

    return render_template("register.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("已退出登录。", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------- admin

@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = db.site_stats()
    recent, _ = db.list_submissions(page=1, per_page=8)
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent=recent,
        judge_queue=judge.queue_stats(),
    )


@app.route("/admin/banks")
@admin_required
def admin_banks():
    return render_template("admin/banks.html", banks=db.list_banks())


@app.route("/admin/banks/new", methods=["GET", "POST"])
@admin_required
def admin_bank_new():
    form_data = dict(BANK_DEFAULTS)
    if request.method == "POST":
        form_data, errors = _bank_form_data()
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                db.create_bank(form_data["name"], form_data["description"])
            except sqlite3.IntegrityError:
                flash("该题库名称已存在。", "error")
            else:
                flash(f"题库「{form_data['name']}」已创建。", "success")
                return redirect(url_for("admin_banks"))
    return render_template("admin/bank_form.html", bank=form_data, mode="new")


@app.route("/admin/banks/<int:bid>/edit", methods=["GET", "POST"])
@admin_required
def admin_bank_edit(bid):
    row = db.get_bank(bid)
    if row is None:
        abort(404)

    form_data = dict(row)
    if request.method == "POST":
        form_data, errors = _bank_form_data()
        form_data["id"] = bid
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                db.update_bank(bid, form_data["name"], form_data["description"])
            except sqlite3.IntegrityError:
                flash("该题库名称已存在。", "error")
            else:
                flash("题库信息已保存。", "success")
                return redirect(url_for("admin_banks"))

    return render_template("admin/bank_form.html", bank=form_data, mode="edit")


@app.route("/admin/banks/<int:bid>/delete", methods=["POST"])
@admin_required
def admin_bank_delete(bid):
    row = db.get_bank(bid)
    if row is None:
        abort(404)

    if row["problem_count"] > 0:
        flash(
            f"题库「{row['name']}」下仍有 {row['problem_count']} 道题目，"
            "请先将题目移动到其他题库或删除。",
            "error",
        )
    elif db.site_stats()["banks"] <= 1:
        flash("至少需要保留一个题库。", "error")
    else:
        try:
            db.delete_bank(bid)
        except sqlite3.IntegrityError:
            flash("该题库下仍有题目，无法删除。", "error")
        else:
            flash(f"题库「{row['name']}」已删除。", "success")
    return redirect(url_for("admin_banks"))


@app.route("/admin/problems")
@admin_required
def admin_problems():
    bank_id = request.args.get("bank", type=int)
    selected_bank = db.get_bank(bank_id) if bank_id is not None else None
    if bank_id is not None and selected_bank is None:
        abort(404)
    difficulty = request.args.get("difficulty", "").strip()
    if difficulty not in DIFFICULTIES:
        difficulty = ""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = app.config["PER_PAGE"]

    def fetch(target_page):
        return db.query_problems(
            include_hidden=True,
            bank_id=bank_id,
            difficulty=difficulty or None,
            page=target_page,
            per_page=per_page,
        )

    rows, total = fetch(page)
    pages = max(1, math.ceil(total / per_page))
    if page > pages:
        page = pages
        rows, total = fetch(page)
    return render_template(
        "admin/problems.html",
        problems=rows,
        banks=db.list_banks(),
        selected_bank=selected_bank,
        selected_difficulty=difficulty,
        total=total,
        page=page,
        pages=pages,
    )


@app.route("/admin/problems/import", methods=["GET", "POST"])
@admin_required
def admin_problem_import():
    banks = db.list_banks()

    def render_import(raw_text="", selected_bank_id=None):
        return render_template(
            "admin/import.html",
            json_text=raw_text,
            banks=banks,
            selected_bank_id=selected_bank_id,
        )

    if request.method == "GET":
        requested = request.args.get("bank", type=int)
        requested_bank = db.get_bank(requested) if requested is not None else None
        selected_bank_id = (
            requested_bank["id"] if requested_bank else (banks[0]["id"] if banks else None)
        )
        return render_import("", selected_bank_id)

    try:
        target_bank_id = int(request.form.get("bank_id", ""))
    except (TypeError, ValueError):
        target_bank_id = None
    target_bank = db.get_bank(target_bank_id) if target_bank_id is not None else None
    if target_bank is None:
        flash("请选择有效的目标题库。", "error")
        return render_import("", None)

    selected_bank_id = target_bank["id"]
    upload = request.files.get("json_file")
    if upload is not None and upload.filename:
        data = upload.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            flash("JSON 文件超过 8 MB 限制。", "error")
            return render_import("", selected_bank_id)
        try:
            raw_text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("JSON 文件不是有效的 UTF-8 编码。", "error")
            return render_import("", selected_bank_id)
    else:
        raw_text = request.form.get("json_text", "")

    raw_text = raw_text.lstrip("﻿")
    if not raw_text.strip():
        flash("请上传 JSON 文件或粘贴 JSON 内容。", "error")
        return render_import(raw_text, selected_bank_id)

    if len(raw_text.encode("utf-8")) > MAX_IMPORT_BYTES:
        flash("JSON 内容超过 8 MB 限制。", "error")
        return render_import(raw_text, selected_bank_id)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        flash(
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}。",
            "error",
        )
        return render_import(raw_text, selected_bank_id)

    items, errors = _parse_problem_bank(payload)
    if errors:
        for message in errors[:10]:
            flash(message, "error")
        if len(errors) > 10:
            flash(f"还有 {len(errors) - 10} 个错误未显示，请修正后重试。", "error")
        return render_import(raw_text, selected_bank_id)

    try:
        count = db.import_problems(items, selected_bank_id)
    except Exception as exc:
        flash(f"导入失败：{exc}", "error")
        return render_import(raw_text, selected_bank_id)

    total_cases = sum(len(item["test_cases"]) for item in items)
    flash(
        f"成功将 {count} 道题目、{total_cases} 个测试点导入题库"
        f"「{target_bank['name']}」。",
        "success",
    )
    return redirect(url_for("admin_problems", bank=selected_bank_id))


@app.route("/admin/problems/import/sample")
@admin_required
def admin_problem_import_sample():
    data = json.dumps(IMPORT_SAMPLE, ensure_ascii=False, indent=2) + "\n"
    return Response(
        data,
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="openoj-problem-bank.json"'
        },
    )


@app.route("/admin/problems/new", methods=["GET", "POST"])
@admin_required
def admin_problem_new():
    banks = db.list_banks()
    form_data = dict(PROBLEM_DEFAULTS)
    if request.method == "GET":
        requested = request.args.get("bank", type=int)
        bank_ids = {bank["id"] for bank in banks}
        if requested in bank_ids:
            form_data["bank_id"] = requested
        elif banks:
            form_data["bank_id"] = banks[0]["id"]
    if request.method == "POST":
        form_data, errors = _problem_form_data()
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            problem_id = db.create_problem(form_data)
            flash("题目已创建，请继续添加测试点。", "success")
            return redirect(url_for("admin_testcases", pid=problem_id))
    return render_template(
        "admin/problem_form.html", problem=form_data, banks=banks, mode="new"
    )


@app.route("/admin/problems/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def admin_problem_edit(pid):
    row = db.get_problem(pid)
    if row is None:
        abort(404)

    banks = db.list_banks()
    form_data = dict(row)
    if request.method == "POST":
        form_data, errors = _problem_form_data()
        form_data["id"] = pid
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            db.update_problem(pid, form_data)
            flash("题目信息已保存。", "success")
            return redirect(url_for("admin_problems", bank=form_data["bank_id"]))

    return render_template(
        "admin/problem_form.html", problem=form_data, banks=banks, mode="edit"
    )


@app.route("/admin/problems/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_problem_delete(pid):
    row = db.get_problem(pid)
    if row is None:
        abort(404)
    db.delete_problem(pid)
    flash(f"题目 #{pid} 及其测试点、提交记录已删除。", "success")
    return redirect(url_for("admin_problems", bank=row["bank_id"]))


@app.route("/admin/problems/<int:pid>/testcases", methods=["GET", "POST"])
@admin_required
def admin_testcases(pid):
    problem_row = db.get_problem(pid)
    if problem_row is None:
        abort(404)

    if request.method == "POST":
        existing = db.list_test_cases(pid)
        rows = []
        for case in existing:
            case_id = case["id"]
            if request.form.get(f"delete_{case_id}"):
                continue
            input_data = request.form.get(f"input_{case_id}", case["input_data"])
            output_data = request.form.get(f"output_{case_id}", case["output_data"])
            input_file = request.files.get(f"infile_{case_id}")
            output_file = request.files.get(f"outfile_{case_id}")
            if input_file is not None and input_file.filename:
                input_data = _read_upload(input_file)
            if output_file is not None and output_file.filename:
                output_data = _read_upload(output_file)
            rows.append((input_data, output_data))

        new_inputs = request.form.getlist("new_input")
        new_outputs = request.form.getlist("new_output")
        new_input_files = request.files.getlist("new_input_file")
        new_output_files = request.files.getlist("new_output_file")
        for index, input_data in enumerate(new_inputs):
            output_data = new_outputs[index] if index < len(new_outputs) else ""
            if index < len(new_input_files):
                file_storage = new_input_files[index]
                if file_storage is not None and file_storage.filename:
                    input_data = _read_upload(file_storage)
            if index < len(new_output_files):
                file_storage = new_output_files[index]
                if file_storage is not None and file_storage.filename:
                    output_data = _read_upload(file_storage)
            rows.append((input_data, output_data))

        rows = [(input_data, output_data) for input_data, output_data in rows
                if input_data != "" or output_data != ""]
        db.replace_test_cases(pid, rows)
        flash(f"已保存 {len(rows)} 个测试点。", "success")
        return redirect(url_for("admin_testcases", pid=pid))

    cases = db.list_test_cases(pid)
    return render_template("admin/testcases.html", problem=problem_row, cases=cases)


@app.route("/admin/users")
@admin_required
def admin_users():
    users = db.list_users_with_stats()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/<int:uid>/role", methods=["POST"])
@admin_required
def admin_user_role(uid):
    target = db.get_user(uid)
    if target is None:
        abort(404)

    if uid == g.user["id"]:
        flash("不能修改自己的角色。", "error")
        return redirect(url_for("admin_users"))

    if target["role"] == "admin":
        if db.count_admins(exclude_uid=uid) == 0:
            flash("系统至少需要保留一名管理员。", "error")
            return redirect(url_for("admin_users"))
        db.set_user_role(uid, "user")
        flash(f"已将 {target['username']} 设为普通用户。", "success")
    else:
        db.set_user_role(uid, "admin")
        flash(f"已将 {target['username']} 设为管理员。", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/submissions/<int:sid>/rejudge", methods=["POST"])
@admin_required
def admin_rejudge(sid):
    row = db.get_submission(sid)
    if row is None:
        abort(404)
    if row["status"] in ("PENDING", "JUDGING"):
        flash("该提交正在评测中，请等待完成后再重新评测。", "error")
        return redirect(url_for("submission", sid=sid))

    with db.get_conn() as conn:
        conn.execute("DELETE FROM submission_cases WHERE submission_id = ?", (sid,))
        conn.execute(
            """
            UPDATE submissions
            SET status = 'PENDING', time_ms = 0, memory_kb = 0,
                compile_output = '', judged_at = NULL
            WHERE id = ?
            """,
            (sid,),
        )
    if judge.start_judge(sid):
        flash(f"提交 #{sid} 已重新加入评测队列。", "success")
    else:
        flash("该提交已在评测队列中。", "error")
    return redirect(url_for("submission", sid=sid))


# ---------------------------------------------------------------- errors

@app.errorhandler(400)
def error_bad_request(error):
    return render_template(
        "error.html", code=400, title="请求无效",
        message=getattr(error, "description", "请求无法处理。"),
    ), 400


@app.errorhandler(403)
def error_forbidden(error):
    return render_template(
        "error.html", code=403, title="没有权限",
        message="你的账号没有访问该页面的权限。",
    ), 403


@app.errorhandler(404)
def error_not_found(error):
    return render_template(
        "error.html", code=404, title="页面不存在",
        message="你访问的页面或资源不存在。",
    ), 404


@app.errorhandler(413)
def error_too_large(error):
    return render_template(
        "error.html", code=413, title="内容过大",
        message="上传的内容超过 16 MB 限制。",
    ), 413


@app.errorhandler(500)
def error_internal(error):
    return render_template(
        "error.html", code=500, title="服务器错误",
        message="服务器处理请求时发生了内部错误。",
    ), 500


db.init_db()
db.recover_stale_submissions()


if __name__ == "__main__":
    debug = os.environ.get("OPENOJ_DEBUG") == "1"
    app.run(
        host=os.environ.get("OPENOJ_HOST", "127.0.0.1"),
        port=int(os.environ.get("OPENOJ_PORT", "5000")),
        debug=debug,
        use_reloader=False,
    )
