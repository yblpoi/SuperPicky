#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MODE_ARGS=""

show_help() {
    echo "SuperPicky macOS compatibility wrapper"
    echo ""
    echo "Usage:"
    echo "  ./build_release.sh --test [extra build_release_mac.py args]"
    echo "  ./build_release.sh --release [extra build_release_mac.py args]"
    echo ""
    echo "This wrapper forwards to build_release_mac.py --build-type full."
    echo "Use --release to append --notarize."
}

if [ "$#" -gt 0 ]; then
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --release)
            MODE_ARGS="--notarize"
            shift
            ;;
        --test)
            shift
            ;;
    esac
fi

exec python3 "$SCRIPT_DIR/build_release_mac.py" --build-type full $MODE_ARGS "$@"