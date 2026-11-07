/* OpenOJ 前端交互：提交轮询、测试点编辑。 */
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
