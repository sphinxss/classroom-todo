@echo off
rem Scheduled refresh entry point. Writes a log next to this file.
cd /d "%~dp0"
echo. >> refresh.log
echo ===== %DATE% %TIME% ===== >> refresh.log

rem Full list: everything outstanding, including old semesters.
call run.bat --noninteractive >> refresh.log 2>&1

rem Semester list + the published page.
set SINCE=
if exist semester_start.txt set /p SINCE=<semester_start.txt
if defined SINCE (
  call run.bat --noninteractive --since %SINCE% --group course --html index.html --out TODO-semester.md >> refresh.log 2>&1
)

rem Publish to GitHub Pages (only index.html is committed).
if exist .git (
  git add index.html
  git diff --cached --quiet
  if errorlevel 1 (
    git commit -m "Update %DATE% %TIME%" --quiet >> refresh.log 2>&1
    git push origin main >> refresh.log 2>&1
  )
)
