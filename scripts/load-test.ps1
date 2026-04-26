param(
    [string]$Url = "http://localhost:8000/chat",
    [int]$Requests = 10,
    [int]$Concurrency = 5,
    [string]$Message = "load-test ping",
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

if ($Requests -lt 1) {
    throw "Requests must be >= 1."
}
if ($Concurrency -lt 1) {
    throw "Concurrency must be >= 1."
}

function Receive-CompletedJobs {
    param(
        [ref]$Jobs,
        [ref]$Results
    )

    $completed = @($Jobs.Value | Where-Object { $_.State -in @("Completed", "Failed", "Stopped") })
    foreach ($job in $completed) {
        $Results.Value += Receive-Job -Job $job -Wait -AutoRemoveJob
        [void]$Jobs.Value.Remove($job)
    }
}

$requestJob = {
    param(
        [string]$Url,
        [string]$Message,
        [int]$Index,
        [int]$TimeoutSeconds
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
    try {
        $formFields = [System.Collections.Generic.List[System.Collections.Generic.KeyValuePair[string, string]]]::new()
        $formFields.Add([System.Collections.Generic.KeyValuePair[string, string]]::new("message", "$Message #$Index"))
        $formFields.Add([System.Collections.Generic.KeyValuePair[string, string]]::new("history", "[]"))
        $formFields.Add([System.Collections.Generic.KeyValuePair[string, string]]::new("attached_filename", ""))
        $content = [System.Net.Http.FormUrlEncodedContent]::new($formFields)

        try {
            $response = $client.PostAsync($Url, $content).GetAwaiter().GetResult()
            $null = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $stopwatch.Stop()
            [pscustomobject]@{
                Index      = $Index
                Success    = $response.IsSuccessStatusCode
                StatusCode = [int]$response.StatusCode
                DurationMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
                Error      = $null
            }
        } finally {
            $content.Dispose()
        }
    } catch {
        $stopwatch.Stop()
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        [pscustomobject]@{
            Index      = $Index
            Success    = $false
            StatusCode = $statusCode
            DurationMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
            Error      = $_.Exception.Message
        }
    } finally {
        $client.Dispose()
    }
}

function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$Percentile
    )

    if ($Values.Count -eq 0) {
        return 0
    }

    $sorted = @($Values | Sort-Object)
    $rank = [math]::Ceiling(($Percentile / 100.0) * $sorted.Count)
    $index = [math]::Max([int]$rank - 1, 0)
    return [math]::Round($sorted[$index], 2)
}

$jobs = [System.Collections.Generic.List[System.Management.Automation.Job]]::new()
$results = @()

for ($i = 1; $i -le $Requests; $i++) {
    while ($jobs.Count -ge $Concurrency) {
        Wait-Job -Job $jobs -Any | Out-Null
        Receive-CompletedJobs -Jobs ([ref]$jobs) -Results ([ref]$results)
    }

    $job = Start-Job -ScriptBlock $requestJob -ArgumentList $Url, $Message, $i, $TimeoutSeconds
    $jobs.Add($job)
}

if ($jobs.Count -gt 0) {
    Wait-Job -Job $jobs | Out-Null
    Receive-CompletedJobs -Jobs ([ref]$jobs) -Results ([ref]$results)
}

$results = @($results | Sort-Object Index)
$failures = @($results | Where-Object { -not $_.Success })
$durations = @($results | ForEach-Object { [double]$_.DurationMs })
$p50 = Get-Percentile -Values $durations -Percentile 50
$p95 = Get-Percentile -Values $durations -Percentile 95

Write-Host "Completed $($results.Count) POST requests against $Url"
Write-Host "  Concurrency: $Concurrency"
Write-Host "  Successes:   $($results.Count - $failures.Count)"
Write-Host "  Failures:    $($failures.Count)"
Write-Host "  p50:         ${p50} ms"
Write-Host "  p95:         ${p95} ms"

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Failures:"
    foreach ($failure in $failures) {
        Write-Host "  #$($failure.Index): status=$($failure.StatusCode) error=$($failure.Error)"
    }
    exit 1
}
