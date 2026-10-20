# Installs skills from ui-ux-pro-max-skill and OmniRoute into %USERPROFILE%\.claude\skills (global).
# Existing skills with the same name are NOT overwritten: they are skipped and listed in the report.
# Does not touch the OmniRoute server, claude-mem or Headroom.
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 misreads UTF-8 without BOM).
#
# Usage:
#   .\install-global-skills.ps1 -DryRun   # only show what would be done
#   .\install-global-skills.ps1           # install
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'

$Src  = Join-Path $HOME 'skill-sources'
$Dest = Join-Path $HOME '.claude\skills'
New-Item -ItemType Directory -Force -Path $Src, $Dest | Out-Null

function Get-Repo($url, $name) {
    $path = Join-Path $Src $name
    if (Test-Path (Join-Path $path '.git')) {
        Write-Host "[=] $name already cloned, using as is"
    } else {
        git clone --depth 1 $url $path
        if ($LASTEXITCODE -ne 0) { throw "git clone $name failed" }
    }
}

$installed = @(); $skipped = @(); $bad = @()

function Install-Skill($dir) {
    $name = Split-Path $dir -Leaf
    if (-not (Test-Path (Join-Path $dir 'SKILL.md'))) { $script:bad += "$name (no SKILL.md)"; return }
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
Write-Host "Installed ($($installed.Count)):";  $installed | ForEach-Object { Write-Host "  - $_" }
Write-Host "Skipped, name already exists ($($skipped.Count)):"; $skipped | ForEach-Object { Write-Host "  - $_" }
Write-Host "Problems ($($bad.Count)):"; $bad | ForEach-Object { Write-Host "  - $_" }

Write-Host ""
Write-Host "Checking name/description fields:"
Get-ChildItem -Directory $Dest | ForEach-Object {
    $f = Join-Path $_.FullName 'SKILL.md'
    if (Test-Path $f) {
        $head = Get-Content -LiteralPath $f -TotalCount 15
        if (-not ($head -match '^name:') -or -not ($head -match '^description:')) {
            Write-Host "  ! $($_.Name): no name/description at the top"
        }
    }
}
Write-Host "Done. Restart Claude Code (or open a new chat) so the skills are picked up."
