/* OpenOJ 前端交互：代码草稿、提交轮询、测试点编辑。 */
(function () {
    "use strict";

    /* ---------------------------------------------------------- IDE 代码编辑器 */
    var COMPLETION_WORDS = {
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

    var editor = document.getElementById("code-editor");
    var languageSelect = document.getElementById("language");
    if (!editor || !languageSelect) {
        return;
    }

    var problemId = editor.dataset.problemId;
    var currentLanguage = languageSelect.value;
    var saveTimer = null;

    var gutter = document.getElementById("editor-gutter");
    var cursorLabel = document.getElementById("editor-cursor");
    var editorWrap = document.getElementById("editor-wrap");
    var popup = document.getElementById("completion-popup");
    var completionList = document.getElementById("completion-list");

    var completionItems = [];
    var completionIndex = 0;
    var completionStart = 0;
    var suppressCompletion = false;
    var hideTimer = null;

    /* ---------------------------------------------------------- 草稿 */

    function storageKey(language) {
        return "openoj:draft:" + problemId + ":" + language;
    }

    function saveDraft() {
        try {
            if (editor.value) {
                localStorage.setItem(storageKey(currentLanguage), editor.value);
            } else {
                localStorage.removeItem(storageKey(currentLanguage));
            }
        } catch (error) {
            /* localStorage 不可用时静默忽略 */
        }
    }

    function loadDraft(language) {
        editor.value = "";
        try {
            var saved = localStorage.getItem(storageKey(language));
            if (saved) {
                editor.value = saved;
            }
        } catch (error) {
            /* ignore */
        }
    }

    /* ---------------------------------------------------------- 行号与光标 */

    function updateLineNumbers() {
        if (!gutter) {
            return;
        }
        var count = editor.value.split("\n").length;
        var html = "";
        for (var i = 1; i <= count; i++) {
            html += "<div>" + i + "</div>";
        }
        gutter.innerHTML = html;
        gutter.scrollTop = editor.scrollTop;
    }

    function updateCursor() {
        if (!cursorLabel) {
            return;
        }
        var position = editor.selectionStart;
        var before = editor.value.slice(0, position);
        var line = before.split("\n").length;
        var column = position - before.lastIndexOf("\n");
        cursorLabel.textContent = "行 " + line + "，列 " + column;
    }

    /* ---------------------------------------------------------- 语法补全 */

    function wordBeforeCaret() {
        var before = editor.value.slice(0, editor.selectionStart);
        var match = before.match(/[A-Za-z_][A-Za-z0-9_]*$/);
        return match ? match[0] : "";
    }

    function wordStartBeforeCaret() {
        var start = editor.selectionStart;
        while (start > 0 && /[A-Za-z0-9_]/.test(editor.value.charAt(start - 1))) {
            start--;
        }
        return start;
    }

    function extractIdentifiers() {
        var matches = editor.value.match(/[A-Za-z_][A-Za-z0-9_]*/g) || [];
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

    function getCompletionItems(prefix) {
        var keywords = COMPLETION_WORDS[languageSelect.value] || [];
        var lowerPrefix = prefix.toLowerCase();
        var items = [];
        var seen = Object.create(null);

        function matches(word) {
            return !prefix || word.toLowerCase().lastIndexOf(lowerPrefix, 0) === 0;
        }

        function add(word) {
            if (!word || seen[word] || word === prefix) {
                return;
            }
            seen[word] = true;
            items.push(word);
        }

        for (var i = 0; i < keywords.length; i++) {
            if (matches(keywords[i])) {
                add(keywords[i]);
            }
        }

        var identifiers = extractIdentifiers();
        identifiers.sort(function (a, b) {
            if (a.length !== b.length) {
                return a.length - b.length;
            }
            return a < b ? -1 : (a > b ? 1 : 0);
        });
        for (var j = 0; j < identifiers.length; j++) {
            if (matches(identifiers[j])) {
                add(identifiers[j]);
            }
        }

        return items.slice(0, 12);
    }

    function hideCompletions() {
        if (!popup) {
            return;
        }
        popup.hidden = true;
        completionItems = [];
        completionIndex = 0;
    }

    function renderCompletions() {
        if (!completionList) {
            return;
        }
        completionList.innerHTML = "";
        for (var i = 0; i < completionItems.length; i++) {
            var item = document.createElement("div");
            item.className = "completion-item" + (i === completionIndex ? " active" : "");
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", i === completionIndex ? "true" : "false");
            item.textContent = completionItems[i];
            (function (index) {
                item.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    applyCompletion(index);
                });
            })(i);
            completionList.appendChild(item);
        }
    }

    function positionCompletions() {
        if (!popup || popup.hidden || !editorWrap) {
            return;
        }
        var style = window.getComputedStyle(editor);
        var mirror = document.createElement("div");
        mirror.style.position = "absolute";
        mirror.style.top = "0";
        mirror.style.left = "-10000px";
        mirror.style.visibility = "hidden";
        mirror.style.pointerEvents = "none";
        mirror.style.whiteSpace = "pre";
        mirror.style.fontFamily = style.fontFamily;
        mirror.style.fontSize = style.fontSize;
        mirror.style.fontWeight = style.fontWeight;
        mirror.style.lineHeight = style.lineHeight;
        mirror.style.letterSpacing = style.letterSpacing;
        mirror.style.tabSize = style.tabSize;
        mirror.style.padding = style.padding;
        mirror.textContent = editor.value.slice(0, editor.selectionStart);
        var marker = document.createElement("span");
        marker.textContent = "​";
        mirror.appendChild(marker);
        document.body.appendChild(mirror);

        var markerRect = marker.getBoundingClientRect();
        var mirrorRect = mirror.getBoundingClientRect();
        var lineHeight = parseFloat(style.lineHeight) || 21;
        var caretTop = markerRect.top - mirrorRect.top - editor.scrollTop;
        var caretLeft = markerRect.left - mirrorRect.left - editor.scrollLeft;
        document.body.removeChild(mirror);

        var left = caretLeft;
        var top = caretTop + lineHeight + 2;
        var maxLeft = editorWrap.clientWidth - popup.offsetWidth - 4;
        if (left > maxLeft) {
            left = maxLeft;
        }
        if (left < 4) {
            left = 4;
        }
        if (top + popup.offsetHeight > editorWrap.clientHeight - 4) {
            top = caretTop - popup.offsetHeight - 2;
        }
        if (top < 4) {
            top = 4;
        }
        popup.style.left = left + "px";
        popup.style.top = top + "px";
    }

    function showCompletions(prefix) {
        if (!popup || !editorWrap || !completionList) {
            return;
        }
        if (editor.selectionStart !== editor.selectionEnd) {
            hideCompletions();
            return;
        }
        var items = getCompletionItems(prefix);
        if (!items.length) {
            hideCompletions();
            return;
        }
        completionItems = items;
        completionIndex = 0;
        completionStart = wordStartBeforeCaret();
        popup.hidden = false;
        renderCompletions();
        positionCompletions();
    }

    function applyCompletion(index) {
        var word = completionItems[index];
        if (word === undefined) {
            return;
        }
        var start = completionStart;
        var end = editor.selectionEnd;
        if (start > end || start < 0) {
            start = wordStartBeforeCaret();
        }
        editor.value = editor.value.slice(0, start) + word + editor.value.slice(end);
        var caret = start + word.length;
        editor.selectionStart = editor.selectionEnd = caret;
        hideCompletions();
        suppressCompletion = true;
        editor.dispatchEvent(new Event("input", { bubbles: true }));
        editor.focus();
    }

    function handleEditorInput(event) {
        updateLineNumbers();
        updateCursor();

        if (!popup) {
            return;
        }
        if (suppressCompletion) {
            suppressCompletion = false;
            return;
        }
        if (event && event.inputType && event.inputType.indexOf("delete") === 0) {
            hideCompletions();
            return;
        }
        if (event && event.inputType === "insertFromPaste") {
            hideCompletions();
            return;
        }
        if (editor.selectionStart !== editor.selectionEnd) {
            hideCompletions();
            return;
        }

        var prefix = wordBeforeCaret();
        if (prefix.length > 0) {
            showCompletions(prefix);
        } else {
            hideCompletions();
        }
    }

    editor.addEventListener("input", function (event) {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, 400);
        handleEditorInput(event);
    });

    editor.addEventListener("scroll", function () {
        if (gutter) {
            gutter.scrollTop = editor.scrollTop;
        }
        hideCompletions();
    });

    editor.addEventListener("keyup", updateCursor);
    editor.addEventListener("click", updateCursor);
    editor.addEventListener("select", updateCursor);

    editor.addEventListener("blur", function () {
        hideTimer = setTimeout(hideCompletions, 120);
    });
    editor.addEventListener("focus", function () {
        if (hideTimer) {
            clearTimeout(hideTimer);
        }
    });

    function autoIndentNewline() {
        var start = editor.selectionStart;
        var end = editor.selectionEnd;
        var value = editor.value;
        var lineStart = value.lastIndexOf("\n", start - 1) + 1;
        var linePrefix = value.slice(lineStart, start);
        var indentMatch = linePrefix.match(/^[ \t]*/);
        var baseIndent = indentMatch ? indentMatch[0] : "";
        var trimmed = linePrefix.replace(/[ \t]+$/, "");
        var lastChar = trimmed.charAt(trimmed.length - 1);
        var extra = "";

        if (lastChar === "{" || lastChar === "[" || lastChar === "(") {
            extra = "    ";
        } else if (languageSelect.value === "python" && lastChar === ":") {
            extra = "    ";
        }

        var restOfLine = value.slice(end).split("\n", 1)[0];
        var closingMatch = restOfLine.match(/^[ \t]*\}/);
        var insertion;
        var caretOffset;

        if (extra && closingMatch) {
            var braceIndex = restOfLine.indexOf("}");
            insertion = "\n" + baseIndent + extra + "\n" + baseIndent + "}";
            editor.value =
                value.slice(0, start) + insertion + value.slice(end + braceIndex + 1);
            caretOffset = 1 + baseIndent.length + extra.length;
        } else {
            insertion = "\n" + baseIndent + extra;
            editor.value = value.slice(0, start) + insertion + value.slice(end);
            caretOffset = insertion.length;
        }

        editor.selectionStart = editor.selectionEnd = start + caretOffset;
        suppressCompletion = true;
        editor.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function outdentClosingBrace() {
        if (languageSelect.value === "python") {
            return false;
        }
        if (editor.selectionStart !== editor.selectionEnd) {
            return false;
        }

        var pos = editor.selectionStart;
        var value = editor.value;
        var lineStart = value.lastIndexOf("\n", pos - 1) + 1;
        var prefix = value.slice(lineStart, pos);
        if (!/^[ \t]+$/.test(prefix)) {
            return false;
        }

        var remove = 1;
        if (prefix.slice(-4) === "    ") {
            remove = 4;
        } else if (prefix.charAt(prefix.length - 1) === "\t") {
            remove = 1;
        }

        var newPrefix = prefix.slice(0, prefix.length - remove);
        editor.value =
            value.slice(0, lineStart) + newPrefix + "}" + value.slice(pos);
        editor.selectionStart = editor.selectionEnd =
            lineStart + newPrefix.length + 1;
        suppressCompletion = true;
        editor.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
    }

    editor.addEventListener("keydown", function (event) {
        var ctrl = event.ctrlKey || event.metaKey;

        if (event.isComposing) {
            return;
        }

        if (ctrl && event.key === "Enter") {
            event.preventDefault();
            var form = editor.closest("form");
            if (form) {
                if (form.requestSubmit) {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            }
            return;
        }

        if (ctrl && (event.key === " " || event.code === "Space")) {
            event.preventDefault();
            showCompletions(wordBeforeCaret());
            return;
        }

        if (popup && !popup.hidden) {
            if (event.key === "ArrowDown") {
                event.preventDefault();
                completionIndex = (completionIndex + 1) % completionItems.length;
                renderCompletions();
                scrollActiveCompletion();
                return;
            }
            if (event.key === "ArrowUp") {
                event.preventDefault();
                completionIndex =
                    (completionIndex - 1 + completionItems.length) % completionItems.length;
                renderCompletions();
                scrollActiveCompletion();
                return;
            }
            if (event.key === "Enter" || event.key === "Tab") {
                event.preventDefault();
                applyCompletion(completionIndex);
                return;
            }
            if (event.key === "Escape") {
                event.preventDefault();
                hideCompletions();
                return;
            }
        }

        if (event.key === "Enter") {
            event.preventDefault();
            autoIndentNewline();
            return;
        }

        if (event.key === "}" && !ctrl && !event.altKey) {
            if (outdentClosingBrace()) {
                event.preventDefault();
                return;
            }
        }

        if (event.key === "Tab") {
            event.preventDefault();
            var start = editor.selectionStart;
            var end = editor.selectionEnd;
            editor.value =
                editor.value.slice(0, start) + "    " + editor.value.slice(end);
            editor.selectionStart = editor.selectionEnd = start + 4;
            suppressCompletion = true;
            editor.dispatchEvent(new Event("input", { bubbles: true }));
        }
    });

    function scrollActiveCompletion() {
        if (!completionList) {
            return;
        }
        var active = completionList.children[completionIndex];
        if (active && active.scrollIntoView) {
            active.scrollIntoView({ block: "nearest" });
        }
    }

    languageSelect.addEventListener("change", function () {
        saveDraft();
        currentLanguage = languageSelect.value;
        loadDraft(currentLanguage);
        updateLineNumbers();
        updateCursor();
        hideCompletions();
        editor.focus();
    });

    loadDraft(currentLanguage);
    updateLineNumbers();
    updateCursor();

    window.addEventListener("beforeunload", saveDraft);
})();

