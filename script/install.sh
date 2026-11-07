#!/usr/bin/env bash
# OpenOJ 交互式安装向导（Linux / macOS / Git Bash）
# 用法：
#   bash script/install.sh
#   bash script/install.sh --check

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="${OPENOJ_REPO_URL:-https://github.com/happycat184/openoj.git}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/openoj"
CONFIG_FILE="$CONFIG_DIR/install-path"

ROOT=""
VENV=""
REQUIREMENTS=""
APP_ENTRY=""

CHECK_ONLY=0
case "${1:-}" in
    --check|-c) CHECK_ONLY=1 ;;
    --help|-h)
        printf '用法: bash script/install.sh [--check]\n'
        exit 0
        ;;
esac

# ---------------------------------------------------------------- output

if [ -t 1 ]; then
    RESET=$'\033[0m'
    BOLD=$'\033[1m'
    DIM=$'\033[2m'
    CYAN=$'\033[36m'
    GREEN=$'\033[32m'
    YELLOW=$'\033[33m'
    RED=$'\033[31m'
    REV=$'\033[7m'
else
    RESET=''
    BOLD=''
    DIM=''
    CYAN=''
    GREEN=''
    YELLOW=''
    RED=''
    REV=''
fi

log_title() { printf '\n%s%s%s\n' "$CYAN" "$1" "$RESET"; printf '%s\n' "----------------------------------------------------"; }
log_step() { printf '%s[*] %s%s\n' "$CYAN" "$1" "$RESET"; }
log_ok() { printf '%s[+] %s%s\n' "$GREEN" "$1" "$RESET"; }
log_warn() { printf '%s[!] %s%s\n' "$YELLOW" "$1" "$RESET"; }
log_err() { printf '%s[-] %s%s\n' "$RED" "$1" "$RESET"; }

clear_screen() {
    if command -v clear >/dev/null 2>&1; then
        clear
    else
        printf '\033[H\033[2J'
    fi
}

pause() {
    if [ -t 0 ]; then
        printf '\n按回车返回菜单'
        IFS= read -r _ || true
    fi
}

confirm_yes_no() {
    local question="$1" default="${2:-Y}" answer
    if [ ! -t 0 ]; then
        [ "$default" = "Y" ]
        return
    fi
    if [ "$default" = "Y" ]; then
        printf '%s [Y/n] ' "$question"
    else
        printf '%s [y/N] ' "$question"
    fi
    IFS= read -r answer || answer=''
    if [ -z "$answer" ]; then
        [ "$default" = "Y" ]
        return
    fi
    [[ "$answer" =~ ^[Yy] ]]
}

# ---------------------------------------------------------------- menu

# 返回选中项下标；255 表示退出
menu() {
    local title="$1"
    shift
    local -a items=("$@")
    local count=${#items[@]}
    local selected=0 i key rest answer

    if [ ! -t 0 ]; then
        printf '\n%s\n' "$title"
        for ((i = 0; i < count; i++)); do
            printf '  %d) %s\n' "$((i + 1))" "${items[$i]}"
        done
        while :; do
            printf '请输入编号：'
            IFS= read -r answer || return 255
            if [[ "$answer" =~ ^[0-9]+$ ]] && ((answer >= 1 && answer <= count)); then
                return $((answer - 1))
            fi
            printf '输入无效，请重试。\n'
        done
    fi

    while :; do
        clear_screen
        printf '%s%s%s\n\n' "$BOLD" "$title" "$RESET"
        for ((i = 0; i < count; i++)); do
            if ((i == selected)); then
                printf '  %s> %s%s\n' "$REV" "${items[$i]}" "$RESET"
            else
                printf '    %s\n' "${items[$i]}"
            fi
        done
        IFS= read -rsn1 key
        if [ "$key" = $'\x1b' ]; then
            IFS= read -rsn2 -t 0.3 rest || rest=''
            key="$key$rest"
        fi
        case "$key" in
            $'\x1b[A') selected=$(((selected - 1 + count) % count)) ;;
            $'\x1b[B') selected=$(((selected + 1) % count)) ;;
            '') return "$selected" ;;
            q | Q | $'\x1b') return 255 ;;
        esac
    done
}

# ---------------------------------------------------------------- project path

have() { command -v "$1" >/dev/null 2>&1; }

case "$(uname -s)" in
    Linux*) OS=linux ;;
    Darwin*) OS=macos ;;
    MINGW* | MSYS* | CYGWIN*) OS=windows-bash ;;
    *) OS=unknown ;;
