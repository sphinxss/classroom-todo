# Google Classroom → To-Do list

This folder contains a small script that signs in to your own Google account,
reads your active Classroom courses and coursework, and writes a prioritized
`TODO.md` checklist (overdue → today → next 7 days → later).

Your data never leaves your machine: the script talks straight to Google and
writes files in this folder.

## What you need to do once (about 5 minutes)

### 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/projectcreate>.
2. Project name: `classroom-todo` (anything works) → **Create**.
3. Make sure the new project is selected in the top bar.

### 2. Enable the Classroom API

1. Go to **APIs & Services → Library**.
2. Search for **Google Classroom API** → open it → **Enable**.

### 3. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. User type: **External** → **Create**.
3. Fill in App name (`Classroom To-Do`), User support email, and Developer
   contact email → **Save and continue**.
4. On **Data access**, click **Add or remove scopes**, and add these three
   (paste each into the "Manually add scopes" box):

   ```
   https://www.googleapis.com/auth/classroom.courses.readonly
   https://www.googleapis.com/auth/classroom.coursework.me
   https://www.googleapis.com/auth/classroom.student-submissions.me.readonly
   ```

   Save, then **Save and continue** through the rest.
5. On **Test users**, click **Add users** and add the Google account you use
   for Classroom.

> While the app is in "Testing" mode only the test users you add can sign in,
> and the cached login expires after ~7 days. If that happens, delete
> `token.json` and run again.

### 4. Create the client credentials

1. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app** → name it → **Create**.
3. Click **Download JSON** on the new client.
4. Rename the downloaded file to `client_secret.json` and move it into:

   ```
   C:\Users\admin\classroom-todo\client_secret.json
   ```

   (Keep this file private — it identifies your app.)

### 5. Run it

Double-click `run.bat`, or from a terminal:

```powershell
cd C:\Users\admin\classroom-todo
.\run.bat
```

A browser window opens asking you to sign in and grant access. After that,
`TODO.md` is generated and refreshed on every run.

> First run also creates `.venv\` and installs three Google packages.

## Options

```powershell
.\run.bat --include-done        # keep completed items in the list
.\run.bat --json tasks.json    # also save the raw data
.\run.bat --since 2026-06-01   # hide items due before this date (skips old semesters)
.\run.bat --group course       # group by course instead of due urgency
.\run.bat --out "C:\path\TODO.md"
```

## Notes

- Due dates come from Classroom in UTC and are converted to your local time.
- If you are a **teacher** in a course, per-student submission state is not
  available, so those items are listed as open.
- Items with no due date appear at the bottom under "No due date".
- Re-running overwrites `TODO.md`; checkboxes you tick there are not synced
  back to Classroom (this is a read-only snapshot).
- To refresh the login later: delete `token.json` and run again.
- To revoke access: <https://myaccount.google.com/permissions>.

## Automatic daily refresh (already installed)

A Windows task named **Classroom To-Do Refresh** runs every day at **7:00 AM**
(it also catches up if the PC was asleep). It calls `refresh.bat`, which:

1. Regenerates `TODO.md` — every outstanding item, including old semesters.
2. Regenerates `TODO-semester.md` — only items due on/after the date in
   `semester_start.txt`.
3. Appends output to `refresh.log`.

To change the semester cutoff, edit `semester_start.txt` (one date,
`YYYY-MM-DD`). To pause the schedule, run in PowerShell:

```powershell
Disable-ScheduledTask -TaskName 'Classroom To-Do Refresh'
```

Re-enable with `Enable-ScheduledTask -TaskName 'Classroom To-Do Refresh'`.

If the saved login expires, the scheduled run exits quietly and logs
"Saved login is missing or expired"; open `run.bat` manually once to refresh
it.
