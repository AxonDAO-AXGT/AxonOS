#!/bin/bash
# Script to apply WhiteSur theme manually (for testing)

export DISPLAY=:1

echo "=== Applying WhiteSur Theme ==="
echo "Available themes:"
ls -1 /usr/share/themes/ | grep -i white || echo "No WhiteSur themes found!"

echo ""
echo "Current GTK theme:"
xfconf-query -c xsettings -p /Net/ThemeName 2>/dev/null || echo "Could not read current theme"

echo ""
echo "Current WM theme:"
xfconf-query -c xfwm4 -p /general/theme 2>/dev/null || echo "Could not read current WM theme"

echo ""
echo "Attempting to apply WhiteSur theme..."

# Find WhiteSur theme
for theme in "WhiteSur-Dark" "WhiteSur-dark" "WhiteSur-Dark-normal" "WhiteSur-Dark-solid" "WhiteSur"; do
    if [ -d "/usr/share/themes/$theme" ]; then
        echo "Found theme: $theme"
        xfconf-query -c xsettings -p /Net/ThemeName -s "$theme"
        xfconf-query -c xfwm4 -p /general/theme -s "$theme"
        echo "Theme applied: $theme"
        exit 0
    fi
done

echo "ERROR: WhiteSur theme not found in /usr/share/themes/"
exit 1
