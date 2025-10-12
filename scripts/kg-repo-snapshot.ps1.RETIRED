# kg-repo-snapshot.ps1
# Document governance script with linter integration
# Creates snapshots and tracks repository changes for governance compliance

# --- Settings ---
$RepoPath  = "C:\Users\Kent\Vaults-repos\kg-automation"   # Repository path
$DropRoot  = "C:\Users\Kent\Dropbox\Automation"           # global Automation root (Windows)
$StateDir  = Join-Path $DropRoot ".state"                 # global
$QueueDir  = Join-Path $DropRoot ".queue"                 # global
$CanonFile = Join-Path $RepoPath "governance\canon.json"  # optional linter inputs
$Bootstrap = Join-Path $RepoPath "ai-context-bootstrap.md"

# --- Prep ---
New-Item -ItemType Directory -Force -Path $StateDir,$QueueDir | Out-Null
Set-Location $RepoPath
$commit = (git rev-parse HEAD) 2>$null
$branch = (git rev-parse --abbrev-ref HEAD) 2>$null
$now    = (Get-Date).ToUniversalTime().ToString("s") + "Z"

# --- File inventory ---
$files = Get-ChildItem -Recurse -File -Force `
  | Where-Object { $_.FullName -notmatch '\\\.git\\' } `
  | ForEach-Object {
      [pscustomobject]@{
        path       = $_.FullName.Substring($RepoPath.Length+1).Replace("\","/")
        size       = $_.Length
        mtime      = $_.LastWriteTimeUtc.ToString("s") + "Z"
        git_status = if ((git ls-files --error-unmatch $_.FullName 2>$null)) { "tracked" } else { "untracked" }
      }
  }

# --- Snapshot ---
$snap = [pscustomobject]@{
  repo = "kg-automation"; branch=$branch; commit=$commit; generated_at=$now
  sot_file = "ai-context-bootstrap.md"
  files = $files
}
$snapPath = Join-Path $StateDir "repo_snapshot.json"
$snap | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $snapPath

# --- Diff vs previous snapshot ---
$prevPath = Join-Path $StateDir "repo_snapshot.prev.json"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$riskNotes = @()

if (Test-Path $prevPath) {
  $prev = Get-Content $prevPath -Raw | ConvertFrom-Json
  $prevSet = $prev.files.path
  $currSet = $files.path
  $added   = $currSet | Where-Object { $_ -notin $prevSet }
  $deleted = $prevSet | Where-Object { $_ -notin $currSet }
  $modified = @()
  
  foreach ($f in ($currSet | Where-Object { $_ -in $prevSet })) {
    $pf = $prev.files | Where-Object { $_.path -eq $f } | Select-Object -First 1
    $cf = $files       | Where-Object { $_.path -eq $f } | Select-Object -First 1
    if ($pf.mtime -ne $cf.mtime -or $pf.size -ne $cf.size) { $modified += $f }
  }
  
  # --- Abstract drift / integrity check (optional) ---
  $lintScript = Join-Path $RepoPath "scripts\doc_linter.ps1"
  if (Test-Path $lintScript) {
    $lintOut = & powershell -NoProfile -ExecutionPolicy Bypass $lintScript `
      -RepoPath $RepoPath -CanonFile $CanonFile -Bootstrap $Bootstrap -ChangedPaths ($added + $modified)
    if ($LASTEXITCODE -ne 0) { $riskNotes += @{ path="(lint)"; note="Linter error (non-zero exit)" } }
    elseif ($lintOut) {
      try { $riskNotes += (ConvertFrom-Json $lintOut) } catch { $riskNotes += @{ path="(lint)"; note="$lintOut" } }
    }
  }
  
  $diff = [pscustomobject]@{
    repo="kg-automation"; from_commit=$prev.commit; to_commit=$commit; generated_at=$now
    changes   = [pscustomobject]@{ added=$added; modified=$modified; deleted=$deleted; moved=@() }
    risk_notes= $riskNotes
    signing   = [pscustomobject]@{ algo="none"; by=$env:COMPUTERNAME }
  }
  $diff | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $QueueDir "repo_diff_$stamp.json")
}

Copy-Item $snapPath $prevPath -Force
