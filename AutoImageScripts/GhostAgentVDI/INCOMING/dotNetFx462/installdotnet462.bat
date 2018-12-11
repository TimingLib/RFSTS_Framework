@echo off

if exist net462.flag (
  echo dotnetfx462 already installed
  goto :eof
)

echo install dotnetfx462
echo > net462.flag
"\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\dotNetFx462\NDP462-KB3151800-x86-x64-AllOS-ENU.exe" /q /log %temp%/dotNetFx462log.htm
echo delay 1 min to ensure reboot completes during .NET 4.6.2 installation.
ping 127.0.0.1 -n 60 -w 1000 >nul
goto :eof
