REG DELETE HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v BOOT_RESTART /f

@echo off
REM renew IP
ipconfig /renew

REM Automaticall synchronize system time
echo modify registry setting the max phase correction to infinity
REG ADD HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\services\W32Time\Config /v MaxNegPhaseCorrection /t REG_DWORD /d 0xffffffff /f
REG ADD HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\services\W32Time\Config /v MaxPosPhaseCorrection /t REG_DWORD /d 0xffffffff /f
echo restore the Windows Time service on the local computer to the default settings
net stop w32time
net start w32time
echo set multiple NTP sources, synchronize time with external time source
w32tm /config /manualpeerlist:"CN-SHA-RODC1.apac.corp.natinst.com" /update
w32tm /resync
ping 127.0.0.1 -n 15 -w 1000 >nul
w32tm /resync
ping 127.0.0.1 -n 15 -w 1000 >nul
echo current system time is %date% %time%

REM Change the working directoy

REM Get working directory from parameter
if (%1)==() (GOTO DEFAULTWORKROOT) else if (%1)==("") (GOTO DEFAULTWORKROOT)
echo Changing working directory to %1
set WORKINGDIRECTORY=%~1
CD /d "%WORKINGDIRECTORY%"
GOTO MOUNTSERVER

:DEFAULTWORKROOT
REM changing working directory to default SYMANTEC incoming folder
set PROGFILES=%PROGRAMFILES%
if defined PROGRAMFILES(X86) set PROGFILES=%PROGRAMFILES(X86)%
echo Changing working directory to "%PROGFILES%\SYMANTEC\Ghost\INCOMING"
set WORKINGDIRECTORY=%PROGFILES%\SYMANTEC\Ghost\INCOMING
CD /d "%PROGFILES%\SYMANTEC\Ghost\INCOMING"

:MOUNTSERVER
REM Wait for the network started
echo delay 1 min to ensure network started
ping 127.0.0.1 -n 60 -w 1000 >nul

REM Mount cn-sha-rdfs01 first to get the Add DNS Suffix script
net use \\cn-sha-rdfs01.apac.corp.natinst.com\RD /persistent:no /user:apac\testfarm  welcome

REM Add DNS Suffix
copy "\\cn-sha-rdfs01.apac.corp.natinst.com\RD\SAST\Installer_Services\Tools\Installer Tools\DNS Suffixes.vbs" .
"DNS Suffixes.vbs"

REM Delete previously mapped drives
echo Deleting previously mapped drives (if they exist)
net use * /delete /y

REM Mapping Network Drives
echo Mapping Network Drives
net use \\cn-sha-rdfs01\RD /persistent:no /user:apac\testfarm  welcome
net use \\cn-sha-rdfs01\pacificExports /persistent:no /user:apac\testfarm  welcome
net use \\cn-sha-rdfs01\NIInstallers-Released /persistent:no /user:apac\testfarm  welcome
net use \\cn-sha-rdfs04\NIInstallers /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-rdfs04\ExportMirror /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-argo\NISoftwarePrerelease /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-argo\NISoftwareReleased /persistent:no /user:apac\testfarm welcome
net use \\nirvana\perforceExports /persistent:no /user:apac\testfarm welcome

REM kill NIUpdateService process
taskkill /F /IM "NIUpdateService.exe" > nul

REM Add a Run registry to execute boot.bat, since the dotnet4 installation may reboot the machine
REG ADD HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v GAAGENTBOOT /t REG_SZ /d "cmd /S /C \"\"%WORKINGDIRECTORY%\boot.bat\" \"%WORKINGDIRECTORY%\"\"" /f

REM Copy bat files first
copy "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\INCOMING\MSWIC\installwic.bat" "%WORKINGDIRECTORY%"
copy "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\INCOMING\dotNetFx462\installdotnet462.bat" "%WORKINGDIRECTORY%"

REM Installing MSWIC
call "%WORKINGDIRECTORY%\installwic.bat"
REM Installing .NET 4.6.2
call "%WORKINGDIRECTORY%\installdotnet462.bat"

REM Delete the Run registry to execute boot.bat, if dotnet had been installed, or it doesn't require a reboot
REG DELETE HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v GAAGENTBOOT /f

REM Restore default Intranet Security Zone but disable security for Intranet
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Zones\1" /v "Flags" /t REG_DWORD /d 219 /f

