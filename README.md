# VECTORone — Business and manufacturing ERP

VECTORone is the product name; each installation has its own company identity, configured by Admin in Settings and displayed on sales invoices. The current workflow supports mechanical manufacturing, fabrication, machining, stores, sales, and accounts. Deploy a separate application instance and MongoDB database for each customer. Shared multi-company hosting and a custom workflow designer are not implemented; industry templates configure the existing modules. Existing company records and document references remain unchanged by the product rename.

Configurable ERP prototype with native MongoDB storage. The web application runs locally and connects to your configured MongoDB Atlas cluster or a MongoDB replica set. Tally is optional. Atlas service charges, if any, depend on your cluster plan.

## Company configuration

Admin Settings supports Factory, Supermarket, and General Business templates, company address, financial-year start, categories, warehouses, units, and custom product fields. New products accept those choices, optional unique barcodes, and custom field values. Existing records are preserved when settings change. Manufacturing can be disabled only when no production jobs remain active; its navigation and API actions are then disabled. Inventory, sales, purchasing, and accounts remain core modules.

Fresh installations start with empty business registers and system ledger accounts. Fictional records are enabled only in test fixtures. Each customer needs a separate deployment directory, private configuration, database, and database user. Do not copy another customer's data or private configuration into a fresh installation.

Current limits: INR, whole stock units, one location per product, and fixed department roles. POS checkout, batch/expiry tracking, tax calculation, stock transfers, configurable approval routes, and consolidated multi-company reporting are not implemented. Templates configure existing capabilities; they do not add these features. Financial-year start is metadata, not an accounting period lock.

For separate local evaluation, run `python local_preview.py` with the local MongoDB replica set running on port 27018 (`tppl-test`). Open http://localhost:8001. This uses database `vectorone_preview`, does not read Atlas credentials, and does not migrate the previous SQLite data. Create your Admin account and complete Settings. This launcher is for local evaluation.

Company tests: `python -m unittest test_company -v`. For the browser setup test, install npm dependencies and Playwright Chromium, set `ERP_TEST_CLEAN=1`, and run `python test_browser.py browser-company.cjs`. Tests use isolated databases, never the Atlas application database.

## Run locally

## Vercel deployment

`vercel.json` serves `public/` and routes `/api/*` to `api/index.py`. Set `MONGODB_URI` and `MONGODB_DATABASE` as sensitive production environment variables in Vercel. Provision the database and initial Admin locally first; the hosted endpoint deliberately rejects first-time Admin creation and never migrates or seeds the database. Deploy with `vercel deploy --prod --yes` after linking the project.

Atlas must permit connections from the hosting platform, separately from the developer computer. Verify `/api/auth/session` returns JSON successfully before treating the hosted application as operational. Vercel outbound IPs may change; use an appropriate stable egress configuration for production. Connection failures log diagnostic categories without credentials. Startup does not call an external IP lookup service.

Hosted cookies include Secure, HttpOnly, and SameSite=Strict. Document uploads are limited to 3 MB to keep base64 JSON requests below Vercel's 4.5 MB payload ceiling. Private files, local databases, backups, and test artifacts are excluded by `.vercelignore`. GitHub auto-deploy additionally requires linking the GitHub login in the Vercel account.

## Local startup

Requires Python 3.10 or later, PyMongo, and an accessible MongoDB replica set (including Atlas). Standalone MongoDB servers are rejected because accounting and stock changes require multi-document transactions.

```powershell
cd E:\TPPL_ERP
python -m pip install -r requirements.txt
# First setup only: copy .env.example to .env and fill in your private connection.
python config.py
python server.py
```

Open http://localhost:8000. Stop with Ctrl+C. Set `MONGODB_URI` and `MONGODB_DATABASE` in `.env` or environment variables. Environment variables take precedence. Password characters in the URI must be percent-encoded (for example, `@` becomes `%40`). Never commit `.env`. `python config.py` checks connectivity without printing credentials.

For Atlas, allow the app computer's public IP under **Network Access** and give the database user read/write permissions on the configured database. TLS certificate verification remains enabled. A TLS handshake failure before authentication is a network/cluster/TLS problem; changing the password alone cannot establish that connection. See [Atlas connection troubleshooting](https://www.mongodb.com/docs/atlas/troubleshoot-connection/).

