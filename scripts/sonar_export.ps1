# ส่งออก issue จาก SonarQube ในเครื่อง (http://localhost:9000) เป็นไฟล์ sonar_issues.json
# ใช้: powershell -ExecutionPolicy Bypass -File scripts\sonar_export.ps1 -Token <TOKEN>
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Project = "Sai-Mu-Backend",
    [string]$Host_ = "http://localhost:9000"
)
$pair = "$($Token):"
$auth = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$all = @()
$page = 1
do {
    $url = "$Host_/api/issues/search?componentKeys=$Project&statuses=OPEN,CONFIRMED&ps=500&p=$page"
    $r = Invoke-RestMethod -Uri $url -Headers @{ Authorization = $auth }
    foreach ($i in $r.issues) {
        $all += [pscustomobject]@{
            rule     = $i.rule
            severity = $i.severity
            type     = $i.type
            file     = ($i.component -replace '^[^:]+:', '')
            line     = $i.line
            message  = $i.message
            impacts  = ($i.impacts | ForEach-Object { "$($_.softwareQuality):$($_.severity)" }) -join ","
        }
    }
    $page++
} while (($page - 1) * 500 -lt $r.paging.total)
$all | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 sonar_issues.json
Write-Host "บันทึก $($all.Count) issue ลง sonar_issues.json แล้ว"

# --- ตัวเลขสรุปโปรเจกต์ (ขนาดโค้ด, เกรด, coverage, quality gate) -> sonar_measures.json
try {
    $metrics = "ncloc,coverage,line_coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots,reliability_rating,security_rating,sqale_rating,alert_status,tests,files"
    $m = Invoke-RestMethod -Uri "$Host_/api/measures/component?component=$Project&metricKeys=$metrics" -Headers @{ Authorization = $auth }
    $gate = Invoke-RestMethod -Uri "$Host_/api/qualitygates/project_status?projectKey=$Project" -Headers @{ Authorization = $auth }
    @{ measures = $m.component.measures; gate = $gate.projectStatus } | ConvertTo-Json -Depth 6 |
        Out-File -Encoding utf8 sonar_measures.json
    Write-Host "บันทึกตัวเลขสรุปลง sonar_measures.json แล้ว"
} catch {
    Write-Host "ดึงตัวเลขสรุปไม่ได้: $($_.Exception.Message)"
}
