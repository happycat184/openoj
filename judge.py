"""OpenOJ 评测引擎：真实编译 / 执行 C、C++、Python 代码。

说明：本引擎面向本机或可信内网环境，使用超时与内存采样进行限制，
并不构成安全沙箱。请勿对不可信用户开放公网服务。
"""

import ctypes
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
COMPILE_TIMEOUT = 15
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RUN_OUTPUT_LIMIT = 64 * 1024
RUN_SLOTS = 2

SOURCE_NAMES = {
    "c": "main.c",
    "cpp": "main.cpp",
    "python": "main.py",
}

try:
    WORKER_COUNT = max(1, min(8, int(os.environ.get("OPENOJ_JUDGE_WORKERS", "2"))))
except ValueError:
    WORKER_COUNT = 2

_JUDGE_QUEUE = queue.Queue()
_QUEUE_LOCK = threading.Lock()
_RUN_SLOTS = threading.BoundedSemaphore(RUN_SLOTS)
_QUEUED_IDS = set()
_RUNNING_IDS = set()
_WORKERS = []
_WORKERS_LOCK = threading.Lock()

_CHILD_ENV = os.environ.copy()
_CHILD_ENV["PYTHONIOENCODING"] = "utf-8"
_CHILD_ENV["PYTHONUTF8"] = "1"
_CHILD_ENV["PYTHONDONTWRITEBYTECODE"] = "1"


# ---------------------------------------------------------------- memory

