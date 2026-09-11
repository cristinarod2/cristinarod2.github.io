#!/usr/bin/env python3
"""
update_publications.py — refresh the Publications list in index.html from ORCID.

Usage (from the folder that contains index.html):
    python3 update_publications.py            # fetch ORCID, rewrite the list, print what changed
    python3 update_publications.py --dry-run  # only show what would change
    python3 update_publications.py --file works.json   # use a saved ORCID JSON instead of fetching

What it does
  1. Downloads your public works from https://pub.orcid.org/v3.0/<ORCID>/works
  2. Keeps one entry per DOI (ORCID sometimes lists the same paper twice), skips entries without a DOI
  3. Cleans up journal names and assigns a theme (thera / spect / nano / alz / comp) by keyword —
     edit THEME_OVERRIDES below to pin a paper to a theme, or JOURNAL_FIX to rename a journal
  4. Replaces everything between <!-- PUBS:START --> and <!-- PUBS:END --> in index.html.
     Counts, year span and filters on the page update themselves from that list.

No extra packages needed — standard library only.
"""
import json, re, sys, urllib.request, html
from pathlib import Path

ORCID = "0000-0002-3313-4422"
INDEX = Path(__file__).with_name("index.html")

# --- manual corrections ------------------------------------------------------
JOURNAL_FIX = {  # ORCID journal string (or empty) → what to show; matched by DOI prefix when journal is blank
    "European journal of pharmaceutics and biopharmaceutics : official journal of Arbeitsgemeinschaft fur Pharmazeutische Verfahrenstechnik e.V": "European Journal of Pharmaceutics and Biopharmaceutics",
    "Journal of controlled release : official journal of the Controlled Release Society": "Journal of Controlled Release",
    "International journal of pharmaceutics": "International Journal of Pharmaceutics",
    "Chembiochem : a European journal of chemical biology": "ChemBioChem",
    "Chemistry (Weinheim an der Bergstrasse, Germany)": "Chemistry – A European Journal",
    "Arthritis research & therapy": "Arthritis Research & Therapy",
    "Physics in medicine and biology": "Physics in Medicine & Biology",
    "PLOS ONE": "PLOS ONE",
}
DOI_JOURNAL = {  # for ORCID entries that have no journal name
    "10.1016/j.bmcl": "Bioorganic & Medicinal Chemistry Letters",
    "10.1039/c4mt": "Metallomics", "10.1039/c3mt": "Metallomics",
    "10.1016/j.jinorgbio": "Journal of Inorganic Biochemistry",
    "10.1063/1.4897": "AIP Conference Proceedings",
    "10.1039/c3mb": "Molecular BioSystems",
    "10.1007/s10822": "Journal of Computer-Aided Molecular Design",
}
THEME_OVERRIDES = {  # DOI (lowercase) → theme key
    "10.1021/acs.inorgchem.9b02350": "thera", "10.1039/c7dt02196h": "thera", "10.1088/1361-6560/aa7926": "spect",
    "10.1063/5.0044515": "nano", "10.1063/1.5018165": "nano", "10.1039/c4mt00167b": "alz",
    "10.1016/j.bmcl.2016.01.080": "alz", "10.1021/ed084p1190": "alz",
}

def theme(title):
    t = title.lower()
    if re.search(r"alzheimer|amyloid|thioflavin|acetylcholinesterase|hydroxy-4-pyridinone|hydroxypyridinone|neurodegenerative|deferiprone|8-hydroxyquinoline", t):
        return "comp" if re.search(r"in silico|ab initio|computational|quantum chemical|simulations", t) else "alz"
    if re.search(r"chelat|macrocycl|theranostic|ligand|bioconjugate|radionuclide therapy|alpha therapy|immunoconjugate|thiourea|neunpa|picoopa|tpan|octox|chxhox|thpn", t):
        return "thera"
    if re.search(r"quantitative spect|spect imaging of|dual spect|multi-isotope|simultaneous spect|activity quantification|image performance|thyroid-probe|dose calibrator|pet scanner|feasibility|decay chain|actinium-226|209at|dosimetry|infrared thermal|pretargeted", t):
        return "spect"
    return "nano"

def clean_title(t):
    t = re.sub(r"</?sup>", "", t)
    t = html.unescape(t).replace("─", " — ").replace("—", " — ")
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    t = re.sub(r"\s+—\s+", " — ", t)
    return t

def fetch(path=None):
    if path:
        return json.load(open(path, encoding="utf-8"))
    req = urllib.request.Request(f"https://pub.orcid.org/v3.0/{ORCID}/works", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def parse(data):
    seen, pubs = set(), []
    for g in data["group"]:
        s = g["work-summary"][0]
        dois = [e["external-id-value"] for e in s["external-ids"]["external-id"] if e["external-id-type"] == "doi"]
        if not dois:
            continue
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", dois[0].strip(), flags=re.I)
        key = doi.lower()
        if key in seen:
            continue
        seen.add(key)
        year = int(((s.get("publication-date") or {}).get("year") or {}).get("value") or 0)
        title = clean_title(s["title"]["title"]["value"])
        journal = ((s.get("journal-title") or {}).get("value") or "").strip()
        journal = JOURNAL_FIX.get(journal, journal)
        if not journal:
            journal = next((v for k, v in DOI_JOURNAL.items() if key.startswith(k)), "")
        pubs.append({"y": year, "t": title, "j": journal, "d": doi, "th": THEME_OVERRIDES.get(key, theme(title))})
    pubs.sort(key=lambda p: (-p["y"], p["t"]))
    return pubs

def main():
    dry = "--dry-run" in sys.argv
    path = sys.argv[sys.argv.index("--file") + 1] if "--file" in sys.argv else None
    pubs = parse(fetch(path))
    src = INDEX.read_text(encoding="utf-8")
    m = re.search(r"(<!-- PUBS:START -->\n)(.*?)(\n<!-- PUBS:END -->)", src, re.S)
    if not m:
        sys.exit("PUBS:START / PUBS:END markers not found in index.html")
    old = json.loads(m.group(2))
    old_d = {p["d"].lower() for p in old}
    new_d = {p["d"].lower() for p in pubs}
    added = [p for p in pubs if p["d"].lower() not in old_d]
    removed = [p for p in old if p["d"].lower() not in new_d]
    block = "[\n" + ",\n".join(json.dumps(p, ensure_ascii=False) for p in pubs) + "\n]"
    print(f"ORCID: {len(pubs)} unique papers with a DOI (page had {len(old)}).")
    for p in added:   print(f"  + {p['y']}  {p['t'][:80]}  [{p['th']}]")
    for p in removed: print(f"  - {p['y']}  {p['t'][:80]}")
    if dry:
        print("Dry run — index.html not changed."); return
    INDEX.write_text(src[:m.start(2)] + block + src[m.end(2):], encoding="utf-8")
    print("index.html updated." if (added or removed) else "index.html rewritten (no new or removed papers).")

if __name__ == "__main__":
    main()
