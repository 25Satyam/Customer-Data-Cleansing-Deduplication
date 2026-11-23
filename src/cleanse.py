"""Customer master data cleansing & deduplication pipeline.

Steps
  1. Load raw customer records
  2. Standardise fields (names, email, phone, state, city, pincode, GSTIN)
  3. Validate against business rules -> route failures to a rejected file
  4. Detect duplicates (exact keys + fuzzy name match) and pick a survivor
  5. Write clean data, duplicate report, rejected records and a quality summary

Usage:  python src/cleanse.py
"""
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "customers_raw.csv"
OUT = ROOT / "data" / "processed"

# ---------------------------------------------------------------- reference data
STATE_MAP = {
    "up": "Uttar Pradesh", "uttar pradesh": "Uttar Pradesh",
    "hr": "Haryana", "haryana": "Haryana",
    "dl": "Delhi", "delhi": "Delhi", "nct of delhi": "Delhi", "new delhi": "Delhi",
    "mh": "Maharashtra", "maharashtra": "Maharashtra",
    "ka": "Karnataka", "karnataka": "Karnataka",
    "tn": "Tamil Nadu", "tamil nadu": "Tamil Nadu",
    "wb": "West Bengal", "west bengal": "West Bengal",
    "rj": "Rajasthan", "rajasthan": "Rajasthan",
}
STATE_GST_CODE = {"Uttar Pradesh": "09", "Haryana": "06", "Delhi": "07", "Maharashtra": "27",
                  "Karnataka": "29", "Tamil Nadu": "33", "West Bengal": "19", "Rajasthan": "08"}

EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
PIN_RE = re.compile(r"^[1-9]\d{5}$")
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

FIELDS = ["customer_name", "contact_person", "email", "phone", "address", "city", "state", "pincode", "gstin"]


# ---------------------------------------------------------------- standardisation
def clean_text(x):
    return re.sub(r"\s+", " ", str(x)).strip()


def std_name(x):
    x = clean_text(x).title()
    x = re.sub(r"\bPrivate Limited\b|\bPvt\.? Ltd\.?\b|\bPvt Lt\b", "Pvt Ltd", x, flags=re.I)
    x = re.sub(r"\bAnd\b", "&", x)
    return x


def std_phone(x):
    digits = re.sub(r"\D", "", str(x))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def std_state(x):
    return STATE_MAP.get(clean_text(x).lower(), clean_text(x).title())


def std_address(x):
    x = clean_text(x)
    x = re.sub(r"\bRd\b\.?", "Road", x, flags=re.I)
    x = re.sub(r"\bSec\b\.?", "Sector", x, flags=re.I)
    return x


def standardise(df):
    out = df.copy()
    for c in FIELDS + ["customer_id", "created_date"]:
        out[c] = out[c].map(clean_text)
    out["customer_name"] = out["customer_name"].map(std_name)
    out["contact_person"] = out["contact_person"].str.title()
    out["email"] = out["email"].str.lower()
    out["phone"] = out["phone"].map(std_phone)
    out["address"] = out["address"].map(std_address)
    out["city"] = out["city"].str.title()
    out["state"] = out["state"].map(std_state)
    out["gstin"] = out["gstin"].str.upper()
    return out


# ---------------------------------------------------------------- validation
def validate_row(r):
    """Return (critical_issues, warnings) for one standardised record."""
    crit, warn = [], []
    if not r["customer_name"]:
        crit.append("missing customer name")
    if not r["state"]:
        crit.append("missing state")
    if not EMAIL_RE.match(r["email"]):
        crit.append("invalid email")
    if not re.fullmatch(r"[6-9]\d{9}", r["phone"]):
        crit.append("invalid phone")
    if not PIN_RE.match(r["pincode"]):
        crit.append("invalid pincode")
    if r["gstin"]:
        if not GSTIN_RE.match(r["gstin"]):
            crit.append("invalid GSTIN format")
        elif r["state"] in STATE_GST_CODE and r["gstin"][:2] != STATE_GST_CODE[r["state"]]:
            warn.append("GSTIN state code does not match state")
    else:
        warn.append("GSTIN missing")
    return crit, warn


