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

    loadDraft(currentLanguage);
    updateCursor();
    editor.refresh();
})();
