import json

from main import handler

event = {
    "job_id": "job-001",
    "policy_number": "POL-123456",
    "claim_text": (
        "Insurance Claim Form\n"
        "Customer ID: CUST-987654\n"
        "Policy Number: POL-123456\n"
        "Patient Name: Rajesh Kumar\n"
        "Age: 42\n"
        "Gender: Male\n"
        "Hospital Name: Apollo Hospitals, Bangalore\n"
        "Diagnosis: Gall Bladder Stones (Cholelithiasis)\n"
        "Procedure: Laparoscopic Cholecystectomy (Gall Bladder Removal)\n"
        "Date of Admission: 12-Feb-2026\n"
        "Date of Discharge: 14-Feb-2026\n"
        "Total Bill Amount: INR 1,85,000\n"
        "Claim Amount Requested: INR 1,75,000\n"
        "Doctor Name: Dr. Anil Sharma\n"
        "Pre-Authorization: Approved\n"
        "Claim Type: Cashless"
    ),
    "policy_text": (
        "Health Insurance Policy Document\n"
        "Policy Name: Comprehensive Health Shield Plan\n"
        "Policy Number: POL-123456\n"
        "Insured Name: Rajesh Kumar\n"
        "Coverage Amount: INR 10,00,000\n"
        "Policy Period: 01-Jan-2026 to 31-Dec-2026\n"
        "Policy Type: Renewal (continuous coverage since 01-Jan-2024)\n"
        "Coverage Details:\n"
        "- In-patient hospitalization expenses\n"
        "- Pre and post hospitalization (30/60 days)\n"
        "- Day care procedures\n"
        "- Ambulance charges\n"
        "Specific Coverage: Gall Bladder Removal\n"
        "- Covered under surgical procedures\n"
        "- Waiting period: 2 years (waived if renewal)\n"
        "- Includes laparoscopic procedures"
    ),
}

if __name__ == "__main__":
    print(json.dumps(handler(event, None), indent=2))
