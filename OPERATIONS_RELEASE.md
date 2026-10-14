# Store, profiles and dispatch documents

The signed-in workspace displays the company and department, for example **TPPL HR**. The sidebar name/avatar opens **My profile**. Profile changes update the same MongoDB employee record that HR reads. The signed-in portal switcher is removed; `/admin` and `/user` remain separate entry links.

**Projects**, **Customer POs** and **Customers** are separate navigation items, subject to department permissions. The PO register links original/revised documents to their projects. HR, QC and Maintenance roles use the same source and workflow in local preview and production.

## Stock corrections

Store/Admin can open a material and select **Edit inbound / outbound**. Enter the corrected cumulative totals, date and reason. Available quantity is calculated from opening + inbound + stock adjustments − outbound. The operation records before/after totals and signed movement corrections atomically; it does not alter original vouchers. Negative stock and stale saves are rejected. Corrections change stock quantities only, not inventory valuation or financial ledgers.

## Dispatch and internal operations

Accounts/Admin → **Sales & invoices → Create invoice**:

- **Dispatch · GST tax invoice** records supplier/customer GSTIN, billing and delivery addresses, place-of-supply state code, HSN, stock unit and per-line GST rate. Domestic forward-charge intrastate invoices split CGST/SGST; interstate invoices use IGST. Tax liabilities post separately from sales revenue, the customer owes the gross amount, and stock is deducted atomically. Credit-note allowances reverse tax proportionately. Historical tax-exclusive invoices remain unchanged.
- **In-house · material issue without GST** records a department/recipient and requires confirmation of internal consumption/movement within the same GST registration. It creates a printable Store issue and reduces stock without a customer receivable, sales entry or GST. The register appears below sales invoices. Separate GST registrations must be reviewed as supplies rather than assumed tax-free internal movements.

Tax rates and HSN codes require Accounts review. This release does not cover exempt bills of supply, exports, reverse-charge invoicing, GST returns, IRN/e-invoice registration or government e-way bill generation. Enter official e-way bill references through Store after generating them externally. Payroll and attendance configuration requirements are documented in [HR_OPERATIONS.md](HR_OPERATIONS.md).

Invoice-field references: [CBIC Rule 46](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000136/1000001) and [CBIC Rule 55](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000146/1000001).

## Admin project deletion

Open a project as Admin and choose **Delete project**. Download the complete ZIP, confirm that the file is saved, and type the project reference. The ZIP contains original documents, structured JSON, readable HTML and CSV reports, approvals, inspection reports, chat, material issues, stock movement references and previous dispatch archives. This works for active, completed and earlier-workflow projects.

The server binds each export to its Admin and project. Downloads are chunked and checked with SHA-256. All chunks must be retrieved before deletion; exports expire after one hour. Changes to the project or related records require a new ZIP. Cancellation leaves the project intact.

Deletion atomically removes project documents, requirements, issue details, approvals, inspection calls, chat, notifications/read receipts, queued dispatch archives and temporary exports. Other projects and shared customer, product, stock movement and accounting records remain unchanged; issued stock is not returned. A minimal company activity receipt records the deletion and archive fingerprint. Deletion is blocked while an archive email is actively being sent. No live project is deleted by deployment or by the automated tests.

Test the flow with `python -m unittest test_project_deletion -v` and `python test_browser.py browser-project-delete.cjs`.

## Verification

`python -m unittest discover -v` uses isolated local test databases. Browser checks: `python test_browser.py browser-hr.cjs`, `python test_browser.py browser-operations.cjs`, and `python test_browser.py browser-projects.cjs`. `python build_production.py` builds the combined corporate site and ERP with versioned assets. Private `.env`, local test data and logs are excluded from Git and deployment uploads.
