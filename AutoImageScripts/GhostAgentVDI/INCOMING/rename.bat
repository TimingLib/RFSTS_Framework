@echo off
IF [%~1] == [] goto InvalidPara
echo "Rename the computer name from %COMPUTERNAME% to %1"
wmic computersystem where name="%COMPUTERNAME%" call rename name="%~1"
goto End
:InvalidPara
echo "Invalidate number of parameters."
:End