@echo off

call :enable_update_service

if exist net40.flag (
  echo dotnetfx40 already installed
  goto :eof
)

echo install dotnetfx40
echo > net40.flag
"\\cn-sha-rdfs01\RD\SAST\Installer_Services\Tools\Installer Tools\dotNetFx40\dotNetFx40_Full_x86_x64.exe" /q /log %temp%/dotNetFx40log.htm
echo delay 1 min to ensure reboot completes during .NET 4.0 installation.
ping 127.0.0.1 -n 60 -w 1000 >nul
goto :eof

::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::
:: enable Update Service on Windows 8
::
:enable_update_service
    if exist "%SystemRoot%\system32\systeminfo.exe" (
        systeminfo | findstr /C:"OS Name" | findstr /C:"Windows 8" > nul
        if %ERRORLEVEL% == 0 (
            sc config wuauserv start= auto
            sc start wuauserv
        )
    )
exit /b 0