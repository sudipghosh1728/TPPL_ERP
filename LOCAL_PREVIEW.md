# TPPL and GREY one local preview

This isolated preview is for local review. Production deployment was authorized on 13 October 2026; future changes still require an explicit publishing instruction.

On this configured workstation, start both the local database and preview with `pwsh -File .\start-local-preview.ps1`. It opens no browser and performs no deployment. Alternatively, start the dedicated MongoDB replica set on port 27018, then run:

```powershell
python prepare_website.py
python local_preview.py --port 8001
```

Open http://localhost:8001/ for the corporate site, `/login.html` for the portal chooser, `/admin` for Admin or `/user` for departments. This uses only the local `grey_plants_preview` database. The preview never starts the email worker and does not change Atlas records.

Local demo usernames: `preview-admin`, `preview-design`, `preview-fabrication`, `preview-machining`, `preview-qc`, `preview-store`, `preview-accounts`, `preview-maintenance`, `preview-hr`. Password for these local demo accounts: `LocalPreview!2026`. The hosted application never creates these accounts.

## Plants and projects

The selector lists Unit I Talawade, Unit II Solu / Alandi, Unit III Chakan / Wasuli and Unit IV Khandala / Satara, matching the supplied TPPL website. It filters projects and Maintenance tickets. Department users can work across plants; this is not a plant security boundary. Stock balances and financial books remain shared.

New projects use `flow_version=2`; earlier jobs retain their prior workflow. Admin and Design create projects with quantity, PO dispatch date and optional revised delivery date. They upload PO/revised PO, drawings and material requirements, and delete PO files with an audit reason. Design and Store upload optional TCs. Every department can upload EWAY challans. Documents and metadata can be updated at any stage. PO/design/material revisions return active work to Design for renewed QC review. Completed-project additions do not modify the dispatch snapshot.

Design release → QC approval → Store for outstanding raw materials / paints → Fabrication and/or Machining → QC inspection → Fabrication packing → dispatch. Production handoffs require QC/Admin approval. Department work/rework requests start immediately; the receiving team submits completed work for QC/Admin approval. Open requests block final inspection and dispatch. Handoffs cannot skip outstanding material issues. Machining-only projects bypass Fabrication production but still use Fabrication packing. Admin can make an audited override with a reason.

Each project has persistent text chat, refreshed every ten seconds while open, and an audit history. Notifications refresh every fifteen seconds. QC customer inspection calls notify Admin and Design; only Admin approves a call. QC records OK or Rework, with required rework details and optional OK remarks. Outstanding call reports block final inspection. Final inspection notifies Admin, Design and Fabrication.

Any department can raise technical Maintenance requests by plant. Requests open immediately for Maintenance. Maintenance records progress and submits completed repairs to QC/Admin for verification; rejected repairs return to Open. Requesters can reopen resolved tickets.

## Dispatch ZIP and email

Dispatch requires final inspection and an uploaded EWAY challan. It atomically completes the PO and queues one immutable ZIP containing project metadata, material identities/issues, documents, approvals, inspection reports, chat and history. Unrelated business records and product prices are excluded. The ZIP is immediately downloadable. Duplicate request IDs cannot dispatch or enqueue twice.

The initial recipient is `sudipghosh1728@gmail.com`. Admin can change the destination for future dispatches under **Notifications → Change recipient**.

Local preview sends no email. To enable delivery later, configure the private SMTP settings listed in `.env.example`, explicitly enable `ARCHIVE_MAIL_ENABLED`, and run `python send_dispatch_mail.py --watch` as a separate worker. Until then, the UI reports **Queued**, not **Sent**. Uncertain deliveries become **Needs review** and are not automatically resent. A hosted release will need a provisioned worker before automatic delivery is enabled.

## Website integration and checks

The supplied `TPPL/` folder retains its own repository and is pinned as a Git submodule. After cloning, run `git submodule update --init`. The generated `public/website/` and `web-dist/` folders are ignored. The local server serves the built corporate site and existing ERP routes on one origin. The corporate login chooser does not collect passwords or create another authentication database.

For production, `python build_production.py` builds the corporate website and ERP into `web-dist/` without reading the database or copying environment files. Vercel serves `/` as the corporate homepage, `/login.html` as the portal chooser, and `/admin` and `/user` as the existing ERP. Configure `MONGODB_URI` and `MONGODB_DATABASE` privately in Vercel. The hosted API uses the existing Atlas records and never runs the local preview seed. Before a workflow upgrade, run `MongoStore.prepare()` against the intended database to provision collections and indexes without creating demo data.

Run `python -m unittest discover -v` and `python test_browser.py browser-projects.cjs` against the disposable local replica set. Tests cover all plants and routes, permissions, duplicate saves, revisions, QC approval, calls/rework, chat isolation/escaping, archive snapshots, Maintenance, plant filters and mobile layouts. Email tests use a fake transport.

Employee profiles, HR, attendance and payroll configuration are described in [HR_OPERATIONS.md](HR_OPERATIONS.md). Preview users also complete their profile on first sign-in. Use invented test details in the isolated preview.


Reminders and attendance shortcuts

Every signed-in employee has **Attendance** and **Send reminder** buttons in the header. Choose an individual or department and optionally link a project. The server determines the colour: Admin red, another department yellow, same department neutral. An open application polls every 15 seconds; each new reminder highlights the interface once for five seconds and remains in Notifications until marked read (read messages remain in history). A closed application displays unread reminders when reopened; these are in-app notifications, not device push messages. Admin/Design can mark a project urgent from its overview; the banner uses the same sender/recipient department colour rules. The 10:00 AM regular and 8:00 PM night check-in cutoffs, IST, remain unchanged.
