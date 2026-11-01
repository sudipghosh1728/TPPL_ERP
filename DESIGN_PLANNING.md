# Design planning, Purchase and project assistance

Open **Design & material planning** from any department, or from a project overview.

1. Admin creates a **Purchase** account through Users & departments. Purchase is a super-admin role with full company, HR, payroll, finance, project and user-management access. Purchase signs in at `/admin`; other departments use `/user`.
2. Design schedules the PO into dispatch lots, for example 60 + 125 + 125 + 125 + 125 = 560 pieces. Each lot has its own name, quantity and date. Choose whether delivery quantities mean finished assemblies or individual parts. For assemblies, add top-level jobs and nested sub-jobs, then add multiple drawings to each job in one save. A drawing quantity equals the total job units in that dispatch multiplied by the parts needed per job. Top-level job totals cannot exceed the dispatch quantity; component totals may exceed it. Earlier individual-part lots retain their existing limits and can change basis only before jobs or drawings are added.
3. For each drawing, Design adds Store materials, stock units per drawing part, finished dimensions in mm, optional blank dimensions, grade/tolerance and cutting instructions. Required inventory units = units per drawing part × drawing batch pieces. Use the actual Store stock unit consistently; this does not convert plate area or bar length into inventory units automatically.
4. Design records cumulative units cut and measured scrap kg. Fabrication can read all dimensions and requirements. Purchase sees required, issued/consumed, outstanding, cut, scrap and available quantities per material and project. Cutting updates do not deduct inventory; Store issues remain the inventory source of truth. This is a planning and recording tool, not an automatic nesting optimizer.

| Process | Owner |
| --- | --- |
| Cutting | Design |
| Machining | Machining |
| Tapping, Finishing, Blasting, Primer & Engraving, Final Paint, Packing | Fabrication |
| QC and Final QC | QC |

QC, Admin and Purchase can update any process using **QC dispatch & reports → Open drawing batch → Update all process quantities**. QC retains the project's assigned-person restrictions; other departments update their own processes. Every changed stage records who updated it and their department. Permissions are enforced by the API as well as the form. Final QC retains traceability, certificate and approved-report requirements. A scheduled lot can complete Final QC, packing and dispatch while other lots remain pending. Project completion still requires every planned quantity and batch to be complete. Dispatch reminders use the earliest incomplete lot date.

## PO specifications

New PO and revised-PO uploads run a local rules-based named-entity recognizer for material grades, certificate requirements, painting systems, RAL colours, surface preparation, coating thickness and dimensions. PDF text, DOCX, XLSX, CSV and text files are supported. Extracted painting and material suggestions appear in the project and planning view. Every signed-in department can review/update them with an audit note. Changed specifications invalidate QC evidence for undispatched batches and retain the previous values in the audit trail. A revised PO preserves reviewed specifications and shows new suggestions separately. **Extract latest PO** also works on previously uploaded POs.

This is a deterministic domain rules model, not a trained statistical language model. It can miss unfamiliar wording and must be checked against the PO. Image-only/scanned PDFs and image files require OCR text or manual specification entry. Unreadable or oversized text does not prevent the PO being stored. No document is sent to an external AI service.

## Project assistant and reports

Project chat detects department names and dimension/material/process terms, then sends in-app reminders to active matching users. Explicit department/person selectors and `@username` mentions can direct messages. Dimensions route to Design/Fabrication; materials to Design/Purchase/Store; painting to Fabrication; machining to Machining; inspections/rework/reports to QC. The assistant posts a visible routing acknowledgement. It does not silently edit approved dimensions, quantities or workflow state.

A chat file is stored once as a project-linked report and appears in **Uploaded reports**, with an original-file download in chat. Existing 3 MB/type limits apply. Reports still need QC approval. QC, Admin and Purchase can delete draft or approved reports with a mandatory reason; deleting a current batch report invalidates final inspection/packing and requires a replacement report. Deletion is blocked for completed projects and dispatched batches, which preserve their issued records. Report deletion remains in the audit trail; deleted chat attachments are marked accordingly.

Validation: `python -m unittest test_planning test_qc test_projects test_report_workshop test_project_deletion -v`; `python test_browser.py browser-planning.cjs`. All use disposable local MongoDB databases. Private environment files, customer documents and browser artifacts remain ignored.

QC can also upload all seven project document types: PO, Revised PO, Drawing, Material requirement, EWAY challan, TC and Supporting. PO/drawing/requirement revisions retain the existing Design resubmission controls. QC PO upload does not grant PO-deletion permission.

## Assembly dispatch example and documents

A dispatch of 80 finished assemblies can contain 60 Frames and 20 Housings. Each Frame needing 2 Plates and 1 Bracket creates batches of 120 Plates and 60 Brackets. A Frame with 2 Support sub-jobs, each needing 3 Pins, creates 360 Pins. Housing drawings are tracked separately. Jobs may contain their own drawings as well as sub-jobs. Each drawing retains independent process quantities, material requirements, traceability, reports and QC checks. The tracker export includes the dispatch lot, job path and quantity multiplier.

Dispatch reminders remain active until **all** required drawing batches in the assembly lot are dispatched; component quantities are never treated as completed assembly quantities. A completed lot's structure cannot be expanded after its first drawing dispatch. Flat Excel tracker imports cannot infer assembly relationships and are unavailable on assembly projects; use the job/drawing planner.

New projects require both the customer PO and a project drawing. Existing projects remain accessible. Normal process updates through painting do not require linked drawing/TC evidence. Drawing evidence and any required TC are checked at final inspection. Upload a TC through Project documents and select the entire project, a job/sub-job (including descendants), or one drawing part. Job/project TCs also apply to subsequently planned drawings. Already inspected drawings retain their approved evidence; completed projects cannot receive a late TC. Other late supporting documents do not alter the immutable dispatch archive.

Assembly workflow browser check: `python test_browser.py browser-assemblies.cjs`.