(function () {
    "use strict";

    /* ---------------------------------------------------------- 提交防重复 */
    var submitForm = document.getElementById("submit-form");
    if (submitForm) {
        var submitButton = submitForm.querySelector('button[type="submit"]');
        var submitButtonText = submitButton ? submitButton.textContent : "提交评测";

        submitForm.addEventListener("submit", function () {
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "正在提交…";
            }
        });

        // 从结果页后退时，浏览器可能从 bfcache 恢复页面，需要重置按钮状态
        window.addEventListener("pageshow", function () {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = submitButtonText;
            }
        });
    }

    /* ---------------------------------------------------------- 危险操作确认 */
    var confirmForms = document.querySelectorAll("form[data-confirm]");
    Array.prototype.forEach.call(confirmForms, function (form) {
        form.addEventListener("submit", function (event) {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    /* ---------------------------------------------------------- 评测结果轮询 */
    var live = document.getElementById("judge-live");
    if (live) {
        var submissionId = live.dataset.submissionId;

        var poll = function () {
            fetch("/api/submission/" + submissionId, {
                headers: { Accept: "application/json" }
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("bad response");
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (data.finished) {
                        window.location.reload();
                        return;
                    }
                    if (data.cases && data.cases.length > 0) {
                        live.textContent =
                            "评测中，已完成 " + data.cases.length + " 个测试点…";
                    }
                    setTimeout(poll, 1200);
                })
                .catch(function () {
                    setTimeout(poll, 2500);
                });
        };

        setTimeout(poll, 900);
    }

    /* ---------------------------------------------------------- 动态添加测试点 */
    var addCaseButton = document.getElementById("add-case-row");
    if (addCaseButton) {
        var caseTemplate = document.getElementById("case-row-template");
        var caseRows = document.getElementById("case-rows");

        addCaseButton.addEventListener("click", function () {
            if (!caseTemplate || !caseRows) {
                return;
            }
            var fragment = caseTemplate.content.cloneNode(true);
            var row = fragment.querySelector(".case-row");
            caseRows.appendChild(fragment);
            if (row) {
                var textarea = row.querySelector("textarea");
                if (textarea) {
                    textarea.focus();
                }
            }
        });
    }
})();
