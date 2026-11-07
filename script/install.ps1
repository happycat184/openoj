<#
.SYNOPSIS
    OpenOJ 交互式安装向导（Windows PowerShell 5.1+ / PowerShell 7+）
.DESCRIPTION
    使用 ↑ / ↓ 选择、Enter 确认。一键安装会先询问安装位置，从 GitHub 克隆项目，
    然后自动安装 Python 3.10+、GCC/G++，创建 .venv 并安装依赖。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File script\install.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File script\install.ps1 -Check
#>
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ScriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$RepoUrl = if ($env:OPENOJ_REPO_URL) { $env:OPENOJ_REPO_URL } else { 'https://github.com/happycat184/openoj.git' }
$ConfigDir = Join-Path $env:APPDATA 'OpenOJ'
$ConfigFile = Join-Path $ConfigDir 'install-path.txt'

$script:ProjectRoot = $null
$script:VenvDir = $null
$script:VenvPython = $null
$script:Requirements = $null
$script:AppEntry = $null

# ---------------------------------------------------------------- output

function Write-Title([string]$Text) {
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('-' * 52) -ForegroundColor DarkGray
}

function Write-Step([string]$Text) { Write-Host ('[*] ' + $Text) -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host ('[+] ' + $Text) -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host ('[!] ' + $Text) -ForegroundColor Yellow }
function Write-Err([string]$Text) { Write-Host ('[-] ' + $Text) -ForegroundColor Red }

function Pause-Menu {
    if ([Console]::IsInputRedirected) { return }
    Write-Host ''
    [void](Read-Host '按回车返回菜单')
}

function Confirm-YesNo {
    param(
        [string]$Question,
        [bool]$DefaultYes = $true
    )
    if ([Console]::IsInputRedirected) { return $DefaultYes }
    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    $answer = Read-Host ($Question + ' ' + $suffix)
    if (-not $answer) { return $DefaultYes }
    return ($answer -match '^[Yy]')
}

# ---------------------------------------------------------------- menu

function Read-Menu {
    param(
        [string]$Title,
        [string[]]$Items
    )

    if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
        Write-Host ''
        Write-Host $Title -ForegroundColor Cyan
        for ($i = 0; $i -lt $Items.Count; $i++) {
            Write-Host ('  {0}) {1}' -f ($i + 1), $Items[$i])
        }
        while ($true) {
            $answer = Read-Host '请输入编号后回车'
            $number = 0
            if ([int]::TryParse($answer, [ref]$number) -and $number -ge 1 -and $number -le $Items.Count) {
                return ($number - 1)
            }
            Write-Host '输入无效，请重新输入。' -ForegroundColor Yellow
        }
    }

    Write-Host ''
    Write-Host $Title -ForegroundColor Cyan
    $width = (($Items | ForEach-Object { $_.Length } | Measure-Object -Maximum).Maximum) + 6
    $top = [Console]::CursorTop
    $selected = 0

    while ($true) {
        [Console]::SetCursorPosition(0, $top)
        for ($i = 0; $i -lt $Items.Count; $i++) {
            $prefix = if ($i -eq $selected) { '  > ' } else { '    ' }
            $line = ($prefix + $Items[$i]).PadRight($width)
            if ($i -eq $selected) {
                Write-Host $line -ForegroundColor Black -BackgroundColor Cyan
            } else {
                Write-Host $line
            }
        }
        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            ([ConsoleKey]::UpArrow) { $selected = ($selected - 1 + $Items.Count) % $Items.Count }
            ([ConsoleKey]::DownArrow) { $selected = ($selected + 1) % $Items.Count }
            ([ConsoleKey]::Enter) {
                [Console]::SetCursorPosition(0, $top + $Items.Count)
                return $selected
            }
            ([ConsoleKey]::Escape) {
                [Console]::SetCursorPosition(0, $top + $Items.Count)
                return -1
            }
        }
    }
}

# ---------------------------------------------------------------- project path