# ---------------------------------------------------------------- deduplication
def name_key(x):
    x = re.sub(r"[^a-z0-9 ]", "", x.lower())
    return re.sub(r"\b(pvt|ltd|private|limited)\b", "", x).strip()


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def find_duplicates(df):
    """Group records that refer to the same customer. Returns df with group_id, match_reason, match_score."""
    df = df.reset_index(drop=True)
    keys = df["customer_name"].map(name_key).tolist()
    uf = UnionFind(len(df))
    reasons = {}

    def link(i, j, reason, score):
        uf.union(i, j)
        for k in (i, j):
            reasons.setdefault(k, (reason, score))

    # blocking: only compare records sharing phone, email, GSTIN or pincode
    for col, rule in [("phone", "same phone + similar name"), ("email", "same email + similar name"),
                      ("gstin", "same GSTIN"), ("pincode", "same pincode + very similar name & address")]:
        for _, idx in df[df[col] != ""].groupby(col).groups.items():
            idx = list(idx)
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    i, j = idx[a], idx[b]
                    s = sim(keys[i], keys[j])
                    if col == "gstin":
                        link(i, j, rule, round(s, 2))
                    elif col in ("phone", "email") and s >= 0.80:
                        link(i, j, rule, round(s, 2))
                    elif col == "pincode" and s >= 0.92 and sim(df.at[i, "address"], df.at[j, "address"]) >= 0.85:
                        link(i, j, rule, round(s, 2))

    df["group_id"] = [uf.find(i) for i in range(len(df))]
    df["match_reason"] = [reasons.get(i, ("", ""))[0] for i in range(len(df))]
    df["match_score"] = [reasons.get(i, ("", ""))[1] for i in range(len(df))]
    return df


def completeness(r):
    return sum(1 for f in FIELDS if r[f])


def pick_survivors(df):
    df = df.copy()
    df["_completeness"] = df.apply(completeness, axis=1)
    df = df.sort_values(["group_id", "_completeness", "created_date"], ascending=[True, False, False])
    df["role"] = df.groupby("group_id").cumcount().map(lambda n: "survivor" if n == 0 else "duplicate")
    return df.drop(columns="_completeness")


# ---------------------------------------------------------------- main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n_raw = len(raw)

    std = standardise(raw)

    results = std.apply(validate_row, axis=1)
    std["critical_issues"] = results.map(lambda t: "; ".join(t[0]))
    std["warnings"] = results.map(lambda t: "; ".join(t[1]))

    rejected = std[std["critical_issues"] != ""].copy()
    valid = std[std["critical_issues"] == ""].copy()

    grouped = pick_survivors(find_duplicates(valid))
    dup_groups = grouped[grouped.duplicated("group_id", keep=False)].copy()
    dup_groups["group_id"] = dup_groups["group_id"].rank(method="dense").astype(int)
    survivors = grouped[grouped["role"] == "survivor"]

    clean_cols = ["customer_id"] + FIELDS + ["created_date"]
    survivors[clean_cols].sort_values("customer_id").to_csv(OUT / "customers_clean.csv", index=False)
    dup_groups[["group_id", "role", "customer_id", "customer_name", "email", "phone", "city", "pincode",
                "created_date", "match_reason", "match_score"]].sort_values(["group_id", "role"], ascending=[True, False]) \
        .to_csv(OUT / "duplicates_report.csv", index=False)
    rejected[["customer_id", "customer_name", "email", "phone", "pincode", "gstin", "critical_issues"]] \
        .to_csv(OUT / "rejected_records.csv", index=False)

    # Count issues fixed by standardisation (raw value != standardised value)
    changed = {f: int((raw[f].astype(str) != std[f]).sum()) for f in FIELDS}
    summary = pd.DataFrame([
        ("Raw records loaded", n_raw),
        ("Records rejected (failed validation)", len(rejected)),
        ("Records passing validation", len(valid)),
        ("Duplicate groups found", dup_groups["group_id"].nunique()),
        ("Duplicate records removed", int((grouped["role"] == "duplicate").sum())),
        ("Final clean customer records", len(survivors)),
        ("Records with GSTIN warnings", int((valid["warnings"] != "").sum())),
        ("Reduction in record count (%)", round((1 - len(survivors) / n_raw) * 100, 1)),
    ] + [(f"Values standardised: {f}", v) for f, v in changed.items()], columns=["metric", "value"])
    summary["value"] = pd.Series([int(v) if float(v).is_integer() else v for v in summary["value"]], dtype=object)
    summary.to_csv(OUT / "data_quality_summary.csv", index=False)

    print(summary.to_string(index=False))
    print("\nTop rejection reasons:")
    print(rejected["critical_issues"].str.split("; ").explode().value_counts().to_string())
    print(f"\nOutputs written to {OUT}")


if __name__ == "__main__":
    main()