Stop the previous SQLite application before switching storage. On first MongoDB startup, if the target is empty and `data/erp.db` exists, the server migrates it automatically and verifies every copied field and uploaded-file hash before committing. A consistent SQLite backup is written under `data/backups/`. You can run the same migration explicitly with `python migrate_to_mongo.py --source data/erp.db`. It refuses to merge into a nonempty database. Repeating the same migration is safe; a changed source is not silently imported twice. Fresh installations without a SQLite file start with empty business registers and system ledger accounts.

If Atlas is unavailable, startup fails with a credential-free message. The app does not silently fall back to SQLite. The original SQLite file and backups remain available for rollback; they are not kept synchronized after MongoDB takes over.

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

MongoDB collections hold business records, users, sessions, and uploaded document bytes. Keep credentials and backups outside Git, and configure MongoDB/Atlas backups for the active database. The old `data/erp.db` is only a migration source/backup, not the active database after switching. Inventory quantities are whole stock units; unit prices and sales totals exclude tax. Dashboard inventory value uses listed price and is not accounting inventory valuation.

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

Uploaded documents are stored as MongoDB binary fields and downloaded through authenticated, job-authorized endpoints. Supported files are PDF, PNG/JPEG, TXT/CSV, DWG/DXF, STEP/STP, DOCX, and XLSX, up to 3 MB each. Files are downloaded rather than rendered inline. TC validation checks attachment presence and a reference, not the technical authenticity of certificate contents.

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

Tests require a dedicated MongoDB replica set. By default they connect to `mongodb://127.0.0.1:27018/?replicaSet=tppl-test`; override with `MONGODB_TEST_URI`. Tests never read the Atlas credentials from `.env`. Each test suite creates and removes a uniquely named `tppl_test_*` database. They verify purchase receipt, duplicate prevention, material issue, job completion, invoices, precision, payments, balanced postings, rollback, migration, persistence, and XML structure. Additional real-MongoDB tests cover competing stock deductions and receipts, binary/password migration, unique indexes, and refusing to overwrite existing targets.

To start a local test replica set with Docker:

```powershell
docker run -d --name tppl-test-mongo -p 127.0.0.1:27018:27018 mongo:8.0 --replSet tppl-test --bind_ip_all --port 27018
docker exec tppl-test-mongo mongosh --port 27018 --eval 'rs.initiate({_id:"tppl-test",members:[{_id:0,host:"127.0.0.1:27018"}]})'
```

Wait for the node to become primary before running tests. GitHub Actions starts its own isolated MongoDB replica set.

Department tests additionally cover both job routes, prohibited actions, document access, TC enforcement, partial stock issue, stale versions, revision requests, disabled users, cross-site request rejection, and data filtering.

Browser tests also require Playwright and its Chromium browser. Run `python test_browser.py` for an isolated finance workflow and `python test_browser.py browser-workflow.cjs` for the six-department manufacturing flow. Both use the test replica set, disposable databases, and test-only accounts. `node browser-check.cjs` runs read-only checks of the local app with an existing Admin account supplied through `ERP_USER` and `ERP_PASSWORD`. If Playwright is outside this project, set `PLAYWRIGHT_MODULE` to its installed module path. Screenshots and a sample invoice PDF are written under `test-results/`.

## MongoDB implementation

`storage.py` uses native PyMongo operations, not an SQL compatibility layer. `with_transaction()` retries transient conflicts and commits before HTTP success is returned. Unique indexes protect ledger names, usernames, SKUs, and journal sources; integer counters preserve existing user-facing IDs. The conversion keeps all earlier accounting, authorization, and manufacturing rules. See [PyMongo transactions](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/) and [connection options](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-options/).

Repository: https://github.com/sudipghosh1728/TPPL_ERP. Local databases, user credentials/sessions, uploaded documents, backups, logs, and test output are excluded from version control.


## Independent Store operations

Store and Admin can use **Store operations** for inbound receipts (GRN) and outbound material issues / delivery challans (DC). No job, purchase order, department approval, or manufacturing module is required. Save a draft to edit later, or post directly to apply the stock movement. Posting is atomic, rejects insufficient stock and duplicate material lines, and preserves the material/company details on the document. Repeated API submissions with the same request ID do not issue twice.

Drafts can be modified or cancelled. Posted documents cannot be edited: cancellation requires a reason and reverses the quantities with a new movement. An inbound receipt cannot be reversed if insufficient stock remains. Document versions reject stale edits. Existing requirement-linked issues no longer require Fabrication approval, but retain quantity, stock, completed-job and explicitly requested TC checks.

