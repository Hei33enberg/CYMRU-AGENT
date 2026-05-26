# Cymru-OH Windows installer builder (S20, LINEAR-2069)
#
# Wymagania:
#   - Python 3.11+
#   - PyInstaller (auto-install jeśli brakuje)
#   - NSIS (opcjonalnie dla .exe installer-a — bez tego dostaniesz pojedynczy .exe)
#
# Output: dist/cymru-oh-windows-<version>.exe
# Plus: sha256 hash zapisany do dist/cymru-oh-windows-<version>.sha256

$ErrorActionPreference = "Stop"

$VERSION = (Get-Content "$PSScriptRoot\..\cymru_oh.py" | Select-String 'CYMRU_OH_VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "🏗  Building Cymru-OH v$VERSION for Windows…"

# Verify Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "Python not found. Install Python 3.11+ from python.org first."
  exit 1
}

# Install PyInstaller if missing
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "📦 Installing PyInstaller…"
  python -m pip install --quiet pyinstaller
}

# Build
$DistDir = "$PSScriptRoot\dist"
$BuildDir = "$PSScriptRoot\build"
$AgentRoot = "$PSScriptRoot\.."

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "🚀 Running PyInstaller…"
Push-Location $AgentRoot
try {
  python -m PyInstaller `
    --onefile `
    --name "cymru-oh-windows-$VERSION" `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $BuildDir `
    --collect-submodules agent `
    --collect-submodules bridges `
    --collect-submodules tools `
    --hidden-import "httpx" `
    --hidden-import "supabase" `
    --console `
    "cymru_oh.py"
} finally {
  Pop-Location
}

# Compute SHA-256
$ExePath = "$DistDir\cymru-oh-windows-$VERSION.exe"
if (-not (Test-Path $ExePath)) {
  Write-Error "Build failed — $ExePath not found"
  exit 2
}

$Hash = (Get-FileHash -Algorithm SHA256 $ExePath).Hash.ToLower()
$Hash | Out-File -Encoding ascii "$DistDir\cymru-oh-windows-$VERSION.sha256"

$Size = (Get-Item $ExePath).Length
Write-Host ""
Write-Host "✅ Built: $ExePath"
Write-Host "   Size: $([math]::Round($Size / 1MB, 2)) MB"
Write-Host "   SHA256: $Hash"
Write-Host ""
Write-Host "📤 Następny krok: upload na GitHub Releases (lub get.cymru.ai/installers/)"
Write-Host "   Update manifest.json:"
Write-Host "     platforms.windows.url     = <release URL>"
Write-Host "     platforms.windows.sha256  = $Hash"
Write-Host "     platforms.windows.size_bytes = $Size"