REM when installing hardware driver on XP, it will popup 'Logo Testing' dialog, which blocks the whole installation.
REM the below vb script polling the dialog 'title = Software Installation', and send Alt C to click off the dialog.
REM reference: http://superuser.com/questions/303234/automatically-accept-windows-logo-testing
REM ClickOffLogoTesting.vbs blocks process, run it in another cmd
REM Wmic OS Get Caption|Find /i "Windows XP">nul&& set win=xp
REM Wmic OS Get Caption|Find /i "Windows 7">nul&&set win=win7
REM we see this issue on xp and windows 2003 server.
copy "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\ClickOffLogoTesting.vbs" .
REM start a console, set it's title for taskkill at the end of boot.bat
start "ClickOffLogoTesting" /min cmd /c ClickOffLogoTesting.vbs

REM Disable Windows Auto Update
sc config wuauserv start= Disabled
sc stop wuauserv

REM Disable Windows Firewall
netsh firewall set opmode mode=disable

REM Disable machine hibernate (vista and above)
POWERCFG -DUPLICATESCHEME 381b4222-f694-41f0-9685-ff5bb260df2e 381b4222-f694-41f0-9685-ff5bb260aaaa & POWERCFG -CHANGENAME 381b4222-f694-41f0-9685-ff5bb260aaaa "autotest" & POWERCFG -SETACTIVE 381b4222-f694-41f0-9685-ff5bb260aaaa & POWERCFG -Change -monitor-timeout-ac 0 & POWERCFG -CHANGE -monitor-timeout-dc 0 & POWERCFG -CHANGE -disk-timeout-ac 0 & POWERCFG -CHANGE -disk-timeout-dc 0 & POWERCFG -CHANGE -standby-timeout-ac 0 & POWERCFG -CHANGE -standby-timeout-dc 0 & POWERCFG -CHANGE -hibernate-timeout-ac 0 & POWERCFG -CHANGE -hibernate-timeout-dc 0

REM Disable machine hibernate (xp)
powercfg /create autotest & powercfg /CHANGE autotest /monitor-timeout-ac 0 & powercfg /CHANGE autotest /monitor-timeout-dc 0 & powercfg /CHANGE autotest /disk-timeout-ac 0 & powercfg /CHANGE autotest /disk-timeout-dc 0 & powercfg /CHANGE autotest /standby-timeout-ac 0 & powercfg /CHANGE autotest /standby-timeout-dc 0 & powercfg /CHANGE autotest /hibernate-timeout-ac 0 & powercfg /CHANGE autotest /hibernate-timeout-dc 0 & powercfg /CHANGE autotest /processor-throttle-ac NONE & powercfg /CHANGE autotest /processor-throttle-dc NONE & powercfg /setactive autotest

echo Disable windows error reporting (vista and above)
sc stop wersvc
echo Disable windows error reporting service (vista and above)
sc config wersvc start= disabled

echo Disable windows error reporting (xp)
sc stop ERSvc
echo Disable windows error reporting service (xp)
sc config ERSvc start= disabled

REM Installing Active-Python
call "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\installPython.bat"

REM Installing Python Plugin Pymssql
xcopy /eiy \\cn-sha-rdfs01\pacificExports\SAST\Internal_Service\PythonToolchain\pymssql\export\1.0\1.0.2d1\tools\win32\pymssql C:\Python26\Lib\site-packages\

REM Workaround for MSI Directory Property PERSONALFOLDER issue, CAR 287728
if not exist "C:\Documents and Settings\LocalService\My Documents" (
    mkdir "C:\Documents and Settings\LocalService\My Documents"
)

if not exist "C:\Windows\system32\config\systemprofile\Documents" (
    mkdir "C:\Windows\system32\config\systemprofile\Documents"
)

REM Copy util and nicu before installing.
xcopy /eiy "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\util" .\util
xcopy /eiy "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\GhostAgentVDI\nicu" .\nicu

REM Execute the script.ini
echo Initiating installer script.
echo Check "%PROGFILES%\SYMANTEC\Ghost\INCOMING\scriptOut.log" for log file
echo This window will close once the script has finished executing.
echo Please wait...
perl bootscript.pl 1 >> scriptOut.log 2>&1

REM kill the console which title = 'ClickOffLogoTesting'
taskkill /F /T /FI "WINDOWTITLE eq ClickOffLogoTesting"

REM Make mapdrives script run at every reboot
REM physical test machine
REG ADD HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v MAPDRIVES /t REG_SZ /d "cmd /S /C \"\"%WORKINGDIRECTORY%\MAPDRIVES.bat\"\"" /f

REM Analyze the log file and send Notification Email
"C:\Python26\python.exe" "GhostNotifyEmail.py" >> GhostNotifyEmail.log 2>&1
"C:\Python26\python.exe" "\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\Bginfo\displaybginfo.py"

