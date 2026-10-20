# Устанавливает скиллы ui-ux-pro-max-skill и OmniRoute в %USERPROFILE%\.claude\skills (глобально).
# Существующие скиллы с тем же именем НЕ перезаписываются: они пропускаются и выводятся в отчёте.
# Сервер OmniRoute, claude-mem и Headroom скрипт не трогает.
#
# Использование:
#   .\install-global-skills.ps1 -DryRun   # только показать, что будет сделано
#   .\install-global-skills.ps1           # установить
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'

$Src  = Join-Path $HOME 'skill-sources'
$Dest = Join-Path $HOME '.claude\skills'
New-Item -ItemType Directory -Force -Path $Src, $Dest | Out-Null

function Get-Repo($url, $name) {
    $path = Join-Path $Src $name
    if (Test-Path (Join-Path $path '.git')) {
        Write-Host "[=] $name уже склонирован, используем как есть"
    } else {
        git clone --depth 1 $url $path
        if ($LASTEXITCODE -ne 0) { throw "git clone $name не удался" }
    }
}

$installed = @(); $skipped = @(); $bad = @()

function Install-Skill($dir) {
    $name = Split-Path $dir -Leaf
    if (-not (Test-Path (Join-Path $dir 'SKILL.md'))) { $script:bad += "$name (нет SKILL.md)"; return }
    $target = Join-Path $Dest $name
    if (Test-Path $target) { $script:skipped += $name; return }
    if ($DryRun) { $script:installed += "$name (dry-run)"; return }
    Copy-Item -Recurse -LiteralPath $dir -Destination $target
    $script:installed += $name
}

Get-Repo 'https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git' 'ui-ux-pro-max-skill'
Get-Repo 'https://github.com/diegosouzapw/OmniRoute.git' 'OmniRoute'

Get-ChildItem -Directory (Join-Path $Src 'ui-ux-pro-max-skill\.claude\skills') | ForEach-Object { Install-Skill $_.FullName }
Get-ChildItem -Directory (Join-Path $Src 'OmniRoute\skills') | ForEach-Object { Install-Skill $_.FullName }

Write-Host ""
Write-Host "Установлено ($($installed.Count)):";  $installed | ForEach-Object { Write-Host "  - $_" }
Write-Host "Пропущено, т.к. такое имя уже есть ($($skipped.Count)):"; $skipped | ForEach-Object { Write-Host "  - $_" }
Write-Host "Проблемы ($($bad.Count)):"; $bad | ForEach-Object { Write-Host "  - $_" }

Write-Host ""
Write-Host "Проверка полей name/description:"
Get-ChildItem -Directory $Dest | ForEach-Object {
    $f = Join-Path $_.FullName 'SKILL.md'
    if (Test-Path $f) {
        $head = Get-Content -LiteralPath $f -TotalCount 15
        if (-not ($head -match '^name:') -or -not ($head -match '^description:')) {
            Write-Host "  ! $($_.Name): нет name/description в начале"
        }
    }
}
Write-Host "Готово. Перезапустите Claude Code (или откройте новый чат), чтобы скиллы подхватились."
