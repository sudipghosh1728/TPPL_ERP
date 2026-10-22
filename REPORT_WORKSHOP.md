# Uploaded reports

Open **Uploaded reports** in any department portal, or use **Upload report** inside a project or QC drawing batch.

1. Prepare the report using your existing tools and format.
2. Choose **Upload report**, select the file and enter a report name/type. Optionally link a project and inspection batch.
3. Users can search, download the original file and see upload/approval history. QC/Admin downloads and checks the file, then approves it with review notes.
4. **Upload revised report** stores a new pending report and retains the earlier file and approval record.

Supported files: PDF, XLS/XLSX, DOC/DOCX, CSV, text, PNG/JPEG/WebP and ODS/ODT. Maximum file size is 3 MB. Files are stored as opaque documents: there is no spreadsheet editor, fixed column requirement, quantity parser or automatic reading assessment. Downloaded files retain their exact uploaded bytes.

Every department can upload. Project visibility and assigned-QC review restrictions still apply; Admin retains oversight. A report linked to an inspection batch becomes its current report and invalidates earlier final inspection/packing. QC approval requires that batch's complete material traceability and required drawing/certificate evidence. Process completion, final inspection and dispatch retain their existing controls. Completed projects and dispatched batches are read-only.

Unlinked reports are shared company reports. Existing reports prepared in the earlier editor remain downloadable. Uploaded reports and revisions are included in batch, project-dispatch and project-deletion ZIPs. They are stored privately in MongoDB, never in Git or public assets.

Checks: `python -m unittest test_report_workshop test_qc test_project_deletion -v`. To run browser coverage, save `test_report_workshop.fixture()` to `.tools/report-upload.xlsx`, then run `python test_browser.py browser-workshop.cjs` (or `browser-qc.cjs`).
