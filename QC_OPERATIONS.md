# QC dispatch and uploaded reports

Every department can create drawing batches and upload finished reports. QC/Admin maintains process progress, material allocation, evidence and approval. Assigned-QC restrictions apply to approval; Admin retains oversight.

1. Admin/Design creates the project, PO and plant.
2. QC/Admin imports the process tracker, or an employee creates drawing batches with quantity and planned dispatch date.
3. QC/Admin allocates heat/plate lots and attaches drawings, numbering references and required TCs.
4. Any employee chooses **Upload report** in the batch and selects the finished PDF, Excel, Word, image or other supported report file. No report layout or cell entry is required in the ERP.
5. QC/Admin downloads and checks the report, then approves it with review notes. Required traceability and documents must be complete first.
6. Process stages through Final QC, project final inspection, packing, EWAY challan and dispatch follow the existing workflow.

Uploading a revised batch report preserves the earlier file and requires fresh QC approval and final inspection. Changes to drawings, certificates or material allocation also invalidate release readiness. Adding an EWAY challan does not invalidate inspection approval. Dispatched batches are read-only. Earlier reports prepared within the application remain available to download.

The process-tracker importer remains available for production quantities. It supports the PROCESS and optional Current PO layouts described in existing company spreadsheets; imported progress is unverified until QC confirms it. **Suggest quantities from Excel** does not approve Final QC or Packing. These tracker checks do not restrict uploaded report layouts.

Batch ZIPs include uploaded report revisions, process/traceability records and linked documents. Batch ZIPs above 4 MB require individual downloads or the Admin project archive. Project dispatch/deletion archives include report files, history and earlier saved report records. Deleting a project removes its linked reports after the existing archive-download confirmation.

See [Uploaded reports](REPORT_WORKSHOP.md) for supported file types, size limits and verification commands.
