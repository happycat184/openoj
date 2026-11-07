# OpenOJ

一个基于 Flask + HTML5 + CSS3 + JavaScript 的在线评测系统（Online Judge），
使用 SQLite 存储数据，支持 **C**、**C++**、**Python** 三种语言的真实编译与评测。

界面采用 Body–Nav–Content 结构，浅色直角风格，无圆角、无阴影、无渐变、无动画。

## 功能

- 首页随机推荐最多 10 道题目，避免题目数量增长后堆满首页
- 题目搜索：按标题、描述或题库名称检索全部可见题目
- 多选题库：首页按题库分类展示，每个题库有独立题目列表与个人进度
- 题库管理：管理员可新建、编辑、删除题库；题目必须归属一个题库，可随时移动
- 题目详情、样例展示、我的通过状态
- 题面支持 Markdown 与 LaTeX（KaTeX）渲染
- 题目难度标签（入门 / 简单 / 中等 / 困难）与按难度、通过状态、题库筛选、分页
- 独立的 IDE 编写页：左侧题面、右侧 CodeMirror 编辑器，语法高亮、行号、补全与自动缩进
- IDE 自测运行：用样例或自定义输入运行代码，不产生提交记录，样例模式自动比对输出
- 多语言提交：C（GCC）、C++（G++）、Python 3
- 真实编译执行，逐测试点显示结果
- 每个测试点显示为一个正方形：中间为状态码，偏下方为用时/内存
- 固定 worker 评测队列 + 前端自动轮询刷新
- 每道题独立的题解 / 讨论区，支持 Markdown/LaTeX、回复与作者删除，无需审核
- 完整用户系统：注册、登录、个人主页、通过题目统计、排行榜、修改密码
- 管理员后台：题库管理、在线新建/编辑题目、上传/编辑测试点、JSON 题库批量导入、隐藏题目、用户角色管理、重新评测
- CSRF 保护、密码哈希存储

## IDE 页面

在题目页点击「开始编写」进入 `/problem/<id>/ide`：

- 左半边为题目描述、格式、样例与提示，可独立滚动
- 右半边为 CodeMirror 代码编写区，带 C / C++ / Python 语法高亮、行号与括号匹配
  - 输入关键字或已有标识符时自动弹出候选
  - `↑` / `↓` 选择，`Tab` 或 `Enter` 补全，`Esc` 关闭
  - `Ctrl+Space` 手动唤出补全
  - 回车自动缩进，C/C++ 自动补全括号
  - `F9` 自测运行，`Ctrl+Enter` 提交
- 草稿按题目与语言自动保存在浏览器本地

### 自测运行

点击工具栏「运行测试」或按 `F9` 打开下方测试面板：

- 「样例输入」模式下使用题目样例输入运行，并自动与样例输出比对（AC / WA）
- 「自定义输入」模式下使用面板中填写的输入运行，只显示结果不比对
- 显示标准输出、标准错误、编译信息、用时与内存；输出超过 64 KB 会截断
- 自测结果**不写入提交记录**，也不会影响通过状态与排行榜
- 同时最多运行 2 个自测，使用题目自身的时间与内存限制

## 评测队列

- 评测使用固定数量的 worker 线程，提交先进入 FIFO 队列，状态为 `PENDING`，被 worker 取走后变为 `JUDGING`
- 默认 2 个 worker，可通过 `OPENOJ_JUDGE_WORKERS` 调整
- 管理控制台显示工作线程数、运行中与排队中的数量
- 服务重启时，仍处于 `PENDING/JUDGING` 的提交会标记为 `ULE`

## 题解与讨论

每道题都有独立的题解/讨论区：

- 支持「题解」和「讨论」两种主题类型
- 登录后可发布主题、回复；内容立即公开，**无需审核**
- 主题和回复均支持 Markdown 与 LaTeX
- 作者可删除自己的主题/回复，管理员可删除任意主题/回复

## 题面、难度与筛选

- 题面支持 Markdown 和 LaTeX，使用本地 KaTeX 渲染数学公式
- 题目难度分为「入门 / 简单 / 中等 / 困难」，在题目列表、题目页和后台显示
- 题库页支持按难度与我的通过状态筛选，并分页
- 搜索结果支持按难度、题库筛选，并分页
- 后台题目管理支持按题库、难度筛选和分页

## 评分状态

| 状态 | 颜色 | 含义 |
| --- | --- | --- |
| AC | 绿色 | 通过该测试点 / 通过 |
| WA | 红色 | 答案错误 |
| TLE | 黑色 | 超时 |
| MLE | 黑色 | 超内存 |
| ULE | 黑色 | 未知错误（运行时错误、内部错误等） |
| CE | 黑色 | 编译错误；Python 运行产生 Traceback 的测试点也记为 CE |

