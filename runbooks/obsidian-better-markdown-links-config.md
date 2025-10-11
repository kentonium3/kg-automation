# Obsidian Better Markdown Links - Configuration & Troubleshooting

**Plugin**: [Better Markdown Links](https://github.com/mnaoumov/obsidian-better-markdown-links)  
**Version Documented**: 3.1.4  
**Platforms**: Mac/Windows (settings identical)  
**Last Updated**: 2025-10-05

## Overview

The Better Markdown Links plugin converts Obsidian [[Wikilinks]] to standards-compliant Markdown links with angle brackets for readability and relative paths for compatibility.

**Example conversion:**
- From: `[[My Note]]`
- To: `[My Note](<./My Note.md>)`

## Critical Configuration Requirements

The plugin will NOT function if Obsidian's core link settings conflict with Markdown link generation. Both settings must be configured correctly.

### Required Obsidian Settings

**Location**: Settings → Files and links

| Setting | Required Value | Why |
|---------|---------------|-----|
| **Use [[Wikilinks]]** | **DISABLED (OFF)** | Plugin respects this global setting. If enabled, plugin assumes you want Wikilinks and won't convert. |
| **New link format** | **Relative path to file** | Enables the plugin to generate proper relative paths with `./` prefix. |

### Plugin Settings

**Location**: Settings → Community Plugins → Better Markdown Links (gear icon)

Recommended configuration:

```json
{
  "shouldUseAngleBrackets": true,
  "shouldUseLeadingDotForRelativePaths": true,
  "shouldUseLeadingSlashForAbsolutePaths": true,
  "shouldAutomaticallyConvertNewLinks": true,
  "shouldAutomaticallyUpdateLinksOnRenameOrMove": true,
  "shouldPreserveExistingLinkStyle": false,
  "shouldAllowEmptyEmbedAlias": true,
  "shouldIncludeAttachmentExtensionToEmbedAlias": false,
  "excludePaths": [],
  "includePaths": []
}
```

**Key settings explained:**
- `shouldUseAngleBrackets`: Generates `<path>` style links for readability with spaces
- `shouldUseLeadingDotForRelativePaths`: Adds `./` prefix for unambiguous relative paths
- `shouldAutomaticallyConvertNewLinks`: Auto-converts manually entered links
- `shouldPreserveExistingLinkStyle`: Set to false to convert ALL links to consistent format

## Available Commands

Access via Command Palette (Ctrl+P / Cmd+P):

1. **Convert links in current file** - Converts all links in active note
2. **Convert links in current folder** - Batch converts all notes in current folder
3. **Convert links in entire vault** - Batch converts all notes in vault

## Common Issues & Solutions

### Issue: Commands Run But Nothing Happens

**Symptoms:**
- Commands appear in palette and execute
- No errors in console
- Links remain unchanged
- No debug output

**Root Cause:** Conflicting Obsidian core settings

**Solution:**
1. Open Settings → Files and links
2. **Disable** "Use [[Wikilinks]]"
3. Set "New link format" to **"Relative path to file"**
4. Retry conversion command

### Issue: Duplicate Plugin Listings in Settings

**Symptoms:**
- Two "Better Markdown Links" entries in Community Plugins list
- Commands registered but don't execute
- Settings may appear for both entries

**Root Cause:** Corrupted plugin installation (often from interrupted installs or sync conflicts)

**Solution:**
1. Uninstall ALL instances via Obsidian UI
2. Close Obsidian completely
3. Verify manual cleanup:
   - Delete: `[vault]/.obsidian/plugins/better-markdown-links/` (if exists)
   - Edit: `[vault]/.obsidian/community-plugins.json` - remove plugin entry
4. Reopen Obsidian
5. Fresh install from Community Plugins

### Issue: No Debug Output When Enabled

**Symptoms:**
- `window.DEBUG.enable('better-markdown-links')` returns `undefined`
- No console output when running commands
- Commands appear to execute silently

**Expected Behavior:**
- `undefined` return is NORMAL (command doesn't return a value)
- Debug messages should appear AFTER running conversion commands
- If NO messages appear after command execution = silent failure (see conflicting settings above)

## Diagnostic Procedures

### Quick Verification Test

1. Create test note with these links:
   ```markdown
   [[Test Note]]
   [[Another Note with Spaces]]
   ```

2. Run: "Better Markdown Links: Convert links in current file"

3. Expected result:
   ```markdown
   [Test Note](<./Test Note.md>)
   [Another Note with Spaces](<./Another Note with Spaces.md>)
   ```

### Developer Console Diagnostics

Open Developer Console (Ctrl+Shift+I / Cmd+Option+I):

**Check plugin loaded:**
```javascript
app.plugins.plugins['better-markdown-links']
// Should return object, not undefined
```

**Check plugin enabled:**
```javascript
app.plugins.enabledPlugins.has('better-markdown-links')
// Should return true
```

**Check commands registered:**
```javascript
Object.keys(app.commands.commands).filter(cmd => cmd.includes('better'))
// Should return array with 3 commands:
// - better-markdown-links:convert-links-in-current-file
// - better-markdown-links:convert-links-in-current-folder
// - better-markdown-links:convert-links-in-entire-vault
```

**Enable debug mode:**
```javascript
window.DEBUG.enable('better-markdown-links');
// Returns: undefined (this is normal)
// Then run a conversion command and watch for console output
```

## Platform-Specific Notes

### Mac
- Vault paths typically: `~/Documents/` or `~/Library/CloudStorage/Dropbox/`
- Plugin config: `[vault]/.obsidian/plugins/better-markdown-links/`

### Windows  
- Vault paths typically: `C:\Users\[username]\Documents\` or `C:\Users\[username]\Dropbox\`
- Plugin config: `[vault]\.obsidian\plugins\better-markdown-links\`

**Settings behavior is identical across platforms.** If it works on Mac but not Windows (or vice versa), check the core Obsidian settings, not the plugin settings.

## Best Practices

1. **Configure once per vault** - Settings are vault-specific, stored in `.obsidian/`
2. **Test on small subset first** - Use "current file" before "entire vault"
3. **Commit before bulk conversion** - If vault is version controlled, commit before running vault-wide conversion
4. **Verify git compatibility** - The `./` prefix ensures links work in GitHub/GitLab markdown renderers
5. **Sync conflicts** - If vault syncs between devices, ensure consistent Obsidian settings on all devices

## References

- [Plugin GitHub](https://github.com/mnaoumov/obsidian-better-markdown-links)
- [Plugin Documentation](https://github.com/mnaoumov/obsidian-better-markdown-links/blob/main/README.md)
- [Debugging Guide](https://github.com/mnaoumov/obsidian-dev-utils/blob/main/docs/debugging.md)

## Troubleshooting History

### 2025-10-05: Windows Silent Failure
- **Issue**: Commands registered but no conversion happening, no debug output
- **Cause**: "Use [[Wikilinks]]" was enabled in Obsidian core settings
- **Resolution**: Disabled Wikilinks, set "New link format" to "Relative path to file"
- **Lesson**: Plugin respects global link settings; conflicting settings cause silent failure

---

*Part of Kent Gale Automation Project - kg-automation repository*
