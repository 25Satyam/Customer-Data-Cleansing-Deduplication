"""Generate a synthetic, deliberately messy customer master dataset.

All data is fictional. Run:  python src/generate_sample_data.py
Output: data/raw/customers_raw.csv
"""
import random
import string
from pathlib import Path

import pandas as pd

random.seed(42)

FIRST = ["Aarav", "Vivaan", "Aditya", "Rohan", "Karan", "Neha", "Priya", "Anjali", "Sneha", "Pooja",
         "Rahul", "Amit", "Sanjay", "Deepak", "Meera", "Kavita", "Ritu", "Vikram", "Manish", "Isha"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Mehta", "Jain", "Agarwal", "Yadav", "Chauhan",
        "Reddy", "Nair", "Iyer", "Bose", "Das", "Khan", "Malhotra", "Kapoor", "Joshi", "Patel"]
SUFFIX = ["Traders", "Enterprises", "Industries", "Solutions", "Pvt Ltd", "& Sons", "Logistics", "Foods"]
LOCATIONS = [  # city, state, pincode prefix
    ("Noida", "Uttar Pradesh", "2013"), ("Gurugram", "Haryana", "1220"), ("New Delhi", "Delhi", "1100"),
    ("Mumbai", "Maharashtra", "4000"), ("Pune", "Maharashtra", "4110"), ("Bengaluru", "Karnataka", "5600"),
    ("Chennai", "Tamil Nadu", "6000"), ("Kolkata", "West Bengal", "7000"), ("Jaipur", "Rajasthan", "3020"),
    ("Lucknow", "Uttar Pradesh", "2260"),
]
STATE_CODE = {"Uttar Pradesh": "09", "Haryana": "06", "Delhi": "07", "Maharashtra": "27",
              "Karnataka": "29", "Tamil Nadu": "33", "West Bengal": "19", "Rajasthan": "08"}
STREETS = ["MG Road", "Sector 18", "Station Road", "Industrial Area Phase 2", "Park Street", "Nehru Place",
           "Civil Lines", "Ring Road", "Market Road", "Main Bazaar"]


def gstin(state):
    pan = "".join(random.choices(string.ascii_uppercase, k=5)) + "".join(random.choices(string.digits, k=4)) \
          + random.choice(string.ascii_uppercase)
    return f"{STATE_CODE[state]}{pan}{random.randint(1, 9)}Z{random.choice(string.digits)}"


def base_customer(i):
    city, state, pin_prefix = random.choice(LOCATIONS)
    first, last = random.choice(FIRST), random.choice(LAST)
    company = f"{last} {random.choice(SUFFIX)}"
    return {
        "customer_id": f"C{1000 + i}",
        "customer_name": company,
        "contact_person": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{random.randint(1, 99)}@{random.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'company.in'])}",
        "phone": f"{random.choice('6789')}{''.join(random.choices(string.digits, k=9))}",
        "address": f"{random.randint(1, 250)}, {random.choice(STREETS)}",
        "city": city,
        "state": state,
        "pincode": pin_prefix + f"{random.randint(0, 99):02d}",
        "gstin": gstin(state),
        "created_date": f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
    }


def messy_variant(rec, new_id):
    """Create a duplicate of a record with realistic data-entry noise."""
    r = dict(rec)
    r["customer_id"] = new_id
    name = r["customer_name"]
    r["customer_name"] = random.choice([
        name.upper(), name.lower(), f"  {name}  ", name.replace("Pvt Ltd", "Private Limited"),
        name.replace("&", "and"), name[:-1] if len(name) > 6 else name, name.replace("  ", " ").replace("a", "aa", 1),
    ])
    ph = rec["phone"]
    r["phone"] = random.choice([f"+91 {ph[:5]} {ph[5:]}", f"91{ph}", f"0{ph}", f"{ph[:3]}-{ph[3:6]}-{ph[6:]}", ph])
    r["email"] = random.choice([rec["email"].upper(), f" {rec['email']} ", rec["email"]])
    r["state"] = random.choice([rec["state"], rec["state"].upper(), {"Uttar Pradesh": "UP", "Delhi": "NCT of Delhi",
                                "Maharashtra": "MH", "Karnataka": "KA", "Haryana": "HR"}.get(rec["state"], rec["state"])])
    r["city"] = random.choice([rec["city"], rec["city"].lower(), rec["city"].upper()])
    r["address"] = rec["address"].replace("Road", "Rd").replace("Sector", "Sec")
    r["created_date"] = f"2026-{random.randint(1, 9):02d}-{random.randint(1, 28):02d}"
    if random.random() < 0.3:
        r["gstin"] = ""
    return r


def main():
    rows = [base_customer(i) for i in range(250)]
    next_id = 1000 + len(rows)

    # ~40 duplicates of existing customers
    for rec in random.sample(rows, 40):
        rows.append(messy_variant(rec, f"C{next_id}"))
        next_id += 1

    # inject invalid / incomplete records
    bad = []
    for _ in range(18):
        r = base_customer(next_id)
        r["customer_id"] = f"C{next_id}"
        next_id += 1
        issue = random.choice(["email", "phone", "pincode", "name", "gstin", "state"])
        if issue == "email":
            r["email"] = random.choice(["not-an-email", "name@@gmail", "abc@.com", "user@domain"])
        elif issue == "phone":
            r["phone"] = random.choice(["12345", "98765", "abcdefghij", "00000"])
        elif issue == "pincode":
            r["pincode"] = random.choice(["12", "ABC123", "9999999"])
        elif issue == "name":
            r["customer_name"] = ""
        elif issue == "gstin":
            r["gstin"] = random.choice(["ABCDE1234", "27XXXXX0000X1Z", "12345678901234"])
        elif issue == "state":
            r["state"] = ""
        bad.append(r)
    rows.extend(bad)

    random.shuffle(rows)
    df = pd.DataFrame(rows)
    out = Path(__file__).resolve().parents[1] / "data" / "raw" / "customers_raw.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