The Store inventory page displays opening, inbound, total stock, consumed/issued, and available quantities **per material**. Totals reconcile stock movements, including reversals. Consumed/issued includes job issues and sales as well as independent Store issues. Quantities currently use whole stock units.

Challan fields include recipient/supplier and address, order reference/date, vehicle, transporter, LR/IR references and dates, HSN, units, line remarks, declared values, CGST/SGST or IGST, and general remarks. Print / Save PDF produces a delivery record; it does not post a financial invoice or generate a government e-way bill. Enter an externally generated 12-digit e-way bill number before or after posting. Cancelling a Store record does not cancel an official e-way bill. Official generation requires the [e-way bill portal or its authorised API](https://docs.ewaybillgst.gov.in/html/faq_new.html).

Verification: `python -m unittest test_store -v` and `python test_browser.py browser-store.cjs`. All test documents use a disposable local database. The new MongoDB `store_documents` collection must be provisioned via `MongoStore.prepare()` before hosting a new release. `.env`, real business records, backups and uploaded documents remain excluded from GitHub and deployment uploads.


### Store and Accounts workspaces

Store now includes linked returns inward/outward, physical stock counts (including zero), and consumption/production stock journals. Drafts do not change stock; posting and reversals are atomic. A count must still match the book quantity captured when it was entered. Returns cannot exceed the original voucher's unreturned quantity; linked returns must be cancelled before cancelling the original voucher.

Click a material in Inventory for its master details and dated stock history. The stock balance table shows outbound and last movement date. Inbound is net of supplier returns; outbound is net issues/sales after returns inward; counts and production journals appear under adjustments. Materials without movements show no movement date. Stock reports provide running quantity balances, date filters, reorder alerts and CSV exports.

Accounts includes Contra transfers between cash/bank ledgers, credit/debit allowances against unpaid invoices/received bills, manual bank clearance, and P&L, balance sheet, trial balance, day book and outstanding reports with CSV export. Financial notes do not move stock; physical returns are separate Store documents. Notes cannot exceed unpaid balances. Paid-document refunds and statutory GST credit/debit notes are not implemented. P&L uses posted income and expenses; purchases are expensed and closing-stock valuation is not automatic. The balance sheet is based on posted ledgers only. Outstanding is a current-position report, while the balance sheet and trial balance use the end date.

This is not yet full TallyPrime parity. Multiple warehouse balances/transfers for the same SKU, batches/expiry tracking, fractional stock units, automated inventory costing/COGS, GST filing, government e-invoice/e-way-bill generation, bank feeds and complete Tally data migration remain separate work. Do not describe these as supported based on the voucher screens.

Additional checks: `python -m unittest discover -v` and `python test_browser.py browser-vouchers.cjs`. All tests use disposable local MongoDB databases; they do not post test vouchers to the company database.


### Daily Store sheet, search and private catalogue import

Store and Admin have **Daily in / out** (`#dailystore`) and **Search Store** (`#storesearch`). The daily sheet supports date/warehouse filters, material search, only-active rows and CSV export. It reconciles opening + inward - outward + count adjustments = closing, with a separate available-now column. Consumption/production journals contribute to inward/outward; physical-count differences stay under adjustments. Returns and cancellation reversals remain visible. Quantities in different units are never added into a misleading grand total.

Store search covers materials, Store vouchers and their supplier invoice/challan references, plus read-only sales invoices and received supplier bills. The Store invoice projection deliberately excludes bank details, settlements and account ledgers. Accounts retains financial posting permissions.

`store_catalog.py <private-json-path>` previews material-name imports; `--apply` imports them. Input rows contain `row`, `name` and optional `source_values`. Existing exact names or import SKUs are retained without changing stock. New names have unconfirmed quantities and units, and cannot be received/issued/invoiced until Store or Admin confirms a stock unit, opening quantity and date. A confirmation writes one dated opening movement. Repeat imports do not create duplicates. Keep source documents, extracted JSON and backups under ignored `data/` or `test-results/`, never under `public/` or in commits. Incomplete or ambiguous historical sheets must not be treated as current verified balances.

Browser verification: set `ERP_TEST_CATALOG=1`, then run `python test_browser.py browser-store-daily.cjs` against the disposable test replica set.
