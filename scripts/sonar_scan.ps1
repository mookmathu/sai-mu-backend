# รันเทสต์วัด coverage -> แก้ path ใน coverage.xml ให้ Docker มองเห็น -> สแกน SonarQube
# ใช้: powershell -ExecutionPolicy Bypass -File scripts\sonar_scan.ps1 -Token <TOKEN>
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Project = "Sai-Mu-Backend"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pytest tests --cov=app --cov-report=xml
if ($LASTEXITCODE -ne 0) { Write-Host "เทสต์ไม่ผ่าน หยุดก่อนสแกน"; exit 1 }

# path ของ Windows (D:\sai_mu_backend\app) -> path ใน container (/usr/src/app)
$xml = [IO.File]::ReadAllText((Resolve-Path coverage.xml), [Text.Encoding]::UTF8)
$xml = [regex]::Replace($xml, '<source>[^<]*</source>', '<source>/usr/src/app</source>')
[IO.File]::WriteAllText((Join-Path (Get-Location).Path 'coverage.xml'), $xml, (New-Object Text.UTF8Encoding($false)))

docker run --rm -e SONAR_HOST_URL=http://host.docker.internal:9000 -e SONAR_TOKEN=$Token `
    -v "$((Get-Location).Path):/usr/src" sonarsource/sonar-scanner-cli "-Dsonar.projectKey=$Project"
