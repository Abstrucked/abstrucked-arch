#!/bin/bash
# Install Node.js version manager (n or nvm)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script variables
INSTALL_CHOICE=""

print_header() {
    echo -e "${BLUE}📦 Node.js Version Manager Installer${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${CYAN}Choose between n (simpler) or nvm (more features)${NC}"
    echo ""
}

print_info() {
    echo -e "${YELLOW}Available options:${NC}"
    echo -e "${GREEN}n${NC}     - Simple, fast Node.js version manager"
    echo -e "${GREEN}      - Pros: Lightweight, fast switching, simple commands${NC}"
    echo -e "${GREEN}      - Cons: Bash-only, no .nvmrc auto-switching${NC}"
    echo ""
    echo -e "${GREEN}nvm${NC}   - Advanced Node.js version manager"
    echo -e "${GREEN}      - Pros: Supports .nvmrc, works with any shell, more features${NC}"
    echo -e "${GREEN}      - Cons: Slower, more complex, requires bash initialization${NC}"
    echo ""
}

get_user_choice() {
    while true; do
        echo -e "${PURPLE}Which Node.js version manager would you like to install?${NC}"
        echo -n "[n/nvm/skip]? "

        local response
        read -r response

        case "${response,,}" in
            "n")
                INSTALL_CHOICE="n"
                break
                ;;
            "nvm")
                INSTALL_CHOICE="nvm"
                break
                ;;
            "skip" | "s")
                echo -e "${YELLOW}Skipping Node.js version manager installation.${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid choice. Please enter 'n', 'nvm', or 'skip'.${NC}"
                ;;
        esac
    done
}

install_n() {
    echo -e "${YELLOW}Installing n (Node.js version manager)...${NC}"

    # Check if n is already installed
    if command -v n &> /dev/null; then
        echo -e "${GREEN}n is already installed!${NC}"
        return 0
    fi

    # Install n using the official installer
    curl -L https://git.io/n-install | bash

    # Source the updated profile to get n in PATH
    if [[ -f "$HOME/.bashrc" ]]; then
        source "$HOME/.bashrc"
    fi
    if [[ -f "$HOME/.zshrc" ]]; then
        source "$HOME/.zshrc"
    fi

    # Verify installation
    if command -v n &> /dev/null; then
        echo -e "${GREEN}✓ n installed successfully!${NC}"
        echo -e "${CYAN}Usage examples:${NC}"
        echo -e "${CYAN}  n latest          # Install latest Node.js${NC}"
        echo -e "${CYAN}  n lts             # Install LTS version${NC}"
        echo -e "${CYAN}  n 18              # Install Node.js 18${NC}"
        echo -e "${CYAN}  n                 # List installed versions${NC}"
    else
        echo -e "${RED}✗ Failed to install n${NC}"
        return 1
    fi
}

install_nvm() {
    echo -e "${YELLOW}Installing nvm (Node Version Manager)...${NC}"

    # Check if nvm is already installed
    if command -v nvm &> /dev/null; then
        echo -e "${GREEN}nvm is already installed!${NC}"
        return 0
    fi

    # Install nvm using the official installer
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

    # Source the updated profile to get nvm in PATH
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

    # Add nvm to shell profiles if not already there
    local shell_profiles=("$HOME/.bashrc" "$HOME/.zshrc")

    for profile in "${shell_profiles[@]}"; do
        if [[ -f "$profile" ]]; then
            if ! grep -q "NVM_DIR" "$profile"; then
                echo "" >> "$profile"
                echo "# NVM (Node Version Manager)" >> "$profile"
                echo 'export NVM_DIR="$HOME/.nvm"' >> "$profile"
                echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> "$profile"
                echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> "$profile"
            fi
        fi
    done

    # Verify installation
    if command -v nvm &> /dev/null; then
        echo -e "${GREEN}✓ nvm installed successfully!${NC}"
        echo -e "${CYAN}Usage examples:${NC}"
        echo -e "${CYAN}  nvm install node     # Install latest Node.js${NC}"
        echo -e "${CYAN}  nvm install --lts    # Install LTS version${NC}"
        echo -e "${CYAN}  nvm install 18       # Install Node.js 18${NC}"
        echo -e "${CYAN}  nvm list             # List installed versions${NC}"
        echo -e "${CYAN}  nvm use 18           # Switch to Node.js 18${NC}"
        echo ""
        echo -e "${YELLOW}Note: Restart your terminal or run 'source ~/.bashrc' to use nvm${NC}"
    else
        echo -e "${RED}✗ Failed to install nvm${NC}"
        return 1
    fi
}

main() {
    print_header
    print_info
    get_user_choice

    case "$INSTALL_CHOICE" in
        "n")
            install_n
            ;;
        "nvm")
            install_nvm
            ;;
    esac

    echo ""
    echo -e "${GREEN}🎉 Node.js version manager installation complete!${NC}"
    echo -e "${CYAN}You can now install Node.js versions using your chosen manager.${NC}"
}

# Run main function
main "$@"