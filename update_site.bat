@echo off
rem Met a jour Le Signal : recharge les donnees Bloomberg (terminal ouvert requis)
rem puis reconstruit web/data.json. Double-cliquable une fois par mois.
cd /d "%~dp0"
echo [1/2] Pull Bloomberg...
python research_bbg\pull.py
if errorlevel 1 goto :err
echo [2/2] Rebuild data.json...
set PYTHONPATH=research_bbg
python scripts\build_signal_page.py
if errorlevel 1 goto :err
echo.
echo OK - data.json a jour. Commit + push pour publier le site.
pause
exit /b 0
:err
echo ECHEC - voir le message ci-dessus (terminal Bloomberg ouvert ?).
pause
exit /b 1
