@echo off
set NAME=farmvillagers_0.01a

REM remember to activate the venv first (Scripts\activate)

:main
call :pyInstaller
echo.
pause>NUL
exit

:pyInstaller
echo [+] Starting pyInstaller...
pyinstaller ^
 --onedir ^
 --console ^
 --noupx ^
 --noconfirm ^
 --paths ..\. ^
 --add-data "..\\..\\patched;patched" ^
 --add-data "..\\..\\templates;templates" ^
 --add-data "..\\..\\villages;villages" ^
 --add-data "..\\..\\xml;xml" ^
 --add-data "..\\..\\embeds;embeds" ^
 --add-data "..\\..\\assethash;assethash" ^
 --workpath ".\\work" ^
 --distpath ".\\dist" ^
 --specpath ".\\spec" ^
 --contents-directory "bundle" ^
 --hidden-import cpyamf ^
 --hidden-import pyamf.amf0 ^
 --hidden-import pyamf.amf3 ^
 --icon=..\icon.ico ^
 --name %NAME% ..\server.py
echo [+] pyInstaller Done.
EXIT /B 0