esac

set_project_root() {
    ROOT="$1"
    VENV="$ROOT/.venv"
    REQUIREMENTS="$ROOT/requirements.txt"
    APP_ENTRY="$ROOT/app.py"
    if [ -d "$ROOT" ]; then
        cd "$ROOT" 2>/dev/null || true
    fi
}

saved_path() {
    [ -f "$CONFIG_FILE" ] || return 1
    local saved
    saved="$(head -n 1 "$CONFIG_FILE" 2>/dev/null)"
    [ -n "$saved" ] && printf '%s' "$saved"
}

save_project_path() {
    mkdir -p "$CONFIG_DIR" 2>/dev/null || return 0
    printf '%s\n' "$1" >"$CONFIG_FILE" 2>/dev/null || true
}

default_root() {
    local saved
    if saved="$(saved_path)" && [ -f "$saved/app.py" ]; then
        printf '%s' "$saved"
        return
    fi
    local repo_root
    repo_root="$(cd "$SCRIPT_DIR/.." && pwd)"
    if [ -f "$repo_root/app.py" ]; then
        printf '%s' "$repo_root"
        return
    fi
    printf '%s' "$HOME/OpenOJ"
}

expand_path() {
    local path="$1"
    case "$path" in
        '~') path="$HOME" ;;
        '~/'*) path="$HOME/${path#\~/}" ;;
    esac
    printf '%s' "$path"
}

