@echo off

if exist net45.flag (
  echo dotnetfx45 already installed
  goto :eof
)

echo install dotnetfx45
echo > net45.flag
"\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\dotNetFx45\dotNetFx45_Full_x86_x64.exe" /q /log %temp%/dotNetFx45log.htm
echo delay 1 min to ensure reboot completes during .NET 4.5 installation.
ping 127.0.0.1 -n 60 -w 1000 >nul
goto :eof
