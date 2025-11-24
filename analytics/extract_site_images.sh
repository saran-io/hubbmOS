#!/bin/bash
# One-time workflow: crawl site → extract images → update analytics UI

set -e

SITE_URL="${1:-https://automation.broadcom.com/}"
MIRROR_DIR="site_mirror"
CSV_OUT="analytics/ui/public/image-report.csv"

echo "Step 1: Crawling ${SITE_URL} (one-time, respectful crawl)..."
python3 scripts/crawl_site.py "${SITE_URL}" --output "${MIRROR_DIR}" --max-pages 50 --delay 1.5

echo ""
echo "Step 2: Extracting images from mirrored pages..."
python3 scripts/extract_images.py "${MIRROR_DIR}" --csv-out "${CSV_OUT}" --verbose

echo ""
echo "✅ Complete! Images extracted to ${CSV_OUT}"
echo "   Run 'cd analytics/ui && npm run dev' to view in dashboard"

