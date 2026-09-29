# TPPL One — Heavy fabrication workspace

Independent local ERP prototype for heavy fabrication. No Tally connection or paid service is required to run it. All business records are stored in SQLite on your computer.

## Run locally

Requires Python 3.10 or later. No Python packages need installing.

```powershell
cd E:\TPPL_ERP
python server.py
```

Open http://localhost:8000. Sample data is created on the first launch. Stop with Ctrl+C. If already running, use the existing browser address.

The first visit displays **Create your Admin account**. Choose your own username and a password of at least 10 characters. There are no built-in passwords. In **Users & departments**, Admin can create named users for Design, Machining, Fabrication, Store, and Accounts, reset their passwords, or disable access. Use separate browser profiles/private windows when demonstrating multiple departments.

## Working features

- Dashboard calculated from saved records and searchable sales/material registers.
- Material catalog: steel plates, structural steel, machining inserts, grinding wheels, paint, and welding supplies.
- Purchase orders and full goods receipt, with stock movements and prevention of duplicate receipt.
- Department logins with server-enforced permissions, password hashing, expiring sessions, and Admin user management.
- Customer PO upload and controlled job routing through Design, optional Machining, Fabrication, and Store.
- Multiple material requirements per job, Test Certificate requirements, review notes, document downloads, revision requests, and handoff history.
- Consolidated Store demand, shortages, approval checks, partial material issue, TC attachment validation, and stock deduction.
- Multi-item sales invoices with editable prices, automatic totals, due dates, notes, stock deduction, searchable status tabs, invoice preview, and Print / Save PDF.
- Customer and supplier accounts, contact details, opening balances, cash/bank accounts, and expense accounts.
- Double-entry journal postings in integer paise, ledger statements with date filters and running balances, CSV statement export, day book, and trial balance.
- Partial/full customer receipts and supplier payments, allocated to a specific invoice, received bill, or opening balance. Overpayments are rejected.
- Business expense vouchers and general journal vouchers for non-party accounts.
- Inventory receipts, low-stock indicators, warehouse valuation, procurement reports, and CSV export.
- Company settings, activity history, and optional Tally sales voucher XML export.

The SQLite database is `data/erp.db` and is excluded from Git. Back it up while the server is stopped. The seed records are fictional. Inventory quantities are whole stock units; unit prices and sales totals exclude tax. Dashboard inventory value uses listed price and is not accounting inventory valuation.

## Scope before production use

This is a local operational prototype, not yet a complete Tally replacement. It binds only to localhost and now has named-user authentication and department authorization. It has not been configured for internet hosting: HTTPS, production serving, malware scanning of uploads, operational monitoring, and deployment hardening remain separate work.

Production implementation still requires: GST tax invoices and returns, sales returns and credit notes, voucher reversal/cancellation, advances and refunds, bank reconciliation, accounting period locks, automated opening-balance imports, reusable BOM templates, units of measure and weight conversion, detailed cutting/welding/grinding/painting scheduling, finished-goods receipts, costing, QC, partial purchase receipts, automated backups and restore, and deployment security. No HR workspace is included.

## Department manufacturing workflow

1. **Admin:** open **Jobs & customer POs → Upload job PO**. Enter the customer, PO number, job title, due date, and PO document. The job goes to Design.
2. **Design:** review the PO, upload drawings, and add any Design material requirements. Approve with a mandatory machining yes/no decision, or return the PO to Admin with review notes. A drawing is required for the machining route.
3. **Machining, when required:** see only jobs approved for machining, including their PO, drawings, and requirements. Add basic material quantities, TC requirements/specifications, and notes, then send to Fabrication for recheck.
4. **Fabrication:** review the combined material requirements, add its own requirements, and approve or request changes. A machining job returns to Machining for execution after this approval. A non-machining job proceeds directly to Fabrication execution.
5. **Store:** view all manufacturing material requirements and combined demand versus stock. Issue only approved requirements, partially or fully. For TC-controlled material, upload the Test Certificate to the job and select it with its heat/batch/reference when issuing stock.
6. **Machining:** once Store has issued the Design and Machining materials, mark machining complete to hand the job to Fabrication.
7. **Fabrication:** once all remaining materials have been issued, mark the job complete. The handoff history records each actor, department, action, and review note.

Jobs that do not need machining never appear in the Machining workspace or its document downloads. Fabrication change requests return machining jobs to Machining requirements and non-machining jobs to Design. Admin PO revisions remain in the document history. Use **Refresh** to pull in another department's latest actions; an open job also rejects stale edits on the server.

