# Windows-MCP External Executable Workaround - UPDATED

**Status**: Active workaround for Windows-MCP limitations  
**Platform**: Windows only (Claude using Windows-MCP extension)  
**Last Updated**: 2025-10-06  
**Critical Discovery**: Windows-MCP cannot capture output from functions OR external executables

---

## Problem Summary - UPDATED

Windows-MCP has TWO output capture limitations:
1. **External .exe programs** produce no visible output
2. **PowerShell functions** produce no visible output

### What Works
✅ Direct inline PowerShell code (not in functions)  
✅ Native PowerShell cmdlets called directly  
✅ Direct Start-Process with file redirection (inline)

### What Doesn't Work  
❌ External .exe programs called directly  
❌ PowerShell functions (ANY function)  
❌ Redirection operators (`>`, `*>`, `2>&1`)

---

## The Workaround - INLINE PATTERN

Since functions don't work, use this **inline pattern** every time:

###  Git Operations Pattern

```powershell
# Navigate to repo
cd C:\Users\Kent\Vaults-repos\kg-automation

# Create temp file
$tempOut = "$env:TEMP\git_output.txt"

# Run git with output redirect
Start-Process -FilePath "C:\Program Files\Git\bin\git.exe" `
              -ArgumentList "status", "--short" `
              -WorkingDirectory (Get-Location) `
              -NoNewWindow `
              -Wait `
              -RedirectStandardOutput $tempOut

# Wait for file write
Start-Sleep -Milliseconds 100

# Read and display
$result = Get-Content $tempOut -Raw
Write-Host $result

# Cleanup
Remove-Item $tempOut
```

### Common Git Operations

**Status:**
```powershell
$tempOut = "$env:TEMP\git_status.txt"
Start-Process -FilePath "C:\Program Files\Git\bin\git.exe" -ArgumentList "status", "--short" -WorkingDirectory "C:\Users\Kent\Vaults-repos\kg-automation" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host $result; Remove-Item $tempOut
```

**Log (last 5 commits):**
```powershell
$tempOut = "$env:TEMP\git_log.txt"
Start-Process -FilePath "C:\Program Files\Git\bin\git.exe" -ArgumentList "log", "--oneline", "-5" -WorkingDirectory "C:\Users\Kent\Vaults-repos\kg-automation" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host $result; Remove-Item $tempOut
```

**Add files:**
```powershell
$tempOut = "$env:TEMP\git_add.txt"
Start-Process -FilePath "C:\Program Files\Git\bin\git.exe" -ArgumentList "add", "." -WorkingDirectory "C:\Users\Kent\Vaults-repos\kg-automation" -NoNewWindow -Wait -RedirectStandardOutput $tempOut -RedirectStandardError "$env:TEMP\git_add_err.txt"
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw -ErrorAction SilentlyContinue; if ($result) { Write-Host $result }
$err = Get-Content "$env:TEMP\git_add_err.txt" -Raw -ErrorAction SilentlyContinue; if ($err) { Write-Host $err -ForegroundColor Red }
Remove-Item $tempOut, "$env:TEMP\git_add_err.txt" -ErrorAction SilentlyContinue
```

**Commit:**
```powershell
$tempOut = "$env:TEMP\git_commit.txt"
Start-Process -FilePath "C:\Program Files\Git\bin\git.exe" -ArgumentList "commit", "-m", "Your commit message here" -WorkingDirectory "C:\Users\Kent\Vaults-repos\kg-automation" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host $result; Remove-Item $tempOut
```

### System Commands Pattern

**Who am I:**
```powershell
$tempOut = "$env:TEMP\whoami.txt"
Start-Process -FilePath "whoami.exe" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host "Current user: $result"; Remove-Item $tempOut
```

**Hostname:**
```powershell
$tempOut = "$env:TEMP\hostname.txt"
Start-Process -FilePath "hostname.exe" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host "Computer name: $result"; Remove-Item $tempOut
```

**IP Config:**
```powershell
$tempOut = "$env:TEMP\ipconfig.txt"
Start-Process -FilePath "ipconfig.exe" -ArgumentList "/all" -NoNewWindow -Wait -RedirectStandardOutput $tempOut
Start-Sleep -Milliseconds 100
$result = Get-Content $tempOut -Raw; Write-Host $result; Remove-Item $tempOut
```

---

## For AI Systems (Claude)

###  CRITICAL: Always Use Inline Pattern

**DO NOT** try to create functions - they won't work in Windows-MCP.

**Every time you need to run an external executable:**

1. Create temp file: `$tempOut = "$env:TEMP\command_output.txt"`
2. Use Start-Process with `-RedirectStandardOutput $tempOut`
3. Add sleep: `Start-Sleep -Milliseconds 100`
4. Read file: `$result = Get-Content $tempOut -Raw`
5. Display: `Write-Host $result`
6. Cleanup: `Remove-Item $tempOut`

### Common External Commands

**Git** (most frequent):
- Use full path: `C:\Program Files\Git\bin\git.exe`
- Always specify `-WorkingDirectory` for repo operations
- Common args: `"status"`, `"log", "--oneline", "-5"`, `"add", "."`, etc.

**System Info**:
- `whoami.exe` - current user
- `hostname.exe` - computer name  
- `ipconfig.exe` - network info
- `systeminfo.exe` - full system details

**Network**:
- `ping.exe` - Args: `"google.com", "-n", "4"`
- `netstat.exe` - Args: `"-an"`
- `tracert.exe` - Args: `"google.com"`

### Decision Tree

```
Need to run a command?
│
├─ Is it Get-*, Set-*, New-*, etc.? (PowerShell cmdlet)
│  └─ YES → Run directly (e.g., Get-Date, Get-Location)
│
├─ Is it a built-in alias? (cd, ls, pwd)
│  └─ YES → Run directly
│
├─ Is it an external .exe or system command?
│  └─ YES → Use inline pattern with Start-Process + file redirect
│
└─ Not sure?
   └─ Try running it directly first
   └─ If no output appears → Use inline pattern
```

---

## Why Functions Don't Work

Windows-MCP appears to have limitations with:
1. Capturing stdout/stderr from external processes
2. Capturing output from PowerShell functions

The only reliable method is **inline code** with explicit file redirection.

---

## For Kent

### When Claude Forgets

If Claude tries to run git or other external commands directly and reports "no output":

**Remind Claude:**
> "Use the inline pattern with Start-Process and file redirection. See windows-mcp-external-commands.md"

### Manual Usage

When you need to run git yourself in PowerShell with Windows-MCP:
1. Use the pattern above
2. Or open a regular PowerShell window (not through Claude)
3. Or use Git GUI/GitHub Desktop

---

## Status and Future

### Current Status
- **Inline Pattern**: ✅ Working
- **Function Wrapper**: ❌ Doesn't work (Windows-MCP limitation)
- **Discord Inquiry**: Submitted 2025-10-01, no response yet

### If Discord/GitHub Fixes This
1. Test the fix
2. Update documentation
3. Simplify to direct calls or function wrappers
4. Archive inline pattern as historical workaround

---

## Related Documentation

- **PowerShell Output Troubleshooting**: `runbooks/powershell-output-troubleshooting.md`
- **Bootstrap Document**: `ai-agents/ai-context-bootstrap.md`
- **Session Continuity**: `runbooks/session-continuity.md`

---

**Last Updated**: 2025-10-06  
**Status**: Inline pattern working, awaiting Windows-MCP fixes
