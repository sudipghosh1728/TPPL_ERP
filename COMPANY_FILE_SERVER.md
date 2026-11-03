# Company laptop and external-drive file storage

## What this changes

The optional **Company hard-drive storage** section appears for Admin and Purchase
under Projects and in each project. It moves original PO files, drawings, TCs,
supporting documents, uploaded reports, and dispatch/deletion ZIP parts from
MongoDB to your drive. New uploads use the drive after configuration is enabled.
Downloads, report approvals, project exports and chat attachments continue through
the ERP's existing authenticated routes. Users do not receive public disk URLs.

MongoDB keeps a small storage identity, file key, size and SHA-256 digest in place
of each binary file. Project details, chat text, approvals, accounts, inventory,
employee profiles/photos and other structured records stay in MongoDB. **This
reduces Atlas space usage; it does not eliminate MongoDB or guarantee that its
512 MB tier will never fill.** You do not have to delete completed projects to
move their files. Atlas metrics may update later and include index/allocated space.

The default remains `FILE_STORAGE_MODE=mongo`. Installing this update alone moves
no existing files and does not change the production database configuration.

## 1. Set up the other Windows laptop

1. Install Python 3.12 or later with **Add Python to PATH**. The file service uses
   only Python's standard library; it needs no MongoDB password or npm install.
2. Copy `file_server.py`, `file_storage.py`, `setup-file-server.ps1`,
   `start-file-server.ps1` and this guide into a folder on that laptop.
3. Connect the external drive and give it a stable drive letter in Windows Disk
   Management. Choose a new empty folder, for example `F:\GREYone-files`.
