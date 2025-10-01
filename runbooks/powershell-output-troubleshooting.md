# PowerShell Output Visibility Troubleshooting Guide

**Document Purpose**: Provide comprehensive context and diagnostic procedures for recurring PowerShell output visibility issues when working with Claude on Windows systems.

**Last Updated**: 2025-10-01  
**Systems Affected**: Office3 (Windows 11), historically Office2 (Windows 10)  
**Current Status**: ✅ Resolved on Office3 as of 2025-10-01

---

## Issue History

### Problem Description
Claude periodically reports inability to see PowerShell command output when using the `Windows-MCP:Powershell-Tool`. This issue has occurred intermittently across multiple projects and sessions, creating a significant blocker for automation work.

### Symptom Pattern
- Claude invokes PowerShell commands
- Commands execute (Status Code: 0) but Response appears empty or truncated
- Claude reports "I cannot see the output" or similar
- Issue is intermittent - sometimes works, sometimes doesn't
- Tends to reoccur after weeks/months even when "resolved"

### Root Causes Identified
Through extensive diagnostics across Office2 and Office3 machines:

1. **Encoding Issues**: Console output encoding mismatches (non-UTF8)
2. **Stream Redirection**: PowerShell preference variables interfering with output visibility
3. **Console State**: Console/buffer not properly initialized in automation contexts
4. **Context Loss**: Different PowerShell process contexts losing output routing

---

## Current Solution (Office3)

### Reliability Script Implementation

**Location**: `C:\Users\Kent\Dropbox\Migration\Scripts\PowerShell_Output_Reliability.ps1`

**Auto-loaded via PowerShell Profile**: `C:\Users\Kent\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`

The script implements a 3-tier reliability system:

#### 1. Prevention Measures (Auto-Applied)
Runs on every PowerShell session initialization:

- **Console Initialization**: Sets console title to verify console availability
- **UTF-8 Enforcement**: Forces UTF-8 encoding on all streams
  - `[Console]::OutputEncoding = UTF8`
  - `[Console]::InputEncoding = UTF8`
  - `$OutputEncoding = UTF8`
- **Stream Preference Reset**: Clears redirection issues
  - `$ErrorActionPreference = 'Continue'`
  - `$WarningPreference = 'Continue'`
  - `$VerbosePreference = 'SilentlyContinue'`
  - `$DebugPreference = 'SilentlyContinue'`
- **Buffer Sizing**: Sets consistent 120x3000 buffer
- **Fallback Functions**: Creates robust output functions with 3-tier fallback chain

#### 2. Diagnostic Functions

**`Test-PowerShellOutput [-Detailed]`**
- Tests all output streams (Write-Output, Write-Host, Write-Information)
- Checks console state, buffer settings, encoding configuration
- Validates execution context and permissions
- Optional detailed tests: file I/O, variable capture

**`Debug-PowerShellOutput`**
- Emergency diagnostic when output fails
- Tries multiple output methods to find what works
- Checks for context changes (PID, Host, User)
- Attempts console reset

#### 3. Robust Output Functions

**`Write-RobustOutput 'message' 'color'`**
- 3-tier fallback: Write-Host → Write-Output → Console.WriteLine()

**`Write-RobustError 'message'`**
- Color-coded error output with fallbacks

**`Write-RobustSuccess 'message'`**
- Color-coded success output with fallbacks

---

## What the Script IS and IS NOT

### ✅ The Script IS:
- **A SOLUTION** that proactively fixes known issues
- A diagnostic toolkit for identifying new problems
- A set of reliable output functions with fallbacks
- Proven to resolve encoding, console state, and stream redirection issues

### ❌ The Script IS NOT:
- The cause of output visibility problems
- Interfering with or blocking output
- Project-specific to the Migration work (despite filename history)
- Something that should be disabled or bypassed

### Critical Note for Claude
**When Claude encounters PowerShell output visibility issues:**

1. **DO NOT** blame or suspect the reliability script
2. **DO NOT** suggest disabling or bypassing it
3. **DO** recognize the script is attempting to FIX the problem
4. **DO** use the diagnostic functions provided by the script

The reliability script loads on every PowerShell invocation and its presence in the output (the "Loading PowerShell Output Reliability..." message) indicates it's working as designed.

---

## Diagnostic Procedure

### When Output Visibility Issues Occur

**Step 1: Verify Script is Loading**
Look for this in PowerShell output:
```
Loading PowerShell Output Reliability...
PowerShell Output Reliability loaded.
```

If NOT present → Profile may have been modified or script file missing

**Step 2: Run Basic Output Test**
```powershell
Write-Host "Test: $(Get-Date)"; echo "Echo test"; "String test"
```

This tests three different output methods. If Claude can see ANY output, script is working.

**Step 3: Run Detailed Diagnostic**
```powershell
Test-PowerShellOutput -Detailed
```

This will output comprehensive diagnostic information about:
- Output streams status
- Console state
- Buffer settings
- Encoding configuration
- Execution context
- File I/O capability
- Variable capture

**Step 4: Check Available Functions**
```powershell
Get-Command Write-Robust*, Test-PowerShell*, Debug-PowerShell* | Select-Object Name
```

