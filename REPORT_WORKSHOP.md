# Report Workshop

Open **Report Workshop** in any department's sidebar. Create a blank workbook or import an `.xlsx` file. This editor has no fixed drawing, PO, quantity or inspection-column layout. Each workbook remains a draft until QC or Admin reviews it.

- Edit cells directly or use the value/formula bar. Shift-click or enter a range such as `A1:D4` to select cells. Paste tab-separated rows from Excel.
- Format headings, fonts, colours, alignment, borders and wrapping. Merge/unmerge cells, change row/column sizes, append rows/columns and add/rename sheets. Undo keeps the last 20 local edits.
- Save to persist changes in MongoDB. Concurrent edits are rejected rather than overwriting another user's work. Unsaved changes stay on screen after a rejected save; copy them before reopening.
- Download the saved workbook as Excel. Original drawing/media parts, including EMF/WMF logos, remain in the download. Raster pictures appear in the editor; unsupported vector pictures carry a preview warning. Browser print/PDF covers the active sheet's displayed block of up to 100 rows. Use Excel to print the complete original page layout.
- Arithmetic and SUM, AVERAGE, MIN, MAX, COUNT, ROUND and ABS recalculate on save. Unsupported formulas stay in Excel and appear as `#EXCEL!` in the editor. Invalid/unsupported formulas block QC approval. Excel recalculates formulas when opening the download. This is a report editor, not a full Excel calculation engine; macros, charts, pivot tables, drawing editing and advanced formulas are not browser editing features.

Reports without a project are explicitly shared company reports. A linked report follows the project's visibility, assignment and completed-project restrictions. Every department can prepare drafts. Only QC/Admin can approve; assigned-QC rules apply for project reports. Approved workbooks cannot be edited. **Copy to revised draft** retains all existing values and the original approved version; clear/update historical measurements before using the copy for a new inspection.

Report approval records document review only. Existing QC batch measurements, traceability, final inspection and dispatch approvals remain required. Project-linked workbook originals, saved Excel versions, cell models and history are included in project dispatch and deletion ZIPs. Deleting a project removes its linked report records after the existing archive confirmation.

Limits: 3 MB input, 20 MB expanded package, 50 sheets, 1,000 rows and 100 columns per sheet, 50,000 populated/formatted cells and 2.5 MB editable model. Original sheets are retained; row/column additions append rather than shift existing drawing anchors. Imported existing data is never assumed to be a new or approved inspection.

Checks: `python -m unittest test_report_workshop -v` and `python test_browser.py browser-workshop.cjs` use the disposable local MongoDB replica set. User workbooks and generated outputs are private and excluded from Git.
