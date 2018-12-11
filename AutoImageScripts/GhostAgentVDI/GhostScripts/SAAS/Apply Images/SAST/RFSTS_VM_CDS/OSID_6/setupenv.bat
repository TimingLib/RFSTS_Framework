REM When target image is normal image, this script should be shipped with the 'clone' step in 'ghost console'.
REM When target image is generic image, client machine_name will copy this file from rdfs01 server via registry.
REM This script will first build network env, then download from file server all necessary files it need to build env.
REM And last, it will call boot.bat via call directly or write command into registry.



@echo off
REM renew IP
ipconfig /renew

set workdir="%~dp0"
if defined PROGRAMFILES set workdir="%PROGRAMFILES%\Symantec\Ghost\INCOMING"
if defined PROGRAMFILES(X86) set workdir="%PROGRAMFILES(X86)%\Symantec\Ghost\INCOMING"
if (%1)==() (GOTO SETUP_DEFAULTWORKROOT) else if (%1)==("") (GOTO SETUP_DEFAULTWORKROOT)
set workdir=%1
:SETUP_DEFAULTWORKROOT
cd /d %workdir%
echo "chdir to " %cd%

REM Wait for the network started
echo delay 2 min to ensure network started
ping 127.0.0.1 -n 120 -w 1000 >nul

echo Deleting previously mapped drives (if they exist)
net use S: /delete

REM Mapping Network Drives
echo Mapping Network Drives
net use S: /persistent:no /user:apac\testfarm \\cn-sha-rdfs01\RD welcome

REM copy files from rdfs01
for %%f in (boot.bat MAPDRIVES.bat BootScript.pl StepClass.pm GhostNotifyEmail.py take_snapshot.bat TakeSnapshot.py vipm_installer.py installNextGenProduct.py) Do (
	echo copying "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\INCOMING\%%f"
	copy /V /Y /Z "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\INCOMING\%%f" %workdir%
)

REM code for copying script.ini from rdfs01 will be appended by GhostAgent.py
REM the new script.ini file will be placed under "Apply Images"/[GroupName]/[Machine Name]/"OS_ID"[OSID]/script.ini
REM when cloning a new system, this is the only one needs to be transfered to the ghosted.
copy /V /Y /Z "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\APPDATA\Apply Images\SAST\RFSTS_VM_CDS\OSID_6\script.ini" .

REM add notification sentense to boot script.
echo set /p GHOST_STATUS=^<ghostStatus.log >> boot.bat
echo "C:\Python26\python.exe" "nicu\notify.py" -t GhostAgent -e GhostClient --status "%%GHOST_STATUS%%" RFSTS_VM_CDS >> boot.bat

echo Start to run boot.bat
reg ADD HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /f /v BOOT_RESTART /t REG_SZ /d "cmd /S /C \"\"%workdir:~1,-1%\boot.bat\" \""C:\Incoming"\"\""
shutdown /f /r /t 10



