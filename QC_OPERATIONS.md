# QC dispatch and inspection reports

Open **QC dispatch & reports** in any department portal. Every signed-in user can create a drawing batch, import inspection readings, prepare a blank report from an existing format, enter measurements, save drafts, create revisions and download PDF/Excel reports. Project visibility rules still apply. QC and Admin maintain process progress, material allocations, evidence and approval. Assigned-QC restrictions apply to approval; Admin retains oversight.

## From a PO to dispatch

1. Admin or Design creates the project with the actual customer PO and correct plant.
2. QC/Admin imports the process tracker, or any employee creates drawing batches manually. Each batch has its own drawing, quantity and planned dispatch date. Repeated deliveries of the same drawing stay separate.
3. QC/Admin allocates heat/plate/AI lots, including split quantities, and attaches the actual drawing and any numbering reference. Select **TC required** when creating a batch if a certificate is mandatory. A filename in Excel does not count as an uploaded drawing.
4. Any employee imports an inspection workbook. **Blank format** starts a new inspection with empty readings. **Historical readings** retains readings as an unapproved Draft; its PO, drawing and quantity must match the batch.
5. Enter measurements in groups of five pieces. Explicit numeric tolerances are checked automatically. Missing readings, out-of-tolerance values and unreviewed text prevent approval. Unsupported tolerances require a recorded assessment and reason. An Excel OK remark is never an approval.
6. QC/Admin reviews and approves the report after complete material traceability and required evidence are attached. Approved measurements and evidence snapshots are immutable. A new revision retains the earlier report; blank reuse clears readings and assessments.
7. QC/Admin records full or partial process quantities. Complete stages through Final QC, then perform the project's final inspection. Packing follows project final inspection. Record each batch's actual dispatch and attach its EWAY challan, then complete the PO through the existing project dispatch action.

Reports added or changed after final inspection require fresh inspection. Changed drawing/certificate/material allocations invalidate release readiness; an approved report needs a new approved revision. Adding an EWAY challan does not invalidate measurement approval. Dispatched batches are read-only.

## Supported spreadsheets

The process importer supports a **PROCESS** sheet with PO, Drawing No, Thickness, ten process columns, Qty, Dispatch Date, Actual Dispatch Date, Drawing and Numbering Ref. Stages: Cutting, Machining, Tapping, Finishing, QC, Blasting, Primer & Engraving, Final Paint, Final QC and Packing.

The optional **Current PO** sheet supplies Thickness, Heat No, Plate No, AI number, Qty and dispatch dates. It contains no drawing association, so allocations are explicit. Quantities cannot exceed the material lot or batch. OLD PO and other sheets remain in the retained original file and are not imported as current production.

Inspection layout: customer/part/date in row 3, drawing/revision/PO/quantity in row 4, piece numbers in row 7 or 8, characteristics in A:D and five readings in E:I per sheet. Up to 100 pieces and 120 characteristics per report, with up to 200 tracker rows per import. Files must be `.xlsx` and at most 3 MB. Split larger batches before import. Formulas are not executed or accepted as numeric readings.

Tracker imports never mark source progress or actual dispatch dates as verified. **Suggest quantities from Excel** pre-fills a review form; partial quantities remain In progress, and Final QC/Packing remain pending. QC must review and save explicitly. Importing the identical tracker into the same project twice is rejected.

## Downloads and history

- PDF and Excel reports include report ID, drawing revision, PO, readings, status, inspector/approver, traceability and manual assessment reasons. Drafts are labelled Draft. Approved exports show the process snapshot at approval.
- **Export PO tracker** provides current process quantities/statuses, planned/actual dates, report references, allocated traceability and unused lot quantities.
- **Download batch ZIP** contains reports, revisions, process/traceability data, audit records and linked evidence. ZIPs above 4 MB require individual downloads or the Admin project archive.
- Project dispatch and pre-deletion archives include QC records and generated reports. Project deletion removes related QC records transactionally.

Version checks prevent an older screen from overwriting newer work. Measurement changes record before/after values and employee identity. Original workbooks, readings and customer reports belong in private database storage or ignored local folders, never public web assets or Git commits.

## Verification

Run `python -m unittest test_qc test_projects test_project_deletion -v` against the disposable local replica set. For browser coverage, create `.tools/qc-fixture.xlsx` from `test_qc.workbook_file()` (base64 content), then run `python test_browser.py browser-qc.cjs`. Coverage includes Store report preparation, persisted edits, blank reuse, exports, permissions, approval validation and mobile layout.
