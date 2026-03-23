#!/bin/bash

# Install and configure Gemini CLI
# Created: 2025-11-30

echo "=== Installing Gemini CLI ==="
echo ""

# Check if Node.js is available (required for gemini-cli)
if command -v node &> /dev/null; then
    echo "✓ Node.js is installed (required for gemini-cli)"
    node --version
else
    echo "⚠️  Node.js not found but will be installed as dependency"
fi

echo ""
echo "Installing Google's gemini-cli via Homebrew..."

# Install gemini-cli (will install Node.js as dependency if needed)
brew install gemini-cli

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ gemini-cli installed successfully!"
    
    # Also install Python package for flexibility
    echo ""
    echo "Installing Python google-generativeai package for additional access..."
    pip3 install google-generativeai
    
    echo ""
    echo "=== Configuration Required ==="
    echo ""
    echo "1. Get your API key from: https://makersuite.google.com/app/apikey"
    echo "   Or from: https://aistudio.google.com/app/apikey"
    echo ""
    echo "2. Set environment variable by adding to ~/.zshrc:"
    echo "   export GEMINI_API_KEY='your-api-key-here'"
    echo ""
    echo "3. Reload your shell:"
    echo "   source ~/.zshrc"
    echo ""
    echo "Usage examples:"
    echo "  gemini prompt 'Your question here'"
    echo "  gemini chat  # Interactive chat"
else
    echo "⚠️  Installation failed"
fi

echo ""
echo "Done!"