function Get-SavedPath {
    if (-not (Test-Path -LiteralPath $ConfigFile)) { return $null }
    try {
        $content = (Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 -ErrorAction Stop)
        $content = $content.TrimStart([char]0xFEFF).Trim()
        if ($content) { return $content }
    } catch { }
    return $null
}

function Save-ProjectPath([string]$Path) {
    try {
        if (-not (Test-Path -LiteralPath $ConfigDir)) {
            New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($ConfigFile, $Path, $utf8NoBom)
    } catch {
        Write-Warn '无法保存安装路径，下次启动需要重新输入。'
    }
}

function Set-ProjectRoot([string]$Path) {
    $script:ProjectRoot = $Path
    $script:VenvDir = Join-Path $Path '.venv'
    $script:VenvPython = Join-Path $script:VenvDir 'Scripts\python.exe'
    $script:Requirements = Join-Path $Path 'requirements.txt'
    $script:AppEntry = Join-Path $Path 'app.py'
    if ($Path -and (Test-Path -LiteralPath $Path)) {
        try { Set-Location -LiteralPath $Path } catch { }
    }
}

function Get-DefaultRoot {
    $saved = Get-SavedPath
    if ($saved -and (Test-Path (Join-Path $saved 'app.py'))) { return $saved }
    $repoRoot = Split-Path -Parent $ScriptRoot
    if (Test-Path (Join-Path $repoRoot 'app.py')) { return $repoRoot }
    return (Join-Path $env:USERPROFILE 'OpenOJ')
}

function Expand-UserPath([string]$Path) {
    if ($Path -eq '~') { return $env:USERPROFILE }
    if ($Path.StartsWith('~\') -or $Path.StartsWith('~/')) {
        return Join-Path $env:USERPROFILE $Path.Substring(2)
    }
    return [Environment]::ExpandEnvironmentVariables($Path)
}

function Read-InstallPath {
    $default = $script:ProjectRoot
    if (-not $default) { $default = Get-DefaultRoot }

    Write-Host ''
    Write-Host '请输入 OpenOJ 的安装位置（将在此目录克隆项目）' -ForegroundColor Cyan
    Write-Host ('  默认：' + $default) -ForegroundColor DarkGray

    while ($true) {
        $answer = Read-Host '安装位置（回车使用默认，输入 q 取消）'
        if ($answer -eq 'q' -or $answer -eq 'Q') { return $null }
        if (-not $answer) { $answer = $default }
        $answer = Expand-UserPath $answer
        if (-not [System.IO.Path]::IsPathRooted($answer)) {
            $answer = Join-Path (Get-Location) $answer
        }
        try {
            return [System.IO.Path]::GetFullPath($answer)
        } catch {
            Write-Warn '路径无效，请重新输入。'
        }
    }
}

# ---------------------------------------------------------------- detection

function Get-PythonInfo {
    $candidates = @(
        @{ Exe = 'py'; Prefix = @('-3') },
        @{ Exe = 'python'; Prefix = @() },
        @{ Exe = 'python3'; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $argList = @($candidate.Prefix) + @('--version')
        try {
            $output = & $candidate.Exe @argList 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
        $text = ((@($output) | ForEach-Object { [string]$_ }) -join ' ').Trim()
        $match = [regex]::Match($text, '(\d+)\.(\d+)\.(\d+)')
        if (-not $match.Success) { continue }
        $version = [version]($match.Groups[1].Value + '.' + $match.Groups[2].Value + '.' + $match.Groups[3].Value)
        return [pscustomobject]@{
            Exe = $candidate.Exe
            Prefix = $candidate.Prefix
            Version = $version
            Ok = ($version -ge [version]'3.10.0')
            Path = $command.Source
        }
    }
    return $null
}

function Get-ToolInfo([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { return $null }
    try {
        $output = & $Name '--version' 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    $first = if ($output) { ([string](@($output)[0])).Trim() } else { $Name }
    return [pscustomobject]@{
        Name = $Name
        Path = $command.Source
        Version = $first
    }
}

function Refresh-Path {
    try {
        $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $user = [Environment]::GetEnvironmentVariable('Path', 'User')
        $parts = @()
        foreach ($chunk in @($machine, $user, $env:Path)) {
            if (-not $chunk) { continue }
            foreach ($entry in ($chunk -split ';')) {
                if ($entry -and ($parts -notcontains $entry)) { $parts += $entry }
            }
        }
        $env:Path = $parts -join ';'
    } catch {
        # 忽略 PATH 刷新失败
    }
}

function Add-PathEntry([string]$Directory) {
    if (-not $Directory -or -not (Test-Path $Directory)) { return }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($userPath) { $entries = @($userPath -split ';' | Where-Object { $_ }) }
    if ($entries -notcontains $Directory) {
        try {
            [Environment]::SetEnvironmentVariable('Path', (($entries + $Directory) -join ';'), 'User')
        } catch {
            # 忽略注册表写入失败，至少刷新当前会话
        }
    }
    if (($env:Path -split ';') -notcontains $Directory) {
        $env:Path = $env:Path + ';' + $Directory
    }
}

function Test-Dependencies {
    if (-not $script:VenvPython -or -not (Test-Path $script:VenvPython)) { return $false }
    & $script:VenvPython -c 'import flask, markdown_it' 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Test-Environment {
    $python = Get-PythonInfo
    $gcc = Get-ToolInfo 'gcc'
    $gpp = Get-ToolInfo 'g++'
    $projectReady = [bool]($script:ProjectRoot -and (Test-Path (Join-Path $script:ProjectRoot 'app.py')))
    return [bool]($projectReady -and $python -and $python.Ok -and $gcc -and $gpp)
}

function Show-Environment {
    Write-Title '环境检查'

    if ($script:ProjectRoot -and (Test-Path (Join-Path $script:ProjectRoot 'app.py'))) {
        Write-Ok ('项目目录：' + $script:ProjectRoot)
    } else {
        $target = if ($script:ProjectRoot) { $script:ProjectRoot } else { '(未设置)' }
        Write-Warn ('项目尚未安装：' + $target)
        Write-Host '  选择「一键安装」可从此位置克隆项目。' -ForegroundColor DarkGray
    }

    Write-Host ('  系统：' + [System.Environment]::OSVersion.VersionString)

    $python = Get-PythonInfo
    if ($python) {
        if ($python.Ok) {
            Write-Ok ('Python {0}  {1}' -f $python.Version, $python.Path)
        } else {
            Write-Warn ('Python {0} 版本过低（需要 3.10+）：{1}' -f $python.Version, $python.Path)
        }
    } else {
        Write-Warn '未找到 Python 3.10+'
    }

    foreach ($tool in @('gcc', 'g++')) {
        $info = Get-ToolInfo $tool
        if ($info) {
            Write-Ok ('{0}：{1}' -f $tool, $info.Version)
        } else {
            Write-Warn ('未找到 {0}' -f $tool)
        }
    }

    $git = Get-ToolInfo 'git'
    if ($git) {
        Write-Ok ('git：' + $git.Version)
    } else {
        Write-Warn '未找到 git（一键安装需要它来克隆项目）'
    }

    if ($script:VenvPython -and (Test-Path $script:VenvPython)) {
        Write-Ok ('虚拟环境：' + $script:VenvDir)
    } else {
        Write-Warn '虚拟环境未创建'
    }

    if (Test-Dependencies) {
        Write-Ok 'Python 依赖已安装（flask、markdown-it-py）'
    } else {
        Write-Warn 'Python 依赖未安装'
    }

    if ($script:ProjectRoot -and (Test-Path (Join-Path $script:ProjectRoot 'openoj.db'))) {
        Write-Ok '数据库 openoj.db 已存在'
    } else {
        Write-Warn '数据库尚未创建（首次启动时自动创建）'
    }
}

# ---------------------------------------------------------------- installers

function Find-PythonInstallDir {
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:ProgramFiles 'Python')
    )
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path $root)) { continue }
        $exe = Get-ChildItem -Path $root -Filter 'python.exe' -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\Lib\\' } |
            Select-Object -First 1
        if ($exe) { return $exe.DirectoryName }
    }
    return $null
}

function Find-GccBin {
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $dirs = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'WinLibs|mingw|MSYS2' }
        foreach ($dir in $dirs) {
            $gcc = Get-ChildItem -Path $dir.FullName -Filter 'gcc.exe' -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($gcc) { return $gcc.DirectoryName }
        }
    }
    return $null
}