Verifies reliability functions are loaded in current session.

**Step 5: Emergency Diagnostic**
If steps 1-4 show problems:
```powershell
Debug-PowerShellOutput
```

This tries every possible output method to find what still works.

**Step 6: Manual Prevention Re-Application**
```powershell
Set-PowerShellOutputPreventive
```

Forces re-application of all prevention measures.

---

## Escalation Scenarios

### If Script is Loading but Output Still Fails

**Possible causes:**
1. MCP tool layer issue (between Claude and PowerShell)
2. Claude's result parsing issue
3. New/unknown PowerShell context problem
4. System-level console redirection

**Investigation steps:**
1. Capture exact error message/symptom
2. Run `Test-PowerShellOutput -Detailed` and capture full output
3. Check if simple commands work: `Get-Date`, `$PSVersionTable`
4. Test if using `Write-RobustOutput` instead of `Write-Host` helps
5. Document any pattern: specific commands failing? All commands? Time-based?

### If Script is Not Loading

**Possible causes:**
1. Profile not being executed
2. Script file moved/deleted
3. Path changed in profile
4. Execution policy blocking

**Investigation steps:**
```powershell
# Check if profile exists and is executed
Test-Path $PROFILE
Get-Content $PROFILE

# Check if script exists
Test-Path "C:\Users\Kent\Dropbox\Migration\Scripts\PowerShell_Output_Reliability.ps1"

# Check execution policy
Get-ExecutionPolicy

# Manually source the script
. "C:\Users\Kent\Dropbox\Migration\Scripts\PowerShell_Output_Reliability.ps1"
```

---

## Machine-Specific Notes

### Office3 (Windows 11) - Current System
- **Status**: ✅ Working as of 2025-10-01
- **Script**: `PowerShell_Output_Reliability.ps1` (renamed from diagnostic version)
- **Functions**: `Write-Robust*` naming convention
- **Profile Path**: `C:\Users\Kent\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`

### Office2 (Windows 10) - Legacy System
- **Status**: Using original script for migration work
- **Script**: `PowerShell_Output_Diagnostic.ps1` (original version)
- **Functions**: `Write-Migration*` naming convention
- **Note**: Both scripts exist in same directory to support both machines

---

## Historical Context

### Resolution Timeline

**Phase 1: Initial Problems (Office2)**
- Intermittent output visibility issues during migration project
- Diagnosis revealed encoding and console state problems
- Created `PowerShell_Output_Diagnostic.ps1` with prevention measures

**Phase 2: Migration to Office3**
- Copied diagnostic script to Office3
- Issue recurred despite script presence
- Confusion arose from "Migration/Diagnostic" naming implying the script was the problem

**Phase 3: Clarification and Renaming (2025-10-01)**
- Extensive testing confirmed script is working correctly
- Renamed to `PowerShell_Output_Reliability.ps1` on Office3
- Updated functions to `Write-Robust*` convention
- Created this troubleshooting guide to prevent future confusion

---

## Key Insights for Future Sessions

### For Claude:
1. **The reliability script is your ally**, not an adversary
2. Its presence in output indicates proper functioning
3. When output fails, use the diagnostic functions it provides
4. Don't suggest disabling it - that removes safeguards
5. The script addresses KNOWN issues; new failures need investigation

### For Kent:
1. If Claude reports output visibility issues, point to this document
2. Run `Test-PowerShellOutput -Detailed` first
3. Share diagnostic results with Claude for analysis
4. Pattern recognition is key: what's different when it fails?
5. Consider if Windows updates or system changes coincide with failures

---

## Related Files

- **Reliability Script**: `C:\Users\Kent\Dropbox\Migration\Scripts\PowerShell_Output_Reliability.ps1`
- **Legacy Script (Office2)**: `C:\Users\Kent\Dropbox\Migration\Scripts\PowerShell_Output_Diagnostic.ps1`
- **PowerShell Profile**: `C:\Users\Kent\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`
- **This Guide**: `~/Vaults-repos/kg-automation/runbooks/powershell-output-troubleshooting.md`

---

## Appendix: Technical Details

### UTF-8 Encoding Issue
Windows PowerShell defaults to console codepage encoding (often CP437 or CP850 in US). When MCP tools expect UTF-8 but receive other encodings, character data can be corrupted or lost entirely. The reliability script forces UTF-8 on all streams to ensure consistent encoding.

### Stream Preference Variables
PowerShell's preference variables (`$ErrorActionPreference`, `$WarningPreference`, etc.) can redirect or suppress streams. In automation contexts, these may be set to values that prevent output visibility. The script resets them to known-good values.

### Console vs Host
PowerShell has both a `[Console]` class (direct .NET console access) and `$Host.UI` (PowerShell host interface). Some automation contexts have one but not the other. The fallback functions try both paths to maximize reliability.

### Buffer Size Issues
Small console buffers can truncate output. Setting a large buffer (120x3000) ensures even lengthy outputs are captured. The buffer is set via `$Host.UI.RawUI.BufferSize` when available.

---

**End of Troubleshooting Guide**

*When in doubt, the script is helping, not hindering. Diagnostics before assumptions.*
