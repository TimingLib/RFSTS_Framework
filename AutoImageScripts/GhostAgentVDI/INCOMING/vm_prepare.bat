@echo off
IF [%~1] == [] goto PrepVMSys
echo "Register this script as RunOnce when start"
reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce /f /v PrepVM /t REG_SZ /d C:\vm_prepare.bat
goto End
:PrepVMSys
echo "Preparing your virtual image, please DO NOT close this script."
set TargeMachineName=NISHVM-%RANDOM%
echo "1.Renaming the image as %TargeMachineName%."
wmic computersystem where name="%COMPUTERNAME%" call rename name="%TargeMachineName%"
echo "2.Restart Machine."
shutdown -r -t 0
:End