function Install-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Ok ('git 已就绪：' + (Get-ToolInfo 'git').Version)
        return $true
    }

    Write-Step '未找到 git，尝试自动安装...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Err '未找到 winget，无法自动安装 git。'
        Write-Host '请从 https://git-scm.com/download/win 安装 Git 后重新运行本脚本。'
        return $false
    }

    & winget install --id Git.Git --exact --source winget --silent `
        --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Ok 'git 安装完成'
        return $true
    }

    Write-Err '自动安装 git 失败，请手动安装后重试。'
    return $false
}

function Install-Python {
    $python = Get-PythonInfo
    if ($python -and $python.Ok) {
        Write-Ok ('Python {0} 已就绪：{1}' -f $python.Version, $python.Path)
        return $true
    }

    Write-Step '未找到可用的 Python 3.10+，尝试自动安装...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Err '未找到 winget，无法自动安装 Python。'
        Write-Host '请从 https://www.python.org/downloads/ 安装 Python 3.10+，'
        Write-Host '安装时勾选「Add python.exe to PATH」，然后重新运行本脚本。'
        return $false
    }

    foreach ($packageId in @('Python.Python.3.13', 'Python.Python.3.12')) {
        Write-Step ('通过 winget 安装 {0} ...' -f $packageId)
        & winget install --id $packageId --exact --source winget --silent `
            --accept-package-agreements --accept-source-agreements
        Refresh-Path
        $installDir = Find-PythonInstallDir
        if ($installDir) {
            Add-PathEntry $installDir
            Refresh-Path
        }
        $python = Get-PythonInfo
        if ($python -and $python.Ok) {
            Write-Ok ('Python {0} 安装完成：{1}' -f $python.Version, $python.Path)
            return $true
        }
    }

    Write-Err '自动安装 Python 失败。'
    Write-Host '请手动安装 Python 3.10+ 后重新运行本脚本。'
    return $false
}

