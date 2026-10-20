OPERATIONAL AUTHOR REVIEW

Open operational_claim_review.html for the 74 graph assertions and response_composition_review.html for the source-linked response wording. The HTML files are readable review views. Enter actual decisions, reasons, reviewer and review time in their corresponding JSON files. Do not treat source checking or permission to continue development as approval of every assertion.

All operational decisions in this package are pending. author_review_translation_en.json is an English translation of the submitted source-record review; it is not the original Arabic document.

When every operational assertion, response profile and ancillary response text has actually been reviewed and approved, run from the package directory:
  python evaluation/rq2_tool.py prepare-approval

This prepares a pending operational_approval_receipt.json bound to the exact files. The named reviewer must then record the actual approval, date and reason. Do not fill another person's approval by inference. The independent RQ2 freeze command verifies the receipt and review files before accepting a build lock.

Read evaluation/RQ2_PROTOCOL.txt for the full order. The approval is an operational source-and-wording review; it is not ethical clearance, a user-study result or RQ2 accuracy.