测试点方块中的时间/内存格式为 `12.34ms/1024.00KB`。

Python 运行时若标准错误输出包含 `Traceback (most recent call last):`，该测试点记为 `CE`；
`SystemExit`、无 Traceback 的非零退出等仍记为 `ULE`。C/C++ 运行时错误仍为 `ULE`。

## 环境要求

- Python 3.10+
- Flask（`pip install -r requirements.txt`）
- GCC / G++（C、C++ 评测必需，需在 PATH 中）
- Python 解释器（评测 Python 时使用运行本应用的同一个解释器）

本机已验证环境：GCC/G++ 15.2、Python 3.13、Flask 3.1。

## 运行

```bash
pip install -r requirements.txt
python app.py
```

浏览器打开 <http://127.0.0.1:5000>。

首次运行会自动创建 `openoj.db`，写入示例题目和默认管理员：

- 用户名：`admin`
- 密码：`admin123`

**首次登录后请立即在个人主页修改密码。**

## 一键安装脚本

`script/` 目录提供交互式安装向导，使用 `↑` / `↓` 选择、`Enter` 确认。
「一键安装」的流程是：

1. 询问安装位置（默认 `~/OpenOJ`，可直接回车）
2. 从 GitHub 克隆 `https://github.com/happycat184/openoj.git` 到该位置
3. 安装 Python 3.10+ 与 GCC/G++（已安装则跳过）
4. 创建 `.venv` 虚拟环境并安装 `requirements.txt` 中的依赖

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File script\install.ps1
```

Linux / macOS：

```bash
bash script/install.sh
```

说明：

- 目标目录为空或不存在时执行克隆；目录中已有本项目时不会重复克隆，可选择是否 `git pull`
- 安装路径会保存到 `%APPDATA%\OpenOJ\install-path.txt`（Windows）
  或 `~/.config/openoj/install-path`（Linux / macOS），下次启动自动读取
- 克隆需要 git，未安装时会尝试自动安装
- Windows 通过 `winget` 安装 Python、Git 和 GCC（WinLibs，失败时回退 MSYS2）
- Debian/Ubuntu、Fedora、Arch、openSUSE、Alpine 使用对应包管理器安装，需要 `sudo`
- macOS 使用 Homebrew 安装 Python，GCC 由 Xcode Command Line Tools 提供
- 在 Git Bash 中运行时会提示切换到 PowerShell 版向导
- 可通过环境变量 `OPENOJ_REPO_URL` 指定其他仓库地址（用于镜像或 Fork）
- 仅检查环境而不安装：`powershell -ExecutionPolicy Bypass -File script\install.ps1 -Check`
  或 `bash script/install.sh --check`

## 目录结构

```
OpenOJ/
├── app.py              # Flask 路由、登录鉴权、后台管理
├── db.py               # SQLite 数据层、建表与示例数据
├── judge.py            # 评测引擎：编译、执行、限时/限内存、输出比对
├── script/
│   ├── install.ps1     # Windows 交互式安装向导
│   └── install.sh      # Linux / macOS 交互式安装向导
├── openoj.db           # 运行时自动生成
├── work/               # 评测临时工作目录（自动创建/清理）
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   ├── js/ide-editor.js
│   ├── js/math.js
│   └── vendor/            # 本地 CodeMirror、KaTeX 资源
└── templates/
    ├── base.html
    ├── index.html
    ├── bank.html
    ├── search.html
    ├── problem.html
    ├── ide.html
    ├── discussions.html
    ├── discussion.html
    ├── discussion_form.html
    ├── submission.html
    ├── submissions.html
    ├── profile.html
    ├── leaderboard.html
    ├── _problem_body.html
    ├── _problem_table.html
    ├── login.html / register.html
    ├── error.html
    └── admin/
        ├── banks.html / bank_form.html
        ├── problems.html / problem_form.html
        ├── import.html / testcases.html
        └── dashboard.html / users.html