function Install-Gcc {
    $gcc = Get-ToolInfo 'gcc'
    $gpp = Get-ToolInfo 'g++'
    if ($gcc -and $gpp) {
        Write-Ok ('GCC / G++ 已就绪：' + $gcc.Version)
        return $true
    }

    Write-Step '未找到 GCC / G++，尝试自动安装...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Err '未找到 winget，无法自动安装 GCC。'
        Write-Host '请安装 WinLibs 或 MSYS2 的 GCC/G++，并将 bin 目录加入 PATH。'
        return $false
    }

    Write-Step '尝试通过 winget 安装 WinLibs GCC ...'
    & winget install --id BrechtSanders.WinLibs.POSIX.UCRT --exact --source winget --silent `
        --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if ((Get-ToolInfo 'gcc') -and (Get-ToolInfo 'g++')) {
        Write-Ok 'GCC / G++ 安装完成'
        return $true
    }

    $binDir = Find-GccBin
    if ($binDir) {
        Add-PathEntry $binDir
        Refresh-Path
        if ((Get-ToolInfo 'gcc') -and (Get-ToolInfo 'g++')) {
            Write-Ok ('GCC / G++ 安装完成：' + $binDir)
            return $true
        }
    }

    Write-Step '尝试通过 MSYS2 安装 GCC ...'
    & winget install --id MSYS2.MSYS2 --exact --source winget --silent `
        --accept-package-agreements --accept-source-agreements
    $msysRoot = @('C:\msys64', (Join-Path $env:SystemDrive 'msys64')) |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
    if ($msysRoot) {
        $pacman = Join-Path $msysRoot 'usr\bin\pacman.exe'
        if (Test-Path $pacman) {
            Write-Step '通过 pacman 安装 mingw-w64-ucrt-x86_64-gcc ...'
            & $pacman -S --noconfirm --needed mingw-w64-ucrt-x86_64-gcc
            $ucrtBin = Join-Path $msysRoot 'ucrt64\bin'
            if (Test-Path (Join-Path $ucrtBin 'gcc.exe')) {
                Add-PathEntry $ucrtBin
                Refresh-Path
                if ((Get-ToolInfo 'gcc') -and (Get-ToolInfo 'g++')) {
                    Write-Ok ('GCC / G++ 安装完成：' + $ucrtBin)
                    return $true
                }
            }
        }
    }

    Write-Err '自动安装 GCC / G++ 失败。'
    Write-Host '请手动安装 MSYS2（https://www.msys2.org/），'
    Write-Host '在 MSYS2 中执行 pacman -S mingw-w64-ucrt-x86_64-gcc，'
    Write-Host '并把 C:\msys64\ucrt64\bin 加入 PATH。'
    return $false
}

