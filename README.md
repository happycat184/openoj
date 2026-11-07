# OpenOJ

一个基于 Flask + HTML5 + CSS3 + JavaScript 的在线评测系统（Online Judge），
使用 SQLite 存储数据，支持 **C**、**C++**、**Python** 三种语言的真实编译与评测。

界面采用 Body–Nav–Content 结构，浅色直角风格，无圆角、无阴影、无渐变、无动画。

## 功能

- 题库列表、题目详情、样例展示、我的通过状态
- 独立的 IDE 编写页：左侧题面、右侧编辑器，带行号、光标位置与基础语法补全
- 多语言提交：C（GCC）、C++（G++）、Python 3
- 真实编译执行，逐测试点显示结果
- 每个测试点显示为一个正方形：中间为状态码，偏下方为用时/内存
- 后台评测线程 + 前端自动轮询刷新
- 完整用户系统：注册、登录、个人主页、通过题目统计、排行榜、修改密码
- 管理员后台：在线新建/编辑题目、上传/编辑测试点、JSON 题库批量导入、隐藏题目、用户角色管理、重新评测
- CSRF 保护、密码哈希存储

## IDE 页面

在题目页点击「开始编写」进入 `/problem/<id>/ide`：

- 左半边为题目描述、格式、样例与提示，可独立滚动
- 右半边为代码编写区，支持 C / C++ / Python 基础补全
  - 输入关键字或已有标识符时自动弹出候选
  - `↑` / `↓` 选择，`Tab` 或 `Enter` 补全，`Esc` 关闭
  - `Ctrl+Space` 手动唤出补全
  - 回车自动缩进：继承当前行缩进，`{`、`[`、`(` 或 Python 的 `:` 后自动增加一级
  - C/C++ 在空行输入 `}` 时自动回退一级缩进
  - `Tab` 插入 4 个空格，`Ctrl+Enter` 提交
- 草稿按题目与语言自动保存在浏览器本地

## 评分状态

| 状态 | 颜色 | 含义 |
| --- | --- | --- |
| AC | 绿色 | 通过该测试点 / 通过 |
| WA | 红色 | 答案错误 |
| TLE | 黑色 | 超时 |
| MLE | 黑色 | 超内存 |
| ULE | 黑色 | 未知错误（运行时错误、内部错误等） |
| CE | 黑色 | 编译错误（未运行任何测试点，不计入测试点方块） |

测试点方块中的时间/内存格式为 `12.34ms/1024.00KB`。

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

## 目录结构

```
OpenOJ/
├── app.py              # Flask 路由、登录鉴权、后台管理
├── db.py               # SQLite 数据层、建表与示例数据
├── judge.py            # 评测引擎：编译、执行、限时/限内存、输出比对
├── openoj.db           # 运行时自动生成
├── work/               # 评测临时工作目录（自动创建/清理）
├── static/
│   ├── css/style.css
│   └── js/app.js
└── templates/
    ├── base.html
    ├── index.html
    ├── problem.html
    ├── ide.html
    ├── submission.html
    ├── submissions.html
    ├── profile.html
    ├── leaderboard.html
    ├── _problem_body.html
    ├── login.html / register.html
    ├── error.html
    └── admin/
```

## 添加题目

1. 使用管理员账号登录，点击导航栏「管理」。
2. 在「题目管理」中新建题目，填写题面、样例、时间与内存限制。
3. 创建成功后进入「测试点」页面，逐条粘贴输入/输出，或上传 `.in` / `.out` 文件。
4. 保存后即可在题库中提交代码。

测试点保存时按顺序重新编号，输入与输出均为空的条目会被忽略。
文件上传会覆盖对应文本框中的内容，单个文件上限 4 MB。

## 批量导入题库（JSON）

管理员在「管理」→「题目管理」→「导入题库」中上传 JSON 文件或直接粘贴 JSON。
导入采用**追加**方式，不会修改或删除现有题目；整批数据校验通过后才会写入，
任一题目有误则整批取消。单个文件上限 8 MB。

根节点可以是 `{ "problems": [...] }`、单个题目对象，或题目数组。
每道题必须包含 `title` 与非空的 `test_cases`。

```json
{
  "problems": [
    {
      "title": "A+B Problem",
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

- 时间限制使用墙钟时间；内存限制采样子进程的峰值工作集（Windows 使用
  `GetProcessMemoryInfo`，Linux 读取 `/proc/<pid>/status` 的 `VmHWM`）。
- 输出比对按行进行：忽略每行行尾空白与末尾空行。
- 总体状态取第一个未通过测试点的状态；用时/内存取所有测试点的最大值。
- 评测在后台线程中进行，页面通过 `/api/submission/<id>` 轮询，完成后自动刷新。
