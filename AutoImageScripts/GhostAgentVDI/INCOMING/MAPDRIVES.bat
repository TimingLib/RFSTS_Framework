echo off

echo delay 1 min to ensure network started
echo.wscript.sleep(60000)>s.vbs
cscript //nologo s.vbs
del s.vbs

REM Delete previously mapped drives
echo Deleting previously mapped drives (if they exist)
net use * /delete /y

REM Mapping Network Drives
echo Mapping Network Drives
net use \\cn-sha-rdfs01 /persistent:no /user:apac\testfarm  welcome
net use \\cn-sha-rdfs04 /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-argo\NISoftwarePrerelease /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-argo\NISoftwareReleased /persistent:no /user:apac\testfarm welcome
net use \\argo\NISoftwarePrerelease /persistent:no /user:apac\testfarm welcome
net use \\argo\NISoftwareReleased /persistent:no /user:apac\testfarm welcome
net use \\cn-sha-argo\ni /persistent:no /user:apac\testfarm welcome
net use \\nirvana /persistent:no /user:apac\testfarm welcome
net use \\limbo /persistent:no /user:apac\testfarm welcome
net use \\2poseidon /persistent:no /user:apac\testfarm welcome

echo on
