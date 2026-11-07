/* OpenOJ IDE: CodeMirror editor, drafts, completion, auto-indent. */
(function () {
    "use strict";

    var textarea = document.getElementById("code-editor");
    var languageSelect = document.getElementById("language");
    var cursorLabel = document.getElementById("editor-cursor");
    var submitForm = document.getElementById("submit-form");
    if (!textarea || !languageSelect || typeof window.CodeMirror === "undefined") {
        return;
    }

    var MODES = {
        c: "text/x-csrc",
        cpp: "text/x-c++src",
        python: "python"
    };

    var KEYWORDS = {
        c: [
            "int", "return", "if", "else", "for", "while", "do", "switch", "case",
            "break", "continue", "char", "double", "float", "long", "short",
            "unsigned", "signed", "void", "const", "static", "struct", "union",
            "typedef", "enum", "sizeof", "extern", "register", "volatile", "goto",
            "inline", "restrict", "auto", "include", "define", "printf", "scanf",
            "puts", "putchar", "getchar", "gets", "malloc", "calloc", "realloc",
            "free", "memcpy", "memset", "strlen", "strcmp", "strcpy", "fopen",
            "fclose", "fgets", "fprintf", "fscanf", "NULL", "FILE", "stdin",
            "stdout", "main", "abs", "qsort"
        ],
        cpp: [
            "int", "printf", "scanf", "return", "if", "else", "for", "while", "do",
            "switch", "case", "break", "continue", "char", "double", "float",
            "long", "short", "unsigned", "signed", "void", "const", "static",
            "struct", "class", "public", "private", "protected", "template",
            "typename", "namespace", "using", "new", "delete", "nullptr", "true",
            "false", "bool", "auto", "constexpr", "static_cast", "dynamic_cast",
            "const_cast", "reinterpret_cast", "try", "catch", "throw", "virtual",
            "override", "std", "cout", "cin", "cerr", "endl", "puts", "putchar",
            "getchar", "memset", "memcpy", "strlen", "strcmp", "malloc", "free",
            "NULL", "FILE", "stdin", "stdout", "main", "abs", "string", "vector",
            "map", "set", "unordered_map", "unordered_set", "pair", "queue",
            "stack", "priority_queue", "sort", "reverse", "find", "push_back",
            "pop_back", "size", "empty", "begin", "end", "first", "second",
            "make_pair", "ios", "sync_with_stdio", "tie", "long long",
            "unsigned long long", "uint64_t", "int64_t", "stringstream"
        ],
        python: [
            "def", "return", "if", "elif", "else", "for", "while", "in", "not",
            "and", "or", "is", "None", "True", "False", "import", "from", "as",
            "class", "try", "except", "finally", "raise", "with", "lambda",
            "yield", "global", "nonlocal", "pass", "break", "continue", "del",
            "assert", "print", "input", "range", "len", "int", "str", "float",
            "list", "dict", "set", "tuple", "bool", "sum", "min", "max", "abs",
            "sorted", "reversed", "enumerate", "zip", "map", "filter", "open",
            "read", "readline", "readlines", "write", "append", "extend", "insert",
            "remove", "pop", "split", "strip", "join", "format", "lower", "upper",
            "replace", "find", "count", "self", "super", "__init__", "__name__",
            "__main__"
        ]
    };

    var problemId = textarea.dataset.problemId || "0";
    var currentLanguage = languageSelect.value;
    var saveTimer = null;
    var hintTimer = null;
    var suppressChange = false;

    function storageKey(language) {
        return "openoj:draft:" + problemId + ":" + language;
    }

    function modeFor(language) {
        return MODES[language] || "text/x-csrc";
    }

    var editor = CodeMirror.fromTextArea(textarea, {
        mode: modeFor(currentLanguage),
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        lineWrapping: false,
        styleActiveLine: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        viewportMargin: 10,
        extraKeys: {
            "Ctrl-Space": function (cm) {
                cm.showHint({ hint: hintFunction, completeSingle: false });
            },
            "Ctrl-Enter": function () {
                if (submitForm) {
                    submitForm.requestSubmit();
                }
            },
            "Cmd-Enter": function () {
                if (submitForm) {
                    submitForm.requestSubmit();
                }
            }
        }
    });

    function saveDraft() {
        try {
            var value = editor.getValue();
            if (value) {
                localStorage.setItem(storageKey(currentLanguage), value);
            } else {
                localStorage.removeItem(storageKey(currentLanguage));
            }
        } catch (error) {
            /* localStorage unavailable */
        }
    }

    function loadDraft(language) {
        var value = "";
        try {
            value = localStorage.getItem(storageKey(language)) || "";
        } catch (error) {
            value = "";
        }
        suppressChange = true;
        editor.setValue(value);
        suppressChange = false;
    }

    function updateCursor() {
        if (!cursorLabel) {
            return;
        }
        var cur = editor.getCursor();
        cursorLabel.textContent = "行 " + (cur.line + 1) + "，列 " + (cur.ch + 1);
    }

    function wordAtCursor() {
        var cur = editor.getCursor();
        var line = editor.getLine(cur.line);
        var start = cur.ch;
        while (start > 0 && /[A-Za-z0-9_]/.test(line.charAt(start - 1))) {
            start--;
        }
        return {
            prefix: line.slice(start, cur.ch),
            start: start,
            line: cur.line,
            ch: cur.ch
        };
    }

    function identifiers() {
        var matches = editor.getValue().match(/[A-Za-z_][A-Za-z0-9_]*/g) || [];
        var seen = Object.create(null);
        var result = [];
        for (var i = 0; i < matches.length; i++) {
            var word = matches[i];
            if (word.length <= 40 && !seen[word]) {
                seen[word] = true;
                result.push(word);
            }
        }
        return result;
    }

    function hintFunction(cm) {
        if (cm.somethingSelected()) {
            return null;
        }
        var word = wordAtCursor();
        var prefix = word.prefix;
        var lower = prefix.toLowerCase();
        var keywords = KEYWORDS[currentLanguage] || [];
        var seen = Object.create(null);
        var list = [];

        function add(value) {
            if (!value || seen[value] || value === prefix) {
                return;
            }
            if (prefix && value.toLowerCase().indexOf(lower) !== 0) {
                return;
            }
            seen[value] = true;
            list.push(value);
        }

        for (var i = 0; i < keywords.length; i++) {
            add(keywords[i]);
        }
        var words = identifiers();
        words.sort(function (a, b) {
            if (a.length !== b.length) {
                return a.length - b.length;
            }
            return a < b ? -1 : (a > b ? 1 : 0);
        });
        for (var j = 0; j < words.length; j++) {
            add(words[j]);
        }

        if (!list.length) {
            return null;
        }
        return {
            list: list.slice(0, 12),
            from: CodeMirror.Pos(word.line, word.start),
            to: CodeMirror.Pos(word.line, word.ch)
        };
    }

    function scheduleHint() {
        if (editor.state.completionActive) {
            return;
        }
        var word = wordAtCursor();
        if (word.prefix.length < 2) {
            return;
        }
        clearTimeout(hintTimer);
        hintTimer = setTimeout(function () {
            if (!editor.state.completionActive) {
                editor.showHint({ hint: hintFunction, completeSingle: false });
            }
        }, 100);
    }

    editor.on("cursorActivity", updateCursor);
    editor.on("change", function () {
        updateCursor();
        if (suppressChange) {
            return;
        }
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, 400);
    });
    editor.on("inputRead", function (cm, change) {
        if (change.origin !== "+input") {
            return;
        }
        var text = change.text && change.text[0] ? change.text[0] : "";
        if (/[A-Za-z_]/.test(text.charAt(0))) {
            scheduleHint();
        }
    });
    editor.on("blur", function () {
        clearTimeout(hintTimer);
    });

    languageSelect.addEventListener("change", function () {
        saveDraft();
        currentLanguage = languageSelect.value;
        editor.setOption("mode", modeFor(currentLanguage));
        loadDraft(currentLanguage);
        editor.focus();
        updateCursor();
        editor.refresh();
    });

    if (submitForm) {
        submitForm.addEventListener("submit", function () {
            editor.save();
            saveDraft();
        });
    }

    window.addEventListener("beforeunload", saveDraft);

    /* ---------------------------------------------------- self-test run */
    var testPanel = document.getElementById("test-panel");
    var testToggle = document.getElementById("test-toggle");
    var testRunButton = document.getElementById("test-run");
    var testStatus = document.getElementById("test-status");
    var testMeta = document.getElementById("test-meta");
    var testStdout = document.getElementById("test-stdout");
    var testExtra = document.getElementById("test-extra");
    var testExtraLabel = document.getElementById("test-extra-label");
    var testExtraPre = document.getElementById("test-extra-pre");
    var testNote = document.getElementById("test-note");
    var testSampleInput = document.getElementById("test-input-sample");
    var testCustomInput = document.getElementById("test-input-custom");
    var testTabs = testPanel ? testPanel.querySelectorAll(".test-tab") : [];
    var csrfField = submitForm ? submitForm.querySelector('input[name="csrf_token"]') : null;
    var testMode = "sample";
    var testRunning = false;

    var RUN_STATUS = {
        OK: "运行完成",
        AC: "通过",
        WA: "答案错误",
        CE: "编译错误",
        TLE: "超时",
        MLE: "超内存",
        ULE: "运行错误"
    };
    var RUN_FAILED = { WA: true, CE: true, TLE: true, MLE: true, ULE: true };

    function setTestStatus(status, fallbackLabel) {
        if (!testStatus) {
            return;
        }
        testStatus.textContent = fallbackLabel || RUN_STATUS[status] || status;
        testStatus.className = "test-status";
        if (status === "AC" || status === "OK") {
            testStatus.className += " test-ok";
        } else if (RUN_FAILED[status]) {
            testStatus.className += " test-bad";
        }
    }

    function showTestExtra(label, text) {
        if (!testExtra || !testExtraPre || !testExtraLabel) {
            return;
        }
        if (!text) {
            testExtra.hidden = true;
            testExtraPre.textContent = "";
            return;
        }
        testExtra.hidden = false;
        testExtraLabel.textContent = label;
        testExtraPre.textContent = text;
    }

    function setTestMode(mode) {
        testMode = mode;
        var sample = mode === "sample";
        for (var i = 0; i < testTabs.length; i++) {
            testTabs[i].className = testTabs[i].dataset.testMode === mode
                ? "test-tab is-active"
                : "test-tab";
        }
        if (testSampleInput) {
            testSampleInput.hidden = !sample;
        }
        if (testCustomInput) {
            testCustomInput.hidden = sample;
        }
        if (testNote) {
            testNote.textContent = sample ? "将与样例输出比对" : "仅运行，不比对输出";
        }
        var active = sample ? testSampleInput : testCustomInput;
        if (active && testPanel && !testPanel.hidden) {
            active.focus();
        }
    }

    function openTestPanel() {
        if (!testPanel) {
            return;
        }
        testPanel.hidden = false;
        editor.refresh();
    }

    function finishTestRun(message) {
        testRunning = false;
        if (testRunButton) {
            testRunButton.disabled = false;
            testRunButton.textContent = "运行";
        }
        if (message && testStdout) {
            testStdout.textContent = message;
        }
    }

    function renderTestResult(result) {
        if (!result || !result.status) {
            setTestStatus("ULE", "运行失败");
            if (testStdout) {
                testStdout.textContent = "服务器返回了无法识别的结果。";
            }
            showTestExtra("", "");
            return;
        }
        setTestStatus(result.status);
        if (testMeta) {
            testMeta.textContent = Number(result.time_ms || 0).toFixed(2) + " ms / " +
                Math.round(Number(result.memory_kb || 0)) + " KB" +
                (result.truncated ? "（输出已截断）" : "");
        }
        if (result.status === "CE") {
            if (testStdout) {
                testStdout.textContent = result.compile_output || "编译失败。";
            }
            showTestExtra("", "");
            return;
        }
        if (testStdout) {
            testStdout.textContent = result.stdout || "（无输出）";
        }
        if (result.stderr) {
            showTestExtra("标准错误", result.stderr);
        } else if (result.status === "WA" && result.expected) {
            showTestExtra("样例期望输出", result.expected);
        } else {
            showTestExtra("", "");
        }
    }

    function runTest() {
        if (!testPanel || !csrfField || testRunning) {
            return;
        }
        openTestPanel();
        if (!testStdout) {
            return;
        }

        var code = editor.getValue();
        if (!code.trim()) {
            setTestStatus("ULE", "无法运行");
            if (testMeta) {
                testMeta.textContent = "";
            }
            testStdout.textContent = "请先编写代码。";
            showTestExtra("", "");
            return;
        }

        saveDraft();
        testRunning = true;
        if (testRunButton) {
            testRunButton.disabled = true;
            testRunButton.textContent = "运行中…";
        }
        setTestStatus("", "运行中…");
        if (testMeta) {
            testMeta.textContent = "";
        }
        testStdout.textContent = "正在编译并运行…";
        showTestExtra("", "");

        var payload = {
            problem_id: problemId,
            language: languageSelect.value,
            code: code,
            mode: testMode,
            input: testMode === "custom" ? testCustomInput.value : ""
        };

        fetch("/api/run", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfField.value
            },
            body: JSON.stringify(payload)
        }).then(function (response) {
            if (response.redirected) {
                throw new Error("请先登录后再运行代码。");
            }
            var contentType = response.headers.get("content-type") || "";
            if (contentType.indexOf("application/json") === -1) {
                throw new Error("运行请求失败（HTTP " + response.status + "）。");
            }
            return response.json().catch(function () {
                return null;
            }).then(function (body) {
                if (!response.ok) {
                    throw new Error(
                        (body && body.error) ||
                        "运行请求失败（HTTP " + response.status + "）。"
                    );
                }
                return body;
            });
        }).then(function (result) {
            renderTestResult(result);
            finishTestRun("");
        }).catch(function (error) {
            setTestStatus("ULE", "运行失败");
            if (testMeta) {
                testMeta.textContent = "";
            }
            testStdout.textContent = error && error.message
                ? error.message
                : "网络错误，请重试。";
            showTestExtra("", "");
            finishTestRun("");
        });
    }

    if (testToggle) {
        testToggle.addEventListener("click", function () {
            if (testPanel.hidden) {
                openTestPanel();
            } else {
                testPanel.hidden = true;
                editor.refresh();
            }
        });
    }
    if (testRunButton) {
        testRunButton.addEventListener("click", runTest);
    }
    document.addEventListener("keydown", function (event) {
        if (event.key === "F9" && testPanel) {
            event.preventDefault();
            runTest();
        }
    });
    for (var tabIndex = 0; tabIndex < testTabs.length; tabIndex++) {
        testTabs[tabIndex].addEventListener("click", function () {
            if (this.dataset.testMode) {
                setTestMode(this.dataset.testMode);
            }
        });
    }

    loadDraft(currentLanguage);
    updateCursor();
    editor.refresh();
})();
