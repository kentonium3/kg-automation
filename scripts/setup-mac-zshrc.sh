#!/bin/bash

# Script to update .zshrc with development environment configurations
# Created: 2025-11-30

echo "Backing up current .zshrc to .zshrc.backup..."
cp ~/.zshrc ~/.zshrc.backup.$(date +%Y%m%d_%H%M%S)

# Check if configurations already exist to avoid duplicates
echo "Adding development environment configurations to .zshrc..."

# Create a temporary file with the additions
cat << 'EOF' > /tmp/zshrc_additions

# ===== Development Environment Configuration =====
# Added by kg-automation setup script

# Homebrew (Intel Mac at /usr/local)
if [[ -f /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

# VS Code command line tools
if [[ -d "/Applications/Visual Studio Code.app" ]]; then
    export PATH="/Applications/Visual Studio Code.app/Contents/Resources/app/bin:$PATH"
fi

# Python from Homebrew (Python 3.13)
# This ensures pip3 and python3 from Homebrew are found first
if [[ -d "/usr/local/opt/python@3.13/libexec/bin" ]]; then
    export PATH="/usr/local/opt/python@3.13/libexec/bin:$PATH"
fi

# Node from Homebrew
if [[ -d "/usr/local/opt/node/bin" ]]; then
    export PATH="/usr/local/opt/node/bin:$PATH"
fi

# Development aliases
alias gs='git status'
alias gc='git commit -v'
alias gp='git push'
alias gpl='git pull'
alias gd='git diff'
alias gb='git branch'
alias gco='git checkout'
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'

# Project navigation shortcuts
alias repos='cd ~/repos'
alias kga='cd ~/repos/kg-automation'
alias intent='cd ~/repos/intentional'
alias sb='cd ~/second-brain'
alias vault='cd ~/second-brain/notes'

# Python/pip aliases for clarity
alias pip='pip3'
alias python='python3'

# Show current git branch in prompt (optional - comment out if not wanted)
# autoload -Uz vcs_info
# precmd() { vcs_info }
# zstyle ':vcs_info:git:*' formats '(%b)'
# setopt PROMPT_SUBST
# PROMPT='%n@%m %1~ ${vcs_info_msg_0_} %# '

# ===== End Development Environment Configuration =====
EOF

# Check if we've already added these configurations
if grep -q "Development Environment Configuration" ~/.zshrc; then
    echo "Development configurations already exist in .zshrc"
    echo "Skipping to avoid duplicates..."
else
    echo "" >> ~/.zshrc
    cat /tmp/zshrc_additions >> ~/.zshrc
    echo "Configurations added successfully!"
fi

# Clean up
rm /tmp/zshrc_additions

echo ""
echo "Done! Changes made to ~/.zshrc"
echo ""
echo "To apply the changes, run one of these commands:"
echo "  source ~/.zshrc"
echo "  OR"
echo "  exec zsh"
echo ""
echo "After sourcing, test with:"
echo "  which pip3"
echo "  which python3"
echo "  pip3 --version"
echo "  code --version"
