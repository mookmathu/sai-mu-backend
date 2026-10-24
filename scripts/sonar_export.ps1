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
