# HR, attendance and project responsibility

Admin creates accounts in **Users & departments**, including QC, Maintenance and HR. Employees sign in through `/user`; Admin uses `/admin`. The workspace asks each employee to complete their name, phone, email, blood group, birth date, plant, assigned department and PNG/JPEG photo. Marital status, address and emergency contact are optional. Only Admin changes account departments. Employee personal details and pay records are restricted to the employee, HR and Admin; Design receives a planning directory with names, departments and extended-leave availability.

The plant selector lists Talawade, Solu, Chakan and Khandala. Existing profiles without a valid plant are prompted to complete it; no plant is guessed. HR/Admin can filter the employee directory by plant, including **Plant not selected**, and edit a record to correct its plant. Design receives the plant in its planning directory.

The sidebar uses the employee photo in a circle. Updating a photo replaces the `photo` value in the same employee profile record; previous photo versions are not retained by the application. Database backup retention is separate from the current record. The database-status card is removed for all roles.

## Project assignments

Open a plant project and use **Assign a person** as Design or Admin. Assign one responsible person per department, including QC. The server checks the assigned employee before QC decisions, inspection reports, production actions and material issue. Admin retains override access. Unassigned projects remain department queues. Projects, Customer POs and Customers have separate workspace entries.

An approved leave request spanning more than five calendar days opens the absent QC employee's projects to other active QC employees during the leave dates. The original assignment stays recorded. **Resume work** closes the leave early and restores exclusive approval to the original employee; access also restores after the approved end date. Merely filing a leave request does not open QC coverage. Previously completed jobs retain their earlier workflow.

Every department can raise a work/handoff or rework request to another department on an active plant project. Requests retain their origin, target, type and notes and must pass QC (or Admin override) before starting. Only one handoff waits for QC at a time. Approving a Machining request adds machining to a fabrication-only route and requires machining completion again. Completed projects remain closed.

## Attendance

HR or Admin must set accurate latitude/longitude for the attendance point at each of the four plants. No production GPS pins are guessed or prefilled.

Employees select their actual working shift and start check-in **before 10:00 AM for Regular shift** or **before 8:00 PM for Night shift**, in Asia/Kolkata time. The exact cutoff is closed; verification started earlier can finish after it. Shift is stored in attendance and included in HR reports and exports. One attendance record is kept per employee per date; changing its shift requires HR-approved regularization. Checkout remains available the next day for night shifts, and an open previous attendance must be checked out before starting another. Night-shift regularization supports next-day checkout. The page requests device location, checks approximately every 50 seconds, and must remain visible for more than 30 minutes. The server checks elapsed time. The reported position plus its accuracy radius must fit inside the 30 metre boundary. Accuracy above 30 metres, leaving the boundary, or a gap above two minutes interrupts verification. Each accepted sample replaces a one-use nonce. Location tracking ends on confirmation or error. Raw travel history is not stored: attendance keeps elapsed time and the last distance/accuracy measurement.

This is browser-reported location. A website cannot guarantee cellular-only positioning, prevent location spoofing, or reliably verify presence while the phone browser is suspended. Use precise location on a phone and keep the app visible. Late arrival, poor GPS and missed attendance require an employee regularization request reviewed by HR/Admin. Checkout is allowed at any time after confirmed or regularized check-in, including the following day.

## Payroll

HR/Admin can configure Monthly or Daily salary structures: base rate, monthly allowances/deductions, overtime hourly rate and effective date. Payroll drafts record reviewed working days, payable days, overtime and additional deductions. Monthly base pay is prorated by payable/working days; daily base pay uses daily rate times payable days. Amounts are stored in paise. Drafts can be approved or voided. Approved payroll can be marked paid with a payment reference. Employees can view and print their own payslips. Attendance export supports the payroll review.

Payroll deliberately requires reviewed payable days and deductions. Company-specific holidays, overtime entitlement, leave accrual, tax/PF/ESI calculation and statutory filings are not automatically inferred. Bank transfers and general-ledger posting are not performed by marking a payslip paid. Configure and verify the company's payroll policy before using the register for actual payroll.

## In-application dispatch reminders

Notifications lists assigned unfinished projects due within two days or overdue. The header shows unread deadline reminders. Design and the current department's responsible employees receive them; Admin sees every reminder. Approved extended QC leave opens reminders to other QC employees. Completed or rescheduled projects disappear automatically when no longer due. Mark read is stored for each employee in MongoDB and persists across devices. New daily reminders appear while the project remains due. The feed refreshes every 15 seconds while the application is visible. Email, SMS gateways and paid messaging accounts are not required. The web application does not issue background phone push notifications when closed.

## Release checks

Run `python -m unittest discover -v`, `python test_browser.py browser-hr.cjs` and `python test_browser.py browser-projects.cjs` using the dedicated local replica set. Tests never use Atlas company data. Before release, run `MongoStore.prepare()` against the intended Atlas database to create collections/indexes only. The production build versions ERP script/style URLs by content hash and disables entry-page caching so the live interface receives updated department options.
