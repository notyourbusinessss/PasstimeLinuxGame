#!/bin/sh
# Installs Space Miner for the current user (no root needed):
#   ~/.local/bin/space-miner, an entry in the applications menu and an icon.
# Remove it again with:  ./install.sh --uninstall
set -e
here=$(cd "$(dirname "$0")" && pwd)
prefix="${PREFIX:-$HOME/.local}"
icon="$prefix/share/icons/hicolor/512x512/apps/space-miner.png"
desktop="$prefix/share/applications/space-miner.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$prefix/bin/space-miner" "$icon" "$desktop"
    echo "Space Miner removed. Your save (~/.space_miner_save.json) was kept."
    exit 0
fi

install -Dm755 "$here/space-miner" "$prefix/bin/space-miner"
install -Dm644 "$here/space-miner.png" "$icon"
mkdir -p "$(dirname "$desktop")"
sed -e "s|^Exec=.*|Exec=$prefix/bin/space-miner|" -e "s|^Icon=.*|Icon=$icon|" "$here/space-miner.desktop" > "$desktop"
chmod 644 "$desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$prefix/share/applications" 2>/dev/null || true
echo "Installed to $prefix. Start it from your applications menu, or run: $prefix/bin/space-miner"
case ":$PATH:" in *":$prefix/bin:"*) ;; *) echo "(Add $prefix/bin to your PATH to start it from a terminal.)" ;; esac
