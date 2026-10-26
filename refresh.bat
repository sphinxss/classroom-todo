@echo off
rem Scheduled refresh entry point. Writes a log next to this file.
cd /d "%~dp0"
echo. >> refresh.log
echo ===== %DATE% %TIME% ===== >> refresh.log

rem Full list: everything outstanding, including old semesters.
call run.bat --noninteractive >> refresh.log 2>&1

rem Semester list: only items due on/after the date in semester_start.txt.
set SINCE=
if exist semester_start.txt set /p SINCE=<semester_start.txt
if defined SINCE (
  call run.bat --noninteractive --since %SINCE% --group course --html TODO.html --out TODO-semester.md >> refresh.log 2>&1
)