# 结果写入 INSTALL_PATH
INSTALL_PATH=""
read_install_path() {
    local default result
    default="${ROOT:-$(default_root)}"

    printf '\n%s请输入 OpenOJ 的安装位置（将在此目录克隆项目）%s\n' "$CYAN" "$RESET"
    printf '  默认：%s\n' "$default"

    while :; do
        printf '安装位置（回车使用默认，输入 q 取消）：'
        IFS= read -r result || return 1
        if [ "$result" = "q" ] || [ "$result" = "Q" ]; then
            return 1
        fi
        [ -z "$result" ] && result="$default"
        result="$(expand_path "$result")"
        case "$result" in
            /*|[A-Za-z]:*) ;;
            *) result="$PWD/$result" ;;
        esac
        INSTALL_PATH="$result"
        return 0
    done
}

# ---------------------------------------------------------------- detection

find_python() {
    local candidate
    for candidate in python3 python; do
        if have "$candidate" &&
            "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

venv_python() {
    if [ -x "$VENV/bin/python" ]; then
        printf '%s' "$VENV/bin/python"
    elif [ -x "$VENV/Scripts/python.exe" ]; then
        printf '%s' "$VENV/Scripts/python.exe"
    else
        return 1
    fi
}

test_dependencies() {
    local python
    python="$(venv_python)" || return 1
    "$python" -c 'import flask, markdown_it' >/dev/null 2>&1
}

check_env() {
    local ok=0 python version tool vpy git_version
    log_title '环境检查'

    if [ -f "$ROOT/app.py" ]; then
        printf '  %s项目目录：%s%s\n' "$GREEN" "$ROOT" "$RESET"
    else
        printf '  %s项目尚未安装：%s%s\n' "$YELLOW" "${ROOT:-（未设置）}" "$RESET"
        printf '  选择「一键安装」可从此位置克隆项目。\n'
        ok=1
    fi
    printf '  系统：%s %s\n' "$(uname -s)" "$(uname -m)"

    if python="$(find_python)"; then
        version="$("$python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
        printf '  %sPython：%s（%s）%s\n' "$GREEN" "$version" "$(command -v "$python")" "$RESET"
    else
        printf '  %sPython：未找到 3.10+%s\n' "$YELLOW" "$RESET"
        ok=1
    fi

    for tool in gcc g++; do
        if have "$tool"; then
            printf '  %s%s：%s%s\n' "$GREEN" "$tool" "$("$tool" --version 2>/dev/null | head -n 1)" "$RESET"
        else
            printf '  %s%s：未找到%s\n' "$YELLOW" "$tool" "$RESET"
            ok=1
        fi
    done

    if have git; then
        git_version="$(git --version 2>/dev/null | head -n 1)"
        printf '  %sgit：%s%s\n' "$GREEN" "$git_version" "$RESET"
    else
        printf '  %sgit：未找到（一键安装需要它来克隆项目）%s\n' "$YELLOW" "$RESET"
        ok=1
    fi

    if vpy="$(venv_python)"; then
        printf '  %s虚拟环境：%s%s\n' "$GREEN" "$VENV" "$RESET"
        if test_dependencies; then
            printf '  %sPython 依赖：已安装（flask、markdown-it-py）%s\n' "$GREEN" "$RESET"
        else
            printf '  %sPython 依赖：未安装%s\n' "$YELLOW" "$RESET"
            ok=1
        fi
    else
        printf '  %s虚拟环境：未创建%s\n' "$YELLOW" "$RESET"
        ok=1
    fi

    if [ -f "$ROOT/openoj.db" ]; then
        printf '  %s数据库：openoj.db 已存在%s\n' "$GREEN" "$RESET"
    else
        printf '  %s数据库：首次启动时自动创建%s\n' "$YELLOW" "$RESET"
    fi

    return "$ok"
}

# ---------------------------------------------------------------- installers

run_system() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif have sudo; then
        sudo "$@"
    else
        log_err '需要管理员权限，请安装 sudo 或以 root 运行。'
        return 1
    fi
}

install_git() {
    if have git; then
        log_ok "git 已就绪：$(git --version 2>/dev/null | head -n 1)"
        return 0
    fi

    log_step '未找到 git，尝试自动安装...'
    case "$OS" in
        linux)
            if have apt-get; then
                run_system apt-get install -y git
            elif have dnf; then
                run_system dnf install -y git
            elif have pacman; then
                run_system pacman -S --needed --noconfirm git
            elif have zypper; then
                run_system zypper install -y git
            elif have apk; then
                run_system apk add git
            else
                log_err '未识别包管理器，请手动安装 git。'
                return 1
            fi
            ;;
        macos)
            if have brew; then
                brew install git
            else
                log_warn '未找到 Homebrew，尝试安装 Xcode Command Line Tools ...'
                xcode-select --install || true
                log_warn '安装完成后请重新运行本脚本。'
                return 1
            fi
            ;;
        windows-bash)
            log_err 'Windows 环境请使用 PowerShell 版：'
            printf '  powershell -ExecutionPolicy Bypass -File script\\install.ps1\n'
            return 1
            ;;
        *)
            log_err '不支持的系统，请手动安装 git。'
            return 1
            ;;
    esac

    if have git; then
        log_ok 'git 安装完成'
        return 0
    fi
    log_err 'git 安装后仍未检测到，请重新打开终端。'
    return 1
}

install_python_linux() {
    if have apt-get; then
        run_system apt-get update || true
        run_system apt-get install -y python3 python3-venv python3-pip
    elif have dnf; then
        run_system dnf install -y python3 python3-pip
    elif have pacman; then
        run_system pacman -S --needed --noconfirm python
    elif have zypper; then
        run_system zypper install -y python3 python3-pip
    elif have apk; then
        run_system apk add python3 py3-pip
    else
        log_err '未识别包管理器，请手动安装 Python 3.10+。'
        return 1
    fi
}

install_gcc_linux() {
    if have apt-get; then
        run_system apt-get install -y gcc g++
    elif have dnf; then
        run_system dnf install -y gcc gcc-c++
    elif have pacman; then
        run_system pacman -S --needed --noconfirm gcc
    elif have zypper; then
        run_system zypper install -y gcc gcc-c++
    elif have apk; then
        run_system apk add gcc g++ musl-dev
    else
        log_err '未识别包管理器，请手动安装 gcc / g++。'
        return 1
    fi
}

install_python_macos() {
    if have brew; then
        brew install python
    else
        log_err '未找到 Homebrew，请先安装：https://brew.sh/'
        log_warn '也可以从 https://www.python.org/downloads/ 安装 Python 3.10+。'
        return 1
    fi
}

install_gcc_macos() {
    if have gcc && have g++; then
        return 0
    fi
    log_warn '未找到 gcc / g++，尝试安装 Xcode Command Line Tools ...'
    if xcode-select -p >/dev/null 2>&1; then
        log_err 'Command Line Tools 已安装但 gcc / g++ 不可用，请检查 PATH。'
        return 1
    fi
    xcode-select --install || true
    log_warn '系统安装窗口已完成安装后，请重新运行本脚本。'
    return 1
}

install_python() {
    local python
    if python="$(find_python)"; then
        log_ok "Python 已就绪：$python ($("$python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'))"
        return 0
    fi

    log_step '未找到可用的 Python 3.10+，尝试自动安装...'
    case "$OS" in
        linux) install_python_linux || return 1 ;;
        macos) install_python_macos || return 1 ;;
        windows-bash)
            log_err 'Windows 环境请使用 PowerShell 版：'
            printf '  powershell -ExecutionPolicy Bypass -File script\\install.ps1\n'
            return 1
            ;;
        *)
            log_err '不支持的系统，请手动安装 Python 3.10+。'
            return 1
            ;;
    esac

    if python="$(find_python)"; then
        log_ok "Python 安装完成：$python"
        return 0
    fi
    log_err 'Python 安装后仍未检测到 3.10+，请重新打开终端或手动安装。'
    return 1
}

install_gcc() {
    if have gcc && have g++; then
        log_ok "GCC / G++ 已就绪：$(gcc --version 2>/dev/null | head -n 1)"
        return 0
    fi

    log_step '未找到 GCC / G++，尝试自动安装...'
    case "$OS" in
        linux) install_gcc_linux || return 1 ;;
        macos) install_gcc_macos || return 1 ;;
        windows-bash)
            log_err 'Windows 环境请使用 PowerShell 版安装 GCC：'
            printf '  powershell -ExecutionPolicy Bypass -File script\\install.ps1\n'
            return 1
            ;;
        *)
            log_err '不支持的系统，请手动安装 gcc / g++。'
            return 1
            ;;
    esac

    if have gcc && have g++; then
        log_ok "GCC / G++ 安装完成：$(gcc --version 2>/dev/null | head -n 1)"
        return 0
    fi
    log_err 'GCC / G++ 安装后仍未检测到，请重新打开终端或手动安装。'
    return 1
}

setup_venv() {
    local python vpy
    if ! python="$(find_python)"; then
        log_err '未找到可用的 Python 3.10+，无法创建虚拟环境。'
        return 1
    fi
    if [ ! -f "$APP_ENTRY" ]; then
        log_err '项目尚未安装，无法安装依赖。'
        return 1
    fi

    if ! vpy="$(venv_python)"; then
        log_step "创建虚拟环境：$VENV"
        if ! "$python" -m venv "$VENV"; then
            log_err '创建虚拟环境失败。'
            log_warn 'Debian / Ubuntu 可先执行：sudo apt-get install -y python3-venv'
            return 1
        fi
        vpy="$(venv_python)" || return 1
    else
        log_ok "虚拟环境已存在：$VENV"
    fi

    log_step '升级 pip ...'
    "$vpy" -m pip install --upgrade pip --disable-pip-version-check || true

    log_step '安装 Python 依赖 ...'
    if ! "$vpy" -m pip install -r "$REQUIREMENTS" --disable-pip-version-check; then
        log_err '依赖安装失败，请检查网络连接后重试。'
        return 1
    fi

    if ! test_dependencies; then
        log_err '依赖校验失败：flask 或 markdown-it-py 无法导入。'
        return 1
    fi
    log_ok 'Python 依赖安装完成'
}

# ---------------------------------------------------------------- repository

ensure_repository() {
    local target="$1"
    local entries

    if [ -f "$target/app.py" ]; then
        log_ok "检测到已有 OpenOJ 项目：$target"
        if [ -d "$target/.git" ] && confirm_yes_no '是否拉取最新代码？' Y; then
            if ! git -C "$target" pull --ff-only; then
                log_warn '拉取失败，将继续使用当前代码。'
            fi
        fi
        return 0
    fi

    if [ -e "$target" ]; then
        if [ ! -d "$target" ]; then
            log_err "目标路径不是目录：$target"
            return 1
        fi
        entries="$(ls -A "$target" 2>/dev/null | head -n 1)"
        if [ -n "$entries" ]; then
            log_err "目录非空且不是 OpenOJ 项目：$target"
            printf '请选择一个空目录或新的安装位置。\n'
            return 1
        fi
    else
        mkdir -p "$(dirname "$target")" 2>/dev/null || {
            log_err "无法创建目录：$(dirname "$target")"
            return 1
        }
    fi

    if ! install_git; then
        return 1
    fi

    log_step "从 GitHub 克隆 OpenOJ 到 $target"
    if ! git clone --depth 1 "$REPO_URL" "$target"; then
        log_err '克隆失败，请检查网络连接或仓库地址。'
        printf '仓库地址：%s\n' "$REPO_URL"
        return 1
    fi

    if [ ! -f "$target/app.py" ]; then
        log_err '克隆完成但未找到 app.py，请检查仓库内容。'
        return 1
    fi

    log_ok '项目克隆完成'
    return 0
}

# ---------------------------------------------------------------- actions

one_click() {
    log_title '一键安装'

    if ! read_install_path; then
        log_warn '已取消安装。'
        return 1
    fi

    if ! ensure_repository "$INSTALL_PATH"; then
        return 1
    fi

    set_project_root "$INSTALL_PATH"
    save_project_path "$INSTALL_PATH"

    if ! install_python; then
        log_err 'Python 未就绪，安装中止。'
        return 1
    fi
    if ! install_gcc; then
        log_warn 'GCC / G++ 未能自动安装，评测 C / C++ 前需要手动补齐。'
    fi

    if setup_venv; then
        log_title '安装完成'
        log_ok '现在可以选择「启动 OpenOJ」开始使用。'
        printf '  项目目录：%s\n' "$ROOT"
        printf '  默认地址：http://127.0.0.1:5000\n'
        printf '  默认管理员：admin / admin123（首次登录后请修改密码）\n'
    else
        log_err '依赖安装失败，请检查网络后重试。'
    fi
}

step_menu() {
    local choice
    while :; do
        menu '分步安装（↑/↓ 选择，Enter 确认）' \
            '安装 / 修复 Python' \
            '安装 / 修复 GCC / G++' \
            '创建虚拟环境并安装依赖' \
            '返回主菜单'
        choice=$?
        case "$choice" in
            0) install_python && log_ok 'Python 就绪'; pause ;;
            1) install_gcc && log_ok 'GCC / G++ 就绪'; pause ;;
            2) setup_venv && log_ok '依赖安装完成'; pause ;;
            *) return 0 ;;
        esac
    done
}

open_browser_later() {
    local url="$1"
    (
        sleep 2
        case "$OS" in
            macos) open "$url" >/dev/null 2>&1 || true ;;
            linux) have xdg-open && xdg-open "$url" >/dev/null 2>&1 || true ;;
            windows-bash) cmd.exe /c start "" "$url" >/dev/null 2>&1 || true ;;
        esac
    ) &
}

start_app() {
    local vpy port url
    if ! vpy="$(venv_python)"; then
        log_err '虚拟环境尚未创建，请先执行「一键安装」。'
        return 1
    fi
    port="${OPENOJ_PORT:-5000}"
    url="http://127.0.0.1:$port"

    log_title '启动 OpenOJ'
    printf '项目目录：%s\n' "$ROOT"
    printf '%s访问地址：%s%s\n' "$GREEN" "$url" "$RESET"
    printf '默认管理员：admin / admin123（首次登录后请修改密码）\n'
    printf '按 Ctrl+C 停止服务。\n\n'

    open_browser_later "$url"
    exec "$vpy" "$APP_ENTRY"
}

# ---------------------------------------------------------------- main

main() {
    set_project_root "$(default_root)"

    if [ "$CHECK_ONLY" -eq 1 ]; then
        check_env
        exit $?
    fi

    if [ "$OS" = "windows-bash" ]; then
        log_warn '检测到 Windows 环境（Git Bash）。'
        if [ -f "$SCRIPT_DIR/install.ps1" ] && [ -t 0 ]; then
            printf '推荐使用 PowerShell 版安装向导，它能通过 winget 安装 Python 与 GCC。\n'
            printf '现在切换到 PowerShell 版？[Y/n] '
            IFS= read -r answer || answer=''
            if [ -z "$answer" ] || [[ "$answer" =~ ^[Yy] ]]; then
                exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/install.ps1"
            fi
        fi
    fi

    printf '\n%s  OpenOJ 安装向导%s\n' "$BOLD" "$RESET"
    printf '  %s项目目录：%s%s\n' "$DIM" "$ROOT" "$RESET"

    while :; do
        menu '请选择操作（↑/↓ 选择，Enter 确认）' \
            '一键安装（克隆项目 + Python + GCC + 依赖）' \
            '检查环境' \
            '分步安装' \
            '启动 OpenOJ' \
            '退出'
        choice=$?
        case "$choice" in
            0) one_click; pause ;;
            1) check_env; pause ;;
            2) step_menu ;;
            3) start_app; pause ;;
            *) exit 0 ;;
        esac
    done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main
fi
