#!/usr/bin/env bash
# NCBI E-utilities over HTTPS via curl (no EDirect esearch/efetch; avoids FTP version checks).
# Optional: NCBI_API_KEY, NCBI_EMAIL, NCBI_TOOL (defaults to pubmed-edirect-skill).
# Intentionally no `set -e` here — this file may be sourced.

EUTILS_ESEARCH="${EUTILS_ESEARCH:-https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi}"
EUTILS_EFETCH="${EUTILS_EFETCH:-https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi}"

_ncbi_tool="${NCBI_TOOL:-pubmed-edirect-skill}"

# curl: fail on HTTP errors, timeouts; no Python (SSL) dependency.
_ncbi_curl() {
  curl -fsS --connect-timeout 30 --max-time 300 "$@"
}

# Extract first XML tag body (single line or greedy across one line — NCBI eSearch is one line often).
eutils_xml_first_tag() {
  local tag="$1"
  sed -n "s:.*<${tag}>\([^<]*\)</${tag}>.*:\1:p" | head -1
}

# PubMed esearch; writes XML to stdout. retmax 0 + usehistory y for efetch history.
pubmed_esearch_curl() {
  local term="$1"
  local retmax="${2:-0}"
  local usehistory="${3:-y}"
  local -a args=(
    -G "$EUTILS_ESEARCH"
    --data-urlencode "db=pubmed"
    --data-urlencode "term=${term}"
    --data-urlencode "retmax=${retmax}"
    --data-urlencode "retmode=xml"
    --data-urlencode "usehistory=${usehistory}"
    --data-urlencode "tool=${_ncbi_tool}"
  )
  if [[ -n "${NCBI_EMAIL:-}" ]]; then
    args+=(--data-urlencode "email=${NCBI_EMAIL}")
  fi
  if [[ -n "${NCBI_API_KEY:-}" ]]; then
    args+=(--data-urlencode "api_key=${NCBI_API_KEY}")
  fi
  _ncbi_curl "${args[@]}"
}

pubmed_efetch_medline_history_curl() {
  local webenv="$1"
  local query_key="$2"
  local retstart="${3:-0}"
  local retmax="$4"
  local -a args=(
    -G "$EUTILS_EFETCH"
    --data-urlencode "db=pubmed"
    --data-urlencode "query_key=${query_key}"
    --data-urlencode "WebEnv=${webenv}"
    --data-urlencode "retstart=${retstart}"
    --data-urlencode "retmax=${retmax}"
    --data-urlencode "rettype=medline"
    --data-urlencode "retmode=text"
    --data-urlencode "tool=${_ncbi_tool}"
  )
  if [[ -n "${NCBI_EMAIL:-}" ]]; then
    args+=(--data-urlencode "email=${NCBI_EMAIL}")
  fi
  if [[ -n "${NCBI_API_KEY:-}" ]]; then
    args+=(--data-urlencode "api_key=${NCBI_API_KEY}")
  fi
  _ncbi_curl "${args[@]}"
}

pubmed_efetch_abstract_id_curl() {
  local pmid="$1"
  local -a args=(
    -G "$EUTILS_EFETCH"
    --data-urlencode "db=pubmed"
    --data-urlencode "id=${pmid}"
    --data-urlencode "rettype=abstract"
    --data-urlencode "retmode=text"
    --data-urlencode "tool=${_ncbi_tool}"
  )
  if [[ -n "${NCBI_EMAIL:-}" ]]; then
    args+=(--data-urlencode "email=${NCBI_EMAIL}")
  fi
  if [[ -n "${NCBI_API_KEY:-}" ]]; then
    args+=(--data-urlencode "api_key=${NCBI_API_KEY}")
  fi
  _ncbi_curl "${args[@]}"
}
