#!/bin/bash
# Build plugin ZIPs for production upload.
#
# Each plugin in plugins-v2/ is already self-contained (has its own
# vendor/pi-shared/). Build just zips the folder after stripping dev-only files.
#
# Usage:
#   bash scripts/build_plugins.sh              # build all 7
#   bash scripts/build_plugins.sh pi-seo-v2    # build 1 plugin

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WP_CONTENT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$WP_CONTENT/plugins"          # WP-activated plugins = source of truth
BUILD_DIR="$WP_CONTENT/dist/plugins"

mkdir -p "$BUILD_DIR"

PLUGINS_TO_BUILD=("$@")
if [ ${#PLUGINS_TO_BUILD[@]} -eq 0 ]; then
    cd "$SRC_DIR"
    # Only pi-*-v2 plugins (v2 self-contained). Skip old v1 plugins.
    PLUGINS_TO_BUILD=(pi-*-v2)
fi

echo "──────────────────────────────────────────"
echo "Build target: $BUILD_DIR"
echo "Source:       $SRC_DIR"
echo "Plugins:      ${PLUGINS_TO_BUILD[*]}"
echo "──────────────────────────────────────────"
echo ""

for slug in "${PLUGINS_TO_BUILD[@]}"; do
    src="$SRC_DIR/$slug"
    if [ ! -d "$src" ]; then
        echo "  ⚠️  skip $slug — not found"
        continue
    fi

    main_php="$src/$slug.php"
    version=""
    if [ -f "$main_php" ]; then
        version=$(grep -oE "Version:\s*[0-9]+\.[0-9]+\.[0-9]+" "$main_php" | head -1 | awk '{print $2}')
    fi
    [ -z "$version" ] && version="0.0.0"

    # Sanity check — each plugin must have vendor/pi-shared/ bundled
    if [ ! -f "$src/vendor/pi-shared/bootstrap.php" ]; then
        echo "  ✗ $slug — missing vendor/pi-shared/bootstrap.php. Build skipped."
        continue
    fi

    stage="$BUILD_DIR/.stage/$slug"
    rm -rf "$stage"
    mkdir -p "$stage"

    # Copy the whole plugin (already self-contained)
    cp -r "$src/." "$stage/"

    # Strip dev-only files
    find "$stage" -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
    find "$stage" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$stage" -type d -name ".git" -exec rm -rf {} + 2>/dev/null || true
    find "$stage" -name "*.bak" -delete 2>/dev/null || true
    find "$stage" -name ".DS_Store" -delete 2>/dev/null || true

    zip_name="$slug-$version.zip"
    zip_path="$BUILD_DIR/$zip_name"
    rm -f "$zip_path"

    cd "$BUILD_DIR/.stage"
    zip -r -q "$zip_path" "$slug"
    cd - > /dev/null

    size=$(du -h "$zip_path" | cut -f1)
    files=$(unzip -l "$zip_path" | tail -1 | awk '{print $2}')
    echo "  ✓ $zip_name   ($size, $files files)"

    rm -rf "$stage"
done

rm -rf "$BUILD_DIR/.stage"

echo ""
echo "✓ Done. ZIPs at: $BUILD_DIR"