function Setup-Venv {
    $python = Get-PythonInfo
    if (-not $python -or -not $python.Ok) {
        Write-Err '未找到可用的 Python 3.10+，无法创建虚拟环境。'
        return $false
    }
    if (-not $script:ProjectRoot -or -not (Test-Path (Join-Path $script:ProjectRoot 'app.py'))) {
        Write-Err '项目尚未安装，无法安装依赖。'
        return $false
    }

    if (-not (Test-Path $script:VenvPython)) {
        Write-Step ('创建虚拟环境：' + $script:VenvDir)
        & $python.Exe @(@($python.Prefix) + @('-m', 'venv', $script:VenvDir))
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $script:VenvPython)) {
            Write-Err '创建虚拟环境失败。'
            return $false
        }
    } else {
        Write-Ok ('虚拟环境已存在：' + $script:VenvDir)
    }

    Write-Step '升级 pip ...'
    & $script:VenvPython -m pip install --upgrade pip --disable-pip-version-check
    Write-Step '安装 Python 依赖 ...'
    & $script:VenvPython -m pip install -r $script:Requirements --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Err '依赖安装失败，请检查网络连接后重试。'
        return $false
    }

    if (-not (Test-Dependencies)) {
        Write-Err '依赖校验失败：flask 或 markdown-it-py 无法导入。'
        return $false
    }
    Write-Ok 'Python 依赖安装完成'
    return $true
}

# ---------------------------------------------------------------- repository

function Ensure-Repository([string]$Target) {
    $targetApp = Join-Path $Target 'app.py'

    if (Test-Path -LiteralPath $targetApp) {
        Write-Ok ('检测到已有 OpenOJ 项目：' + $Target)
        if (Test-Path (Join-Path $Target '.git')) {
            if (Confirm-YesNo '是否拉取最新代码？' $true) {
                Push-Location -LiteralPath $Target
                try {
                    & git pull --ff-only
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warn '拉取失败，将继续使用当前代码。'
                    }
                } catch {
                    Write-Warn '拉取失败，将继续使用当前代码。'
                } finally {
                    Pop-Location
                }
            }
        }
        return $true
    }

    if (Test-Path -LiteralPath $Target) {
        if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
            Write-Err ('目标路径不是目录：' + $Target)
            return $false
        }
        $entries = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue)
        if ($entries.Count -gt 0) {
            Write-Err ('目录非空且不是 OpenOJ 项目：' + $Target)
            Write-Host '请选择一个空目录或新的安装位置。'
            return $false
        }
    } else {
        $parent = Split-Path -Parent $Target
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            try {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            } catch {
                Write-Err ('无法创建目录：' + $parent)
                return $false
            }
        }
    }

    if (-not (Install-Git)) { return $false }

    Write-Step ('从 GitHub 克隆 OpenOJ 到 ' + $Target)
    & git clone --depth 1 $RepoUrl $Target
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $targetApp)) {
        Write-Err '克隆失败，请检查网络连接或仓库地址。'
        Write-Host ('仓库地址：' + $RepoUrl)
        return $false
    }

    Write-Ok '项目克隆完成'
    return $true
}

