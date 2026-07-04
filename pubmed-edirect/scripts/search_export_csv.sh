#!/bin/bash
# search_export_csv.sh
# Search PubMed and export results to CSV (NCBI E-utilities HTTPS via curl; no esearch/efetch).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_eutils_curl.sh
source "${SCRIPT_DIR}/lib_eutils_curl.sh"

QUERY="$1"
MAX_RESULTS="${2:-100}"
OUTPUT_FILE="${3:-search_results.csv}"

if [ -z "$QUERY" ]; then
    echo "Error: Search query required"
    echo "Usage: $0 \"search query\" [max_results] [output_file]"
    echo "Example: $0 \"CRISPR [TIAB]\" 50 crispr_results.csv"
    exit 1
fi

echo "Searching PubMed for: $QUERY"
echo "Max results: $MAX_RESULTS"
echo "Output file: $OUTPUT_FILE"

echo -n "Getting result count... "
esearch_xml=$(pubmed_esearch_curl "$QUERY" 0 y)
total=$(printf '%s' "$esearch_xml" | eutils_xml_first_tag Count)
echo "$total results found"

if [ -z "$total" ] || ! [[ "$total" =~ ^[0-9]+$ ]]; then
    echo "Error: could not parse esearch response (empty or non-numeric Count)."
    exit 1
fi

if [ "$total" -eq 0 ]; then
    echo "No results found for query: $QUERY"
    exit 0
fi

to_fetch=$(( total < MAX_RESULTS ? total : MAX_RESULTS ))
echo "Fetching $to_fetch results (HTTPS + curl)..."

echo "pmid,year,month,title,journal,first_author,has_abstract" > "$OUTPUT_FILE"

webenv=$(printf '%s' "$esearch_xml" | eutils_xml_first_tag WebEnv)
query_key=$(printf '%s' "$esearch_xml" | eutils_xml_first_tag QueryKey)

if [ -z "$webenv" ] || [ -z "$query_key" ]; then
    echo "Error: esearch did not return WebEnv/QueryKey (need usehistory)."
    exit 1
fi

pubmed_efetch_medline_history_curl "$webenv" "$query_key" 0 "$to_fetch" | \
    awk -f "${SCRIPT_DIR}/medline_batch_to_tsv.awk" | \
    awk '
    BEGIN {FS="\t"; OFS=","}
    {
        gsub(/"/, "\"\"", $4)
        gsub(/"/, "\"\"", $5)
        gsub(/"/, "\"\"", $6)
        print "\"" $1 "\",\"" $2 "\",\"" $3 "\",\"" $4 "\",\"" $5 "\",\"" $6 "\",\"" $7 "\""
    }' >> "$OUTPUT_FILE"

result_count=$(($(wc -l < "$OUTPUT_FILE") - 1))

echo ""
echo "=== Export Complete ==="
echo "Query: $QUERY"
echo "Total available: $total"
echo "Exported: $result_count"
echo "File: $OUTPUT_FILE"

if [ "$result_count" -gt 0 ]; then
    echo ""
    echo "=== Sample of exported data ==="
    head -5 "$OUTPUT_FILE" | column -t -s, | head -6
fi

if [ "$result_count" -gt 1 ]; then
    echo ""
    echo "=== Summary Statistics ==="
    echo "Year distribution:"
    tail -n +2 "$OUTPUT_FILE" | cut -d, -f2 | sed 's/"//g' | \
        sort | uniq -c | sort -rn | head -10 | \
        while read -r count year; do
            printf "  %-4s: %3d papers\n" "$year" "$count"
        done
    echo ""
    echo "Top journals:"
    tail -n +2 "$OUTPUT_FILE" | cut -d, -f5 | sed 's/"//g' | \
        sort | uniq -c | sort -rn | head -5 | \
        while read -r count journal; do
            printf "  %-40s: %3d papers\n" "$journal" "$count"
        done
fi
