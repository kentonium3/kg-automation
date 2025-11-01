Set-Location 'C:\Users\Kent\Vaults-repos\kg-automation'

# Pull latest with rebase
git pull --rebase

# Stage the Copilot instructions file
git add .github\copilot-instructions.md

# Commit only if there are staged changes
$staged = git diff --staged --name-only
if ($staged) {
    git commit -m 'chore: add copilot instructions'
} else {
    Write-Host 'No staged changes to commit'
}

# Push to origin/main
git push origin main
