# Convert PubMed MEDLINE (efetch rettype=medline) to TSV:
# pmid, year, month, title, journal, first_author, has_abstract (YES/NO)
BEGIN {
  pmid = ""; year = ""; month = ""; title = ""; journal = ""; first = ""; has_ab = "NO"
  field = ""; fau_done = 0
}
function flush() {
  if (pmid == "") return
  gsub(/\t/, " ", title)
  gsub(/\t/, " ", journal)
  gsub(/\t/, " ", first)
  gsub(/  +/, " ", first)
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", first)
  print pmid "\t" year "\t" month "\t" title "\t" journal "\t" first "\t" has_ab
}
/^PMID-/ {
  flush()
  pmid = $2
  year = ""; month = ""; title = ""; journal = ""; first = ""; has_ab = "NO"
  field = ""; fau_done = 0
  next
}
/^      / {
  if (field == "TI") {
    t = $0
    sub(/^      /, "", t)
    title = title " " t
  }
  next
}
/^TI  - / {
  field = "TI"
  title = substr($0, 7)
  next
}
/^AB  - / {
  has_ab = "YES"
  field = "AB"
  next
}
/^JT  - / {
  field = ""
  journal = substr($0, 7)
  next
}
/^TA  - / {
  if (journal == "") journal = substr($0, 7)
  next
}
/^DP  - / {
  field = ""
  ds = substr($0, 7)
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", ds)
  n = split(ds, a, /[[:space:]]+/)
  if (n >= 1) year = a[1]
  if (n >= 2) month = a[2]
  next
}
/^FAU - / {
  if (!fau_done) {
    first = substr($0, 7)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", first)
    fau_done = 1
  }
  next
}
/^[A-Z]/ {
  if (field == "TI" || field == "AB") field = ""
  next
}
END {
  flush()
}