# ---------------------------------------------------------------- actions

function Invoke-OneClick {
    Write-Title '一键安装'

    $target = Read-InstallPath
    if (-not $target) {
        Write-Warn '已取消安装。'
        return
    }

    if (-not (Ensure-Repository $target)) { return }

    Set-ProjectRoot $target
    Save-ProjectPath $target

    if (-not (Install-Python)) {
        Write-Err 'Python 未就绪，安装中止。'
        return
    }
    if (-not (Install-Gcc)) {
        Write-Warn 'GCC / G++ 未能自动安装，评测 C / C++ 前需要手动补齐。'
    }

    if (Setup-Venv) {
        Write-Title '安装完成'
        Write-Ok '现在可以选择「启动 OpenOJ」开始使用。'
        Write-Host ('  项目目录：' + $Target)
        Write-Host '  默认地址：http://127.0.0.1:5000'
        Write-Host '  默认管理员：admin / admin123（首次登录后请修改密码）'
    } else {
        Write-Err '依赖安装失败，请检查网络后重试。'
    }
}

function Invoke-StepMenu {
    while ($true) {
        $choice = Read-Menu '分步安装（↑/↓ 选择，Enter 确认）' @(
            '安装 / 修复 Python',
            '安装 / 修复 GCC / G++',
            '创建虚拟环境并安装依赖',
            '返回主菜单'
        )
        switch ($choice) {
            0 { if (Install-Python) { Write-Ok 'Python 就绪' }; Pause-Menu }
            1 { if (Install-Gcc) { Write-Ok 'GCC / G++ 就绪' }; Pause-Menu }
            2 { if (Setup-Venv) { Write-Ok '依赖安装完成' }; Pause-Menu }
            default { return }
        }
    }
}

function Start-OpenOJ {
    if (-not $script:VenvPython -or -not (Test-Path $script:VenvPython)) {
        Write-Err '虚拟环境尚未创建，请先执行「一键安装」。'
        return
    }

    $port = if ($env:OPENOJ_PORT) { $env:OPENOJ_PORT } else { '5000' }
    $url = "http://127.0.0.1:$port"

    Write-Title '启动 OpenOJ'
    Write-Host ('项目目录：' + $script:ProjectRoot) -ForegroundColor DarkGray
    Write-Host ('访问地址：' + $url) -ForegroundColor Green
    Write-Host '默认管理员：admin / admin123（首次登录后请修改密码）'
    Write-Host '按 Ctrl+C 停止服务。'
    Write-Host ''

    $opener = Start-Job -ScriptBlock {
        param($target)
        Start-Sleep -Seconds 2
        Start-Process $target
    } -ArgumentList $url

    try {
        & $script:VenvPython $script:AppEntry
    } finally {
        Stop-Job $opener -ErrorAction SilentlyContinue
        Remove-Job $opener -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------- main

function Invoke-Main {
    Set-ProjectRoot (Get-DefaultRoot)

    if ($Check) {
        Show-Environment
        if (Test-Environment) { exit 0 } else { exit 1 }
    }

    Write-Host ''
    Write-Host '  OpenOJ 安装向导' -ForegroundColor White
    Write-Host ('  项目目录：' + $script:ProjectRoot) -ForegroundColor DarkGray

    while ($true) {
        $choice = Read-Menu '请选择操作（↑/↓ 选择，Enter 确认）' @(
            '一键安装（克隆项目 + Python + GCC + 依赖）',
            '检查环境',
            '分步安装',
            '启动 OpenOJ',
            '退出'
        )
        switch ($choice) {
            0 { Invoke-OneClick; Pause-Menu }
            1 { Show-Environment; Pause-Menu }
            2 { Invoke-StepMenu }
            3 { Start-OpenOJ; return }
            default { return }
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Main
}