**Accounts is a separate workflow:** customer/supplier ledgers, sales, receipts/payments, expense vouchers, trial balance, and supplier purchase orders. Store receives these supplier POs, which posts the supplier bill to Accounts. Customer POs uploaded to manufacturing are job documents; they do not automatically create a sales invoice or accounting entry.

Uploaded documents are stored inside the local SQLite database and downloaded through authenticated, job-authorized endpoints. Supported files are PDF, PNG/JPEG, TXT/CSV, DWG/DXF, STEP/STP, DOCX, and XLSX, up to 5 MB each. Files are downloaded rather than rendered inline. TC validation checks attachment presence and a reference, not the technical authenticity of certificate contents.

New jobs use the departmental workflow. Earlier single-material prototype jobs remain visible to Admin as a read-only register. Existing sales, stock, and financial postings are preserved. Manufacturing stock issues track quantities but do not yet post inventory/WIP accounting entries.

## Accounts and sales: quick start

1. Open **Accounts & contacts → Add customer**. Add contact information and optionally an opening balance. Create suppliers the same way.
2. Open **Sales & invoices → Create invoice**. Choose a customer, add one or more products, enter quantities/prices, and set the payment due date. Saving issues stock and posts the sale to the books.
3. Select **Receive payment** on an invoice. Enter the actual amount, cash/bank account, date, and reference. Partial receipts leave the remainder outstanding.
4. Use **View → Print / Save PDF** for a printable sales document and payment history.
5. Select an account's **Open ledger** action to see its transactions. Use date filters or export the statement.
6. Accounts creates supplier **Purchase orders**; Store receives goods. Accounts can then use **Pay supplier** to settle the bill in full or in parts. Admin can perform both actions.
7. Create an expense account under **Add account**, then use **Record expense**. Use **Books & vouchers** for the day book, trial balance, and general journal vouchers.

### Bookkeeping model and existing records

Sales debit the customer and credit Sales revenue. Customer receipts debit cash/bank and credit the customer. Goods receipt debits Material purchases and credits the supplier. Supplier payments debit the supplier and credit cash/bank. Opening entries use Opening balance equity. Manual journals cannot post to customer/supplier accounts, which keeps document allocations consistent.

Material purchases are posted to an expense account using a simplified periodic model. Physical stock is tracked separately: inventory capitalization, cost of sales, work-in-progress, and closing stock adjustments are not automated. The trial balance is not a complete set of financial statements.

Existing local sales are migrated once without another stock deduction. Previously paid demo sales are assumed received in Main bank; their vouchers explicitly identify this migration assumption. Existing received purchase orders are posted once. A pre-upgrade copy of this workspace's database is saved at `data/backups/before-accounting.db`. New installations do not require that backup file. Review migrated entries before using real company data.

Posted documents are immutable in this version. There is no edit, deletion, return, or reversal flow yet. Customer-credit and supplier-debit openings can be recorded, but refund settlement is not yet available. All invoices exclude tax and are labelled as non-GST documents.

Tally XML is an optional transition helper, not live synchronization. Matching ledgers must already exist; export excludes GST and stock allocations and has not been validated against your hosted Tally instance. Test on a disposable Tally company. Reimport may duplicate vouchers.

## Validation

```powershell
python -m unittest discover -p 'test_*.py' -v
node --check public/app.js
node --check public/finance.js
node --check public/workflow.js
```

Tests use a temporary database and verify purchase receipt, duplicate prevention, material issue, job completion, multi-item invoices, monetary precision, partial settlements, overpayment rejection, balanced postings, rollback, migration idempotence, persistence, and XML structure.

Department tests additionally cover both job routes, prohibited actions, document access, TC enforcement, partial stock issue, stale versions, revision requests, disabled users, cross-site request rejection, and data filtering.

Browser tests require Playwright and its Chromium browser. With Playwright installed, run `python test_browser.py` for an isolated finance workflow and `python test_browser.py browser-workflow.cjs` for the six-department manufacturing flow. Both create disposable databases and test-only accounts. `node browser-check.cjs` runs read-only checks of the local app with an existing Admin account supplied through `ERP_USER` and `ERP_PASSWORD`. If Playwright is outside this project, set `PLAYWRIGHT_MODULE` to its installed module path. Screenshots and a sample invoice PDF are written under `test-results/`. GitHub Actions runs backend tests and JavaScript syntax checks on pushes and pull requests.

Repository: https://github.com/sudipghosh1728/TPPL_ERP. Local databases, user credentials/sessions, uploaded documents, backups, logs, and test output are excluded from version control.
