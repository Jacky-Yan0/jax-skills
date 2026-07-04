#!/bin/bash
# publication_trends.sh
# Analyze publication trends over time (esearch over HTTPS via curl).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_eutils_curl.sh
source "${SCRIPT_DIR}/lib_eutils_curl.sh"

QUERY="$1"
START_YEAR="${2:-2000}"
END_YEAR="${3:-$(date +%Y)}"
OUTPUT_FILE="${4:-trends.csv}"

if [ -z "$QUERY" ]; then
    echo "Error: Search query required"
    echo "Usage: $0 \"search query\" [start_year] [end_year] [output_file]"
    echo "Example: $0 \"machine learning\" 2010 2023 ml_trends.csv"
    exit 1
fi

echo "Analyzing publication trends for: $QUERY"
echo "Years: $START_YEAR to $END_YEAR"
echo "Output: $OUTPUT_FILE"

echo "year,count,cumulative" > "$OUTPUT_FILE"

total_cumulative=0
years_processed=0

for year in $(seq "$START_YEAR" "$END_YEAR"); do
    echo -n "Processing $year... "

    term="(${QUERY}) AND ${year}:${year}[PDAT]"
    xml=$(pubmed_esearch_curl "$term" 0 n)
    count=$(printf '%s' "$xml" | eutils_xml_first_tag Count)

    if [ -z "$count" ] || ! [[ "$count" =~ ^[0-9]+$ ]]; then
        count=0
    fi

    total_cumulative=$((total_cumulative + count))
    years_processed=$((years_processed + 1))

    echo "$year,$count,$total_cumulative" >> "$OUTPUT_FILE"

    echo "$count publications"

    if [ "$year" -lt "$END_YEAR" ]; then
        sleep 1
    fi
done

echo ""
echo "=== Analysis Complete ==="
echo "Years analyzed: $years_processed"
echo "Total publications: $total_cumulative"
echo "Output file: $OUTPUT_FILE"

if command -v gnuplot >/dev/null 2>&1; then
    echo ""
    echo "Generating plot..."

    gnuplot << EOF
    set terminal dumb size 80,30
    set title "Publication Trend: $QUERY"
    set xlabel "Year"
    set ylabel "Publications"
    set xrange [$START_YEAR:$END_YEAR]
    set xtics 5
    set key off
    plot "$OUTPUT_FILE" using 1:2 with linespoints
EOF
else
    echo ""
    echo "=== Data Summary ==="
    echo "Year Range: $START_YEAR - $END_YEAR"
    echo "Peak year(s):"
    tail -n +2 "$OUTPUT_FILE" | sort -t, -k2,2nr | head -3 | \
        while IFS=, read -r y c cum; do
            echo "  $y: $c publications"
        done

    echo ""
    echo "Recent trend (last rows in file):"
    tail -n +2 "$OUTPUT_FILE" | tail -5 | \
        while IFS=, read -r y c cum; do
            echo "  $y: $c publications"
        done
fi

if [ "$years_processed" -ge 2 ]; then
    first_year_count=$(awk -F, -v y="$START_YEAR" '$1==y {print $2}' "$OUTPUT_FILE")
    last_year_count=$(awk -F, -v y="$END_YEAR" '$1==y {print $2}' "$OUTPUT_FILE")

    if [ -n "$first_year_count" ] && [ "$first_year_count" -gt 0 ] 2>/dev/null; then
        growth_rate=$(echo "scale=2; ($last_year_count - $first_year_count) / $first_year_count * 100" | bc 2>/dev/null || echo "N/A")
        echo ""
        echo "Growth from $START_YEAR to $END_YEAR: ${growth_rate}%"
    fi
fi

echo ""
echo "=== Text Visualization ==="
max_count=$(tail -n +2 "$OUTPUT_FILE" | cut -d, -f2 | sort -nr | head -1)
scale=$((max_count / 50 + 1))
if [ "$scale" -lt 1 ]; then scale=1; fi

tail -n +2 "$OUTPUT_FILE" | \
    while IFS=, read -r y c cum; do
        bars=$((c / scale))
        printf "%4s: %5d |" "$y" "$c"
        for ((i=0; i<bars; i++)); do
            printf "█"
        done
        printf "\n"
    done | tail -20
