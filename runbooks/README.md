# Runbooks Documentation

## Overview
Operational procedures, troubleshooting guides, and emergency protocols.

## Documents  
- 🚧 session-continuity.md - Maintaining context across AI sessions
- 🚧 ai-troubleshooting.md - Common AI collaboration issues
- ✅ **powershell-output-troubleshooting.md** - PowerShell output visibility issues and diagnostic procedures
- ✅ **windows-mcp-external-commands.md** - Workaround for external executable output capture (Windows only)

## Status
- PowerShell troubleshooting guide: Complete and actively maintained
- Other documents are stubs awaiting content development

## Quick Reference

### PowerShell Output Issues
If Claude reports inability to see PowerShell output:
1. Point Claude to `powershell-output-troubleshooting.md`
2. Run `Test-PowerShellOutput -Detailed` and share results
3. Remember: The reliability script is a solution, not a problem

### Windows-MCP External Executables (Windows Only)
Claude **cannot see output** from external .exe programs (git, ipconfig, etc.):
1. Use `Invoke-ExternalCommand` wrapper for ALL external executables
2. Example: `Invoke-ExternalCommand -Command "git" -Arguments "status"`
3. See `windows-mcp-external-commands.md` for complete details and command list
4. If Claude forgets and reports "no output" → remind to use wrapper
