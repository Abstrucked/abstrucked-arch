#!/bin/bash
echo "Select power mode:"
echo "1) Battery (1.6GHz, 10W)"
echo "2) Balanced (2.1GHz, 15W)"
echo "3) Performance (2.5GHz, 20W)"
read -p "Choice [1-3]: " choice

case $choice in
    1) ~/.local/bin/batt-mode.sh ;;
    2) ~/.local/bin/balanced-mode.sh ;;
    3) ~/.local/bin/perf-mode.sh ;;
    *) echo "Invalid choice" ;;
esac