```

## 题库

- 首页展示全部题库，包括名称、简介、题目数和个人通过进度。
- 每个题库拥有独立页面 `/bank/<id>`，其中只显示该题库的题目。
- 管理员在「管理」→「题库管理」中新建、编辑、删除题库。
- 新建或编辑题目时必须选择所属题库，可随时将题目移动到其他题库。
- 「题目管理」支持按题库筛选；「导入题库」时需选择目标题库。
- 删除题库前必须先清空其中题目，且系统至少保留一个题库。
- 从旧版本升级时，已有题目会自动归入「默认题库」。

## 首页与搜索

- 首页只展示最多 10 道随机推荐题目，可通过「换一批」重新抽取，不会随题目总数增长而无限变长。
- 首页同时保留题库列表，可按题库进入对应题目列表。
- 搜索框位于首页，支持按题目标题、题目描述或题库名称搜索。
- 搜索结果按每页 20 条分页显示；搜索接口为 `/search?q=<关键词>`。

## 添加题目

1. 使用管理员账号登录，点击导航栏「管理」。
2. 如有需要，先在「题库管理」中创建题库。
3. 在「题目管理」中新建题目，选择所属题库，填写题面、样例、时间与内存限制。
4. 创建成功后进入「测试点」页面，逐条粘贴输入/输出，或上传 `.in` / `.out` 文件。
5. 保存后即可在对应题库中提交代码。

测试点保存时按顺序重新编号，输入与输出均为空的条目会被忽略。
文件上传会覆盖对应文本框中的内容，单个文件上限 4 MB。

## 批量导入题库（JSON）

管理员在「管理」→「题目管理」→「导入题库」中上传 JSON 文件或直接粘贴 JSON，
并选择**目标题库**，本次导入的所有题目都会归入该题库。
导入采用**追加**方式，不会修改或删除现有题目；整批数据校验通过后才会写入，
任一题目有误则整批取消。单个文件上限 8 MB。

根节点可以是 `{ "problems": [...] }`、单个题目对象，或题目数组。
每道题必须包含 `title` 与非空的 `test_cases`。

```json
{
  "problems": [
    {
      "title": "A+B Problem",
      "difficulty": "入门",
      "description": "输入两个整数 a 和 b，输出它们的和。",
      "input_format": "一行，包含两个整数 a 和 b。",
      "output_format": "输出一个整数，表示 a + b。",
      "sample_input": "1 2\n",
      "sample_output": "3\n",
      "hint": "",
      "time_limit_ms": 1000,
      "memory_limit_kb": 65536,
      "is_visible": true,
      "test_cases": [
        { "input": "1 2\n", "output": "3\n" },
        { "input": "-5 7\n", "output": "2\n" }
      ]
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 题目标题，最多 200 字符 |
| `description` | 否 | 题目描述，纯文本 |
| `input_format` / `output_format` | 否 | 输入/输出格式 |
| `sample_input` / `sample_output` | 否 | 样例 |
| `hint` | 否 | 提示 |
| `time_limit_ms` | 否 | 默认 1000，范围 100–60000 |
| `memory_limit_kb` | 否 | 默认 65536，范围 1024–1048576 |
| `is_visible` | 否 | 默认 `true` |
| `difficulty` | 否 | 入门 / 简单 / 中等 / 困难，默认 `简单` |
| `test_cases` | 是 | 非空数组，每项含字符串 `input` 与 `output` |

导入页面提供「下载示例 JSON」链接，可直接作为模板使用。

## 配置

可通过环境变量调整：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENOJ_HOST` | `127.0.0.1` | 监听地址 |
| `OPENOJ_PORT` | `5000` | 监听端口 |
| `OPENOJ_SECRET_KEY` | 开发用固定值 | Flask 会话密钥，部署前务必修改 |
| `OPENOJ_DB` | `./openoj.db` | SQLite 数据库路径 |
| `OPENOJ_DEBUG` | 关闭 | 设为 `1` 开启调试模式（不启用自动重载，避免评测线程被中断） |
| `OPENOJ_JUDGE_WORKERS` | `2` | 评测队列 worker 线程数（1–8） |

示例（Git Bash）：

```bash
OPENOJ_SECRET_KEY="change-me" OPENOJ_PORT=8000 python app.py
```

## 安全提示

- 本系统会**真实执行用户提交的代码**，仅使用超时与内存采样做限制，**不是安全沙箱**。
  请只在个人电脑或可信内网中使用，不要直接暴露到公网。
- 部署前请修改 `OPENOJ_SECRET_KEY` 与默认管理员密码。
- 评测使用运行 Flask 的同一个 Python 解释器。

## 实现说明

- 时间限制使用墙钟时间，从进程创建完成后开始计时（不计入系统创建进程的开销）；
  内存限制采样子进程的峰值工作集（Windows 使用
  `GetProcessMemoryInfo`，Linux 读取 `/proc/<pid>/status` 的 `VmHWM`）。
- 输出比对按行进行：忽略每行行尾空白与末尾空行。
- 总体状态取第一个未通过测试点的状态；用时/内存取所有测试点的最大值。
- 评测提交进入固定 worker 队列，页面通过 `/api/submission/<id>` 轮询，完成后自动刷新。
- 题面与讨论区使用 Markdown 渲染，KaTeX 处理 LaTeX；题面 HTML 默认被转义。
- IDE 使用本地 CodeMirror 5 提供语法高亮、行号、括号匹配和补全。
- CodeMirror 与 KaTeX 均为 MIT 许可，许可证文件位于 `static/vendor/` 对应目录。
