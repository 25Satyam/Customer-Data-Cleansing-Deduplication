# SOP: Customer Master Data Cleansing & Deduplication

**Purpose:** Keep customer master data accurate, consistent and free of duplicates.
**Scope:** All new and existing customer records before they are loaded to or updated in the master data system.

## 1. Inputs
Raw customer extract (`customer_id, customer_name, contact_person, email, phone, address, city, state, pincode, gstin, created_date`).

## 2. Procedure

1. **Backup** the raw file. Never edit raw data in place.
2. **Standardise** formats:
   - Name: proper case, single spaces, company suffix as `Pvt Ltd`
   - Email: lowercase, no spaces
   - Phone: 10 digits, remove `+91`, leading `0`, spaces and dashes
   - State: full official name; City: proper case
   - Address: expand abbreviations (`Rd` → `Road`, `Sec` → `Sector`)
3. **Validate** each record:

   | Field | Rule | Severity |
   |---|---|---|
   | Customer name | Not blank | Critical |
   | State | Not blank | Critical |
   | Email | Valid format | Critical |
   | Phone | 10 digits starting 6-9 | Critical |
   | Pincode | 6 digits, first digit 1-9 | Critical |
   | GSTIN | 15-char valid format (if provided) | Critical |
   | GSTIN state code | Matches state | Warning |
   | GSTIN | Present | Warning |

4. **Reject and log** critical failures to `rejected_records.csv` with the reason and return them to the requester/data owner for correction. Do not load them.
5. **Identify duplicates** using the matching rules in the README (phone, email, GSTIN, pincode + name/address similarity).
6. **Review** the duplicate report. For low-score matches (< 0.90), confirm manually before merging.
7. **Merge:** keep the most complete record; if equal, keep the most recent. Retain the merged IDs in the duplicate report as an audit trail.
8. **Publish** `customers_clean.csv` and the quality summary.

## 3. Quality metrics (track each run)
Records loaded, rejected %, duplicates removed, final records, warnings count.

## 4. Roles
| Role | Responsibility |
|---|---|
| Data analyst | Runs the process, reviews the duplicate report |
| Data owner / requester | Corrects rejected records within the agreed turnaround time |
| Approver | Signs off on merges of low-confidence matches |

## 5. Turnaround
Rejected records are returned to the requester the same day; corrected records are re-processed within the next run.
