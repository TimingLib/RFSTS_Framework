@echo off

if exist mswic.flag (
  echo microsoft WIC already installed
  goto exits
)

if /i "%PROCESSOR_IDENTIFIER:~0,3%"=="X86" goto needinstall
goto exits

:needinstall
echo install microsoft WIC for 32bit machine
"\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\MSWIC\wic_x86_enu.exe" /quiet /norestart /log:%temp%mswic.htm
echo > mswic.flag
goto exits

:exits