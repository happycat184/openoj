/* Render LaTeX inside rendered Markdown blocks with KaTeX. */
(function () {
    "use strict";

    function renderMath() {
        if (typeof window.renderMathInElement !== "function") {
            return;
        }
        var nodes = document.querySelectorAll(".md");
        for (var i = 0; i < nodes.length; i++) {
            try {
                window.renderMathInElement(nodes[i], {
                    delimiters: [
                        { left: "$$", right: "$$", display: true },
                        { left: "\\[", right: "\\]", display: true },
                        { left: "$", right: "$", display: false },
                        { left: "\\(", right: "\\)", display: false }
                    ],
                    throwOnError: false,
                    strict: false,
                    ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"]
                });
            } catch (error) {
                /* Leave the raw LaTeX visible if rendering fails. */
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", renderMath);
    } else {
        renderMath();
    }
})();
