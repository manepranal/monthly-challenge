"""Build-time only: generate the demo attachment PDFs (+ .txt fallbacks).

The Deal Organizer *reads* these at runtime; it does not need this script. It is
kept in the repo so the fixtures are reproducible. Requires fpdf2:

    pip3 install fpdf2
    python3 examples/_make_fixtures.py

Every document below is fictional. The Purchase Agreement is the single source of
truth for the deal's milestone dates; the other documents reinforce a few of them.
"""

import os
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).parent / "attachments"
OUT.mkdir(parents=True, exist_ok=True)

# --- Document text ---------------------------------------------------------
# Each entry: filename stem -> (title, body_lines)

DOCS = {
    "Purchase_Agreement_123_Maple_Ave": (
        "RESIDENTIAL PURCHASE AND SALE AGREEMENT",
        """Property: 123 Maple Avenue, Rye, New York 10580
Escrow No.: ESC-88213

SELLER: Michael Bennett and Susan Bennett
BUYER: Jordan Shah and Priya Shah
LISTING BROKER: Harborview Realty
BUYER'S BROKER: The Real Brokerage (Agent: Alex Rivera)

1. PURCHASE PRICE. The total purchase price is $985,000.00, payable as follows:
   Earnest money deposit of $49,250.00 held in escrow; balance due at closing.

2. EFFECTIVE DATE. This Agreement is fully executed and effective as of
   July 8, 2026 (the "Effective Date").

3. ATTORNEY REVIEW. This Agreement is subject to review by the attorneys for
   both parties. The attorney review period shall expire at 5:00 PM on
   July 11, 2026. If not disapproved in writing by that date, this Agreement
   becomes binding.

4. HOME INSPECTION CONTINGENCY. Buyer shall have the right to conduct
   inspections of the Property. Buyer's inspection contingency shall expire on
   July 18, 2026. Buyer must deliver any inspection objections in writing on or
   before that date.

5. APPRAISAL CONTINGENCY. This Agreement is contingent upon the Property
   appraising for at least the purchase price. The appraisal contingency shall
   be satisfied or waived no later than July 25, 2026.

6. MORTGAGE / FINANCING CONTINGENCY. Buyer shall apply for a mortgage loan and
   shall obtain a written mortgage commitment on or before August 7, 2026 (the
   "Mortgage Commitment Date"). Buyer's obligation is contingent on such
   commitment.

7. FINAL WALK-THROUGH. Buyer shall be entitled to a final walk-through of the
   Property on September 4, 2026, the day prior to Closing.

8. CLOSING. The closing of title (the "Closing Date") shall occur on
   September 5, 2026, at the offices of the title company, time being of the
   essence.

9. POSSESSION. Seller shall deliver possession of the Property to Buyer at
   Closing.

The parties acknowledge and agree to the terms above.

Seller: ______________________  Date: July 8, 2026
Buyer:  ______________________  Date: July 8, 2026
""",
    ),
    "Inspection_Report_123_Maple": (
        "HOME INSPECTION REPORT",
        """Prepared for: Jordan & Priya Shah
Property: 123 Maple Avenue, Rye, NY 10580
Inspection Date: July 14, 2026
Inspector: ProHome Inspections, License #NY-INSP-4471

SUMMARY OF FINDINGS
The home is generally in good and well-maintained condition. The following
items are noted for the buyers' awareness:

  - Water Heater: Approximately 11 years old and near the end of its service
    life. Budget for replacement within 1-2 years. (Recommend)
  - Basement: Minor moisture staining observed on the north foundation wall.
    No active leak at time of inspection. Recommend monitoring. (Monitor)
  - Roof: Asphalt shingle roof in serviceable condition, est. 8 years old.
  - Electrical: 200-amp panel, updated, no deficiencies observed.
  - HVAC: Forced-air gas furnace and central AC both operational.

This report should be reviewed prior to the expiration of the inspection
contingency on July 18, 2026.
""",
    ),
    "Appraisal_Report_123_Maple": (
        "UNIFORM RESIDENTIAL APPRAISAL REPORT",
        """Property: 123 Maple Avenue, Rye, NY 10580
Borrower: Jordan & Priya Shah
Lender: Meridian Home Loans
Effective Date of Appraisal: July 21, 2026

APPRAISED VALUE: $990,000

The subject property was appraised using the sales comparison approach with
three comparable sales within 0.5 miles closed in the last 90 days. The
appraised value of $990,000 exceeds the contract price of $985,000; the
property therefore supports the financing.

This report is provided in connection with the mortgage financing contingency.
The appraisal contingency date under the contract is July 25, 2026.
""",
    ),
    "Commission_Statement_123_Maple": (
        "COMMISSION DISBURSEMENT AUTHORIZATION (CDA)",
        """Escrow No.: ESC-88213
Property: 123 Maple Avenue, Rye, NY 10580
Anticipated Closing Date: September 5, 2026

Sale Price: $985,000.00
Total Buyer-Side Commission (2.5%): $24,625.00

DISBURSEMENT
  Brokerage (The Real Brokerage):            $24,625.00
  Agent Net to Alex Rivera (after split):    $22,162.50
  Brokerage Retained:                        $ 2,462.50

Please remit the agent net to the payee on file at closing. This CDA is
authorized by The Real Brokerage Commissions Team.
""",
    ),
    "Sellers_Disclosure_123_Maple": (
        "SELLER'S PROPERTY CONDITION DISCLOSURE",
        """Property: 123 Maple Avenue, Rye, NY 10580
Sellers: Michael & Susan Bennett

The sellers disclose the following, to the best of their knowledge:

  - Year built: 1998.
  - Roof: replaced 2018. No known leaks.
  - Basement: seasonal minor dampness after heavy rain; sump pump installed.
  - Systems: gas furnace (2015), central AC (2015), water heater (2015).
  - No known structural defects. No known lead plumbing.

LEAD-BASED PAINT DISCLOSURE
Because the home was built after 1978, federal lead-based paint disclosure
requirements do not apply; nonetheless sellers have no knowledge of lead-based
paint or hazards on the Property.

Buyers are advised to acknowledge receipt of these disclosures.
""",
    ),
}


def build_pdf(title: str, body: str, path: Path) -> None:
    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", size=10)
    for line in body.split("\n"):
        # fpdf2's core fonts are latin-1; keep the fixtures ASCII-clean.
        safe = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5, safe if safe else " ", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def main() -> None:
    for stem, (title, body) in DOCS.items():
        pdf_path = OUT / f"{stem}.pdf"
        txt_path = OUT / f"{stem}.txt"
        build_pdf(title, body, pdf_path)
        txt_path.write_text(f"{title}\n\n{body}")
        print(f"  wrote {pdf_path.name}  (+ {txt_path.name})")
    print(f"Done. {len(DOCS)} attachments in {OUT}")


if __name__ == "__main__":
    main()