if os.name == "nt":
    import ctypes.wintypes as _wintypes

    class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", _wintypes.DWORD),
            ("PageFaultCount", _wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        _psapi = ctypes.WinDLL("psapi", use_last_error=True)
        _GetProcessMemoryInfo = _psapi.GetProcessMemoryInfo
        _GetProcessMemoryInfo.argtypes = [
            _wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            _wintypes.DWORD,
        ]
        _GetProcessMemoryInfo.restype = _wintypes.BOOL
    except OSError:
        _GetProcessMemoryInfo = None
else:
    _GetProcessMemoryInfo = None


def _peak_memory_kb(proc):
    """读取子进程的峰值常驻内存（KB），读取失败返回 0。"""
    if os.name == "nt":
        if _GetProcessMemoryInfo is None:
            return 0.0
        try:
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if _GetProcessMemoryInfo(
                int(proc._handle), ctypes.byref(counters), counters.cb
            ):
                return counters.PeakWorkingSetSize / 1024.0
        except Exception:
            return 0.0
        return 0.0

    # POSIX：优先读取 /proc 中的峰值（VmHWM）
    try:
        with open(f"/proc/{proc.pid}/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return float(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0.0


# ---------------------------------------------------------------- process helpers

def _kill_process(proc):
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _normalize_output(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.lstrip("﻿")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _outputs_match(actual, expected):
    return _normalize_output(actual) == _normalize_output(expected)


def _read_stderr_text(stderr_path, limit=20000):
    try:
        with open(stderr_path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _has_python_traceback(stderr_path):
    return "Traceback (most recent call last):" in _read_stderr_text(stderr_path)


def _run_case(command, workdir, input_path, output_path, stderr_path,
              time_limit_ms, memory_limit_kb):
    """运行单个测试点，返回 (killed_reason, returncode, time_ms, peak_kb)。"""
    peak_kb = 0.0
    killed = None
    killed_at_ms = None

    with open(input_path, "rb") as fin, open(output_path, "wb") as fout, \
            open(stderr_path, "wb") as ferr:
        proc = subprocess.Popen(
            command,
            cwd=workdir,
            stdin=fin,
            stdout=fout,
            stderr=ferr,
            env=_CHILD_ENV,
            creationflags=CREATE_NO_WINDOW,
        )
        # 进程创建可能被安全软件扫描阻塞数秒，计时从创建完成后开始，
        # 避免把环境开销计入被测程序运行时间。
        start = time.perf_counter()
        try:
            while True:
                returncode = proc.poll()
                memory = _peak_memory_kb(proc)
                if memory > peak_kb:
                    peak_kb = memory
                elapsed_ms = (time.perf_counter() - start) * 1000.0

                if returncode is not None:
                    break
                if memory_limit_kb and peak_kb > memory_limit_kb:
                    killed = "MLE"
                    killed_at_ms = elapsed_ms
                    _kill_process(proc)
                    break
                if elapsed_ms > time_limit_ms:
                    killed = "TLE"
                    killed_at_ms = elapsed_ms
                    _kill_process(proc)
                    break
                time.sleep(0.005)

            memory = _peak_memory_kb(proc)
            if memory > peak_kb:
                peak_kb = memory

            if proc.poll() is None:
                proc.wait()
        finally:
            if proc.poll() is None:
                _kill_process(proc)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

    elapsed_ms = (time.perf_counter() - start) * 1000.0

    if killed is None and memory_limit_kb and peak_kb > memory_limit_kb:
        killed = "MLE"
        killed_at_ms = elapsed_ms
    if killed is None and elapsed_ms > time_limit_ms:
        killed = "TLE"
        killed_at_ms = elapsed_ms

    reported_ms = killed_at_ms if killed_at_ms is not None else elapsed_ms
    return killed, proc.returncode, reported_ms, peak_kb


def _run_compile(command, workdir):
    try:
        proc = subprocess.run(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=COMPILE_TIMEOUT,
            env=_CHILD_ENV,
            creationflags=CREATE_NO_WINDOW,
        )
        output = (proc.stdout or b"").decode("utf-8", "replace")
        return proc.returncode == 0, output
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        return False, raw.decode("utf-8", "replace") + "\n编译超时。"
    except FileNotFoundError:
        return False, f"找不到编译器或解释器：{command[0]}"
    except OSError as exc:
        return False, f"无法启动编译器：{exc}"


def _build_commands(language, workdir):
    """返回 (编译命令或 None, 运行命令)。"""
    if language == "c":
        exe_name = "main.exe" if os.name == "nt" else "main"
        compile_cmd = ["gcc", "-O2", "-std=c11", "-pipe", "-o", exe_name, "main.c", "-lm"]
        return compile_cmd, [os.path.join(workdir, exe_name)]
    if language == "cpp":
        exe_name = "main.exe" if os.name == "nt" else "main"
        compile_cmd = ["g++", "-O2", "-std=c++17", "-pipe", "-o", exe_name, "main.cpp", "-lm"]
        return compile_cmd, [os.path.join(workdir, exe_name)]
    if language == "python":
        syntax_check = [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "compile(open('main.py', encoding='utf-8').read(), 'main.py', 'exec')",
        ]
        run_cmd = [sys.executable, "-I", "-B", "main.py"]
        return syntax_check, run_cmd
    return None, None


def _finish(conn, submission_id, status, time_ms, memory_kb, note=""):
    conn.execute(
        """
        UPDATE submissions
        SET status = ?, time_ms = ?, memory_kb = ?, compile_output = ?,
            judged_at = ?
        WHERE id = ?
        """,
        (status, round(time_ms, 2), round(memory_kb, 2), note, db.now_str(), submission_id),
    )
    conn.commit()


def _read_limited(path, limit=RUN_OUTPUT_LIMIT):
    """读取文本文件并截断到 limit 字节，返回 (text, truncated)。"""
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return "", False
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", "replace"), truncated


def run_custom(language, source, input_data, time_limit_ms, memory_limit_kb,
               expected_output=None):
    """在临时目录中编译并运行一次代码，供 IDE 自测使用。

    expected_output 为 None 时只运行不比对，状态为 OK；
    提供期望输出时，按行比对得到 AC / WA。结果不写入数据库。
    """
    result = {
        "status": "ULE",
        "time_ms": 0.0,
        "memory_kb": 0.0,
        "stdout": "",
        "stderr": "",
        "compile_output": "",
        "expected": expected_output or "",
        "truncated": False,
    }

    source_name = SOURCE_NAMES.get(language)
    if source_name is None:
        result["compile_output"] = f"不支持的语言：{language}"
        return result

    with _RUN_SLOTS:
        os.makedirs(WORK_DIR, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix="run_", dir=WORK_DIR)
        try:
            with open(os.path.join(workdir, source_name), "w",
                      encoding="utf-8", newline="\n") as handle:
                handle.write(source)

            compile_cmd, run_cmd = _build_commands(language, workdir)
            if compile_cmd is not None:
                ok, output = _run_compile(compile_cmd, workdir)
                if not ok:
                    result["status"] = "CE"
                    result["compile_output"] = output.strip()[-10000:] or "编译失败。"
                    return result

            input_path = os.path.join(workdir, "run.in")
            output_path = os.path.join(workdir, "run.out")
            stderr_path = os.path.join(workdir, "run.err")
            with open(input_path, "wb") as handle:
                handle.write(input_data.encode("utf-8"))

            killed, returncode, elapsed_ms, peak_kb = _run_case(
                run_cmd,
                workdir,
                input_path,
                output_path,
                stderr_path,
                time_limit_ms,
                memory_limit_kb,
            )

            stdout, out_truncated = _read_limited(output_path)
            stderr, err_truncated = _read_limited(stderr_path)
            result["time_ms"] = round(elapsed_ms, 2)
            result["memory_kb"] = round(peak_kb, 2)
            result["stdout"] = stdout.replace("\r\n", "\n").replace("\r", "\n")
            result["stderr"] = stderr.replace("\r\n", "\n").replace("\r", "\n")
            result["truncated"] = out_truncated or err_truncated

            if killed in ("TLE", "MLE"):
                result["status"] = killed
            elif returncode != 0:
                result["status"] = "ULE"
            elif expected_output is None:
                result["status"] = "OK"
            else:
                result["status"] = (
                    "AC" if _outputs_match(stdout, expected_output) else "WA"
                )
            return result
        except Exception as exc:  # 自测失败不应让接口 500
            traceback.print_exc()
            result["status"] = "ULE"
            result["compile_output"] = f"运行内部错误：{exc}"
            return result
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def judge_submission(submission_id):
    conn = None
    workdir = None
    try:
        conn = db.connect()
        submission = conn.execute(
            """
            SELECT s.*, p.time_limit_ms, p.memory_limit_kb
            FROM submissions s
            JOIN problems p ON p.id = s.problem_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()
        if submission is None:
            return

        conn.execute("UPDATE submissions SET status = 'JUDGING' WHERE id = ?", (submission_id,))
        conn.commit()

        cases = conn.execute(
            "SELECT * FROM test_cases WHERE problem_id = ? ORDER BY case_no ASC",
            (submission["problem_id"],),
        ).fetchall()
        if not cases:
            _finish(conn, submission_id, "ULE", 0, 0, "该题目暂无测试数据，无法评测。")
            return

        language = submission["language"]
        source_name = SOURCE_NAMES.get(language)
        if source_name is None:
            _finish(conn, submission_id, "ULE", 0, 0, f"不支持的语言：{language}")
            return

        os.makedirs(WORK_DIR, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix=f"sub_{submission_id}_", dir=WORK_DIR)

        with open(os.path.join(workdir, source_name), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(submission["source_code"])

        compile_cmd, run_cmd = _build_commands(language, workdir)
        if compile_cmd is not None:
            ok, output = _run_compile(compile_cmd, workdir)
            if not ok:
                note = output.strip()[-10000:] or "编译失败。"
                _finish(conn, submission_id, "CE", 0, 0, note)
                return

        conn.execute("DELETE FROM submission_cases WHERE submission_id = ?", (submission_id,))
        conn.commit()

        overall = None
        max_time = 0.0
        max_memory = 0.0
        runtime_note = ""

        for case in cases:
            case_no = case["case_no"]
            input_path = os.path.join(workdir, f"case_{case_no}.in")
            output_path = os.path.join(workdir, f"case_{case_no}.out")
            stderr_path = os.path.join(workdir, f"case_{case_no}.err")
            with open(input_path, "wb") as handle:
                handle.write(case["input_data"].encode("utf-8"))

            killed, returncode, elapsed_ms, peak_kb = _run_case(
                run_cmd,
                workdir,
                input_path,
                output_path,
                stderr_path,
                submission["time_limit_ms"],
                submission["memory_limit_kb"],
            )

            if killed == "MLE":
                status = "MLE"
            elif killed == "TLE":
                status = "TLE"
            elif returncode != 0:
                if language == "python" and _has_python_traceback(stderr_path):
                    status = "CE"
                    if not runtime_note:
                        stderr_text = _read_stderr_text(stderr_path, limit=8000)
                        runtime_note = (
                            f"测试点 #{case_no} 运行异常（Traceback）：\n{stderr_text}"
                        )
                else:
                    status = "ULE"
            else:
                try:
                    with open(output_path, "r", encoding="utf-8", errors="replace") as handle:
                        actual = handle.read()
                except OSError:
                    actual = ""
                status = "AC" if _outputs_match(actual, case["output_data"]) else "WA"

            max_time = max(max_time, elapsed_ms)
            max_memory = max(max_memory, peak_kb)
            if status != "AC" and overall is None:
                overall = status

            conn.execute(
                """
                INSERT INTO submission_cases
                    (submission_id, case_no, status, time_ms, memory_kb)
                VALUES (?, ?, ?, ?, ?)
                """,
                (submission_id, case_no, status, round(elapsed_ms, 2), round(peak_kb, 2)),
            )
            conn.commit()

        final_status = overall or "AC"
        _finish(conn, submission_id, final_status, max_time, max_memory, runtime_note)

    except Exception as exc:  # 评测线程不能静默失败
        traceback.print_exc()
        try:
            if conn is not None:
                conn.rollback()
                _finish(conn, submission_id, "ULE", 0, 0, f"评测内部错误：{exc}")
        except Exception:
            traceback.print_exc()
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _worker_loop():
    while True:
        submission_id = _JUDGE_QUEUE.get()
        try:
            with _QUEUE_LOCK:
                _QUEUED_IDS.discard(submission_id)
                _RUNNING_IDS.add(submission_id)
            judge_submission(submission_id)
        except Exception:
            traceback.print_exc()
        finally:
            with _QUEUE_LOCK:
                _RUNNING_IDS.discard(submission_id)
            _JUDGE_QUEUE.task_done()


def _ensure_workers():
    with _WORKERS_LOCK:
        if _WORKERS:
            return
        for index in range(WORKER_COUNT):
            worker = threading.Thread(
                target=_worker_loop,
                daemon=True,
                name=f"judge-worker-{index + 1}",
            )
            worker.start()
            _WORKERS.append(worker)


def start_judge(submission_id):
    """Enqueue a submission. Returns False if it is already queued/running."""
    _ensure_workers()
    with _QUEUE_LOCK:
        if submission_id in _QUEUED_IDS or submission_id in _RUNNING_IDS:
            return False
        _QUEUED_IDS.add(submission_id)
    _JUDGE_QUEUE.put(submission_id)
    return True


def queue_stats():
    with _QUEUE_LOCK:
        queued = len(_QUEUED_IDS)
        running = len(_RUNNING_IDS)
    return {
        "workers": WORKER_COUNT,
        "queued": queued,
        "running": running,
        "pending": _JUDGE_QUEUE.qsize(),
    }
