#!/bin/bash
# batch_fetch_abstracts.sh
# Fetch abstracts for a list of PMIDs (efetch over HTTPS via curl).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_eutils_curl.sh
source "${SCRIPT_DIR}/lib_eutils_curl.sh"

INPUT_FILE="${1:-pmids.txt}"
OUTPUT_DIR="${2:-abstracts}"
DELAY="${3:-0.5}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file '$INPUT_FILE' not found"
    echo "Usage: $0 [input_file] [output_dir] [delay_seconds]"
    echo "Default: pmids.txt abstracts 0.5"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

total=$(wc -l < "$INPUT_FILE")
echo "Processing $total PMIDs from $INPUT_FILE"
echo "Output directory: $OUTPUT_DIR"
echo "Delay between requests: ${DELAY}s"

count=0
success=0
fail=0

while read -r pmid; do
    [ -z "$pmid" ] && continue

    count=$((count + 1))
    output_file="${OUTPUT_DIR}/${pmid}.txt"

    echo -n "[$count/$total] PMID $pmid: "

    if pubmed_efetch_abstract_id_curl "$pmid" > "$output_file" 2>/dev/null; then
        if [ -s "$output_file" ] && ! grep -qi "error" "$output_file" 2>/dev/null; then
            echo "✓"
            success=$((success + 1))
        else
            echo "✗ (empty/error)"
            rm -f "$output_file"
            fail=$((fail + 1))
        fi
    else
        echo "✗ (fetch failed)"
        rm -f "$output_file"
        fail=$((fail + 1))
    fi

    if [ "$count" -lt "$total" ]; then
        sleep "$DELAY"
    fi

done < "$INPUT_FILE"

echo ""
echo "=== Summary ==="
echo "Total processed: $count"
echo "Successful: $success"
echo "Failed: $fail"
echo "Output in: $OUTPUT_DIR/"

if [ "$success" -gt 0 ]; then
    cat "$OUTPUT_DIR"/*.txt > "${OUTPUT_DIR}_combined.txt" 2>/dev/null || true
    echo "Combined file: ${OUTPUT_DIR}_combined.txt"
fi
