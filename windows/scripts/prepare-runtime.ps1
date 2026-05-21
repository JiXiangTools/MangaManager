param(
  [Parameter(Mandatory = $true)]
  [string]$PythonRoot,

  [Parameter(Mandatory = $true)]
  [string]$PostgresRoot
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WindowsDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $WindowsDir "..")
$RuntimeDir = Join-Path $WindowsDir "runtime"
$RuntimePython = Join-Path $RuntimeDir "python"
$RuntimePostgres = Join-Path $RuntimeDir "postgresql"
$BackendDir = Join-Path $RepoRoot "backend"

if (!(Test-Path (Join-Path $PythonRoot "python.exe"))) {
  throw "PythonRoot must contain python.exe: $PythonRoot"
}
if (!(Test-Path (Join-Path $PostgresRoot "bin\postgres.exe"))) {
  throw "PostgresRoot must contain bin\postgres.exe: $PostgresRoot"
}
if (!(Test-Path (Join-Path $PostgresRoot "bin\initdb.exe"))) {
  throw "PostgresRoot must contain bin\initdb.exe: $PostgresRoot"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
if (Test-Path $RuntimePython) {
  Remove-Item -Recurse -Force $RuntimePython
}
if (Test-Path $RuntimePostgres) {
  Remove-Item -Recurse -Force $RuntimePostgres
}

Copy-Item -Recurse -Force $PythonRoot $RuntimePython
Copy-Item -Recurse -Force $PostgresRoot $RuntimePostgres

$PythonExe = Join-Path $RuntimePython "python.exe"
$SitePackages = Join-Path $RuntimePython "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $SitePackages | Out-Null

$PthFiles = Get-ChildItem $RuntimePython -Filter "python*._pth" -ErrorAction SilentlyContinue
foreach ($Pth in $PthFiles) {
  $Content = Get-Content $Pth.FullName
  if ($Content -notcontains "import site") {
    Add-Content -Path $Pth.FullName -Value "import site"
  }
}

& $PythonExe -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Embedded Python must include pip. Install pip into $RuntimePython before running this script."
}

& $PythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
  throw "pip upgrade failed"
}

& $PythonExe -m pip install --target $SitePackages $BackendDir
if ($LASTEXITCODE -ne 0) {
  throw "backend dependency installation failed"
}

& node (Join-Path $ScriptDir "verify-runtime.js")
if ($LASTEXITCODE -ne 0) {
  throw "runtime verification failed"
}

Write-Host "Embedded runtime prepared under $RuntimeDir"