4. Open PowerShell in the copied folder and run:

   ```powershell
   .\setup-file-server.ps1 -DriveFolder 'F:\GREYone-files'
   .\start-file-server.ps1
   ```

   Setup generates a unique drive identity and private random key in
   `.env.file-server`. Never put that file in GitHub or send its key in chat.
   If PowerShell blocks scripts, use a process-only execution-policy override:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-file-server.ps1 -DriveFolder 'F:\GREYone-files'
   powershell -NoProfile -ExecutionPolicy Bypass -File .\start-file-server.ps1
   ```

   These commands do not change the machine-wide execution policy.
5. The service listens on `127.0.0.1:8090`. Leave it running; prevent sleep while
   plugged in. Configure your laptop to restart the service after a reboot using
   Windows Task Scheduler once the connection has been tested.

The drive has a `.grey-store.json` identity marker. Preserve it in backups. If
the drive is disconnected or another disk uses its letter, writes fail instead of
silently storing files on the wrong disk. Files use hash names; original filenames
and project relationships remain in MongoDB and in project ZIP exports.

## 2. Connect over LAN or from Vercel

An Ethernet cable connects the laptop to a local network. Prefer connecting it
to the company router/switch and reserving its LAN IP. Directly connecting two
laptops only makes those devices reachable; it does not connect the other plants
or Vercel to this server.

**Current Vercel ERP:** provide a stable, authenticated HTTPS endpoint that forwards
to this service through a securely configured reverse proxy or outbound tunnel.
Vercel cannot reach `192.168.x.x`, `10.x.x.x`, `localhost`, a Windows drive letter,
or an SMB share on your LAN. The endpoint must preserve the Authorization and
X-Store-ID headers, support GET and PUT requests up to 3 MB, and must not redirect
or present an interactive login page. Do not expose Windows file sharing or
MongoDB ports to the internet. Choose and configure the network connection before
enabling remote storage; no external network service is set up by these scripts.

**LAN-hosted ERP on the same laptop:** `FILE_STORAGE_MODE=disk` can use the drive
directly. Other users connect to that ERP host. LAN hosting requires its own ERP
server/network setup; this file service does not move the Vercel application.

**ERP on a different LAN computer:** use an HTTPS reverse proxy, or configure
`FILE_SERVER_CERT` and `FILE_SERVER_KEY` in `.env.file-server`, then run:

```powershell
python file_server.py serve --root 'F:\GREYone-files' --host 0.0.0.0 --port 8090
```

The certificate must match the hostname used by the ERP. An internal CA can be
trusted with `FILE_STORAGE_CA_FILE` on a locally hosted ERP. TLS verification is
never disabled. Permit the port only for the intended clients in Windows Firewall.

## 3. Add the network server inside the ERP

1. Sign in as Admin or Purchase. Open **Projects → Company hard-drive storage →
   Manage all stored files → Add network server**.
2. Enter the server name, its HTTPS address, the storage ID and private key from
   the Windows laptop's `.env.file-server` file.
3. Click **Test & connect**. The ERP checks authentication, writes and downloads a
   small verification file, checks existing file samples where available, and
   only then saves the connection. An invalid connection leaves the previous
   settings unchanged. No existing project files move during this test.
4. New uploads now use this server. Use **Edit network server** to update its
   address or key. A blank key keeps the current key only for the same address.
   A replacement computer/drive must preserve the existing storage identity and
   files; the form prevents switching existing references to a different drive.

No Vercel environment editing or redeployment is needed for this form. The private
server key is stored in MongoDB's backend-only `_metadata` collection, never in
public settings, project exports, activity logs or API responses. Restrict direct
database access and protect database backups. The key is not displayed again in
the form. This setting takes precedence over optional environment settings.

### Optional environment configuration

If you prefer deployment-managed settings instead of the form, set these private
Vercel **Production Environment Variables** and redeploy. Copy identity/key from
the laptop's private configuration:

```dotenv
FILE_STORAGE_MODE=remote
FILE_STORAGE_URL=https://YOUR-FILE-SERVER-HOSTNAME
FILE_STORAGE_ID=IDENTITY_FROM_LAPTOP
FILE_STORAGE_TOKEN=PRIVATE_KEY_FROM_LAPTOP
```

For the ERP running on the same computer as the drive, use its private `.env`:

```dotenv
FILE_STORAGE_MODE=disk
FILE_STORAGE_ROOT=F:\GREYone-files
FILE_STORAGE_ID=IDENTITY_FROM_LAPTOP
```

Keep the existing MongoDB settings. Never point Vercel at `disk` mode: its local
filesystem is not your external drive. Preview/test databases default to isolated
storage and do not use your production file server.

## 4. Move existing files

1. Back up both the company database and the external drive before migration.
2. Sign in as Admin/Purchase → **Projects → Company hard-drive storage**.
3. Open **Manage all stored files** to check the connection and file counts, or
   open an individual project's **Manage file storage**.
4. Click **Move files to drive**. Each original is written, flushed and read back;
   only a matching byte count and SHA-256 permits replacement of the MongoDB copy.
   No project, approval or chat record is deleted.
5. Closing the dialog pauses after the current file. Reopen to resume. Failed
   transfers leave the affected MongoDB file intact; prior verified moves remain.
6. Download a PO, drawing, TC, report and project ZIP to verify operation before
   relying on the drive. Test from another user's device as well.

The transfer works one file per request. Files are immutable and deduplicated by
content; transaction retries cannot overwrite an unrelated file. Existing inline
MongoDB files and drive references can coexist during migration. A failed database
commit can leave an extra drive file, but cannot lose its MongoDB copy.

## Availability, backup and retention

- Power/internet/drive failure makes stored documents unavailable until restored.
  Metadata-only project lists continue to load, but actions needing documents may
  fail. Uploads do not silently fall back to filling MongoDB.
- Keep a second copy of the entire drive folder **and a database backup including
  file references** on a separate physical disk. MongoDB's Database Tools
  `mongodump`/`mongorestore` can back up/restore the database; protect their private
  credentials and backups. A single external disk is not a backup.
- Test restoring the drive marker, files and matching database backup together.
  Keep the same storage identity when restoring, and verify sample downloads.
- Deleting a project removes its ERP records under the existing confirmation
  flow. **Drive blobs are retained**, including old revisions and temporary ZIP
  parts. Automatic drive cleanup is deliberately not provided: shared files and
  rollback/backup references must not be accidentally erased. Securely manage
  old disk backups and retention separately; never manually remove files still
  referenced by MongoDB.
- Changing the mode back to `mongo` does not bring files back: existing references
  need the original file server. Restore server access instead of discarding its
  identity. No reverse migration is implemented in this version.
- Project deletion email still requires SMTP configuration. Offloaded mail ZIPs
  are read from the company drive when sent.
- The current 3 MB per uploaded document and existing Vercel request/time limits
  remain. Moving storage does not remove those application limits. Large whole-
  project ZIP generation still requires sufficient memory and execution time.

No subscription or cloud object-storage account is required by this implementation.
Internet access to a Vercel app still requires a working secure network route to
your laptop. A fully independent installation would additionally move the ERP
and MongoDB replica set onto company hardware; that is a separate deployment.
