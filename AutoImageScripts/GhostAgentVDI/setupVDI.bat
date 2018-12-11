REM Mapping Network Drives
echo Mapping Network Drives
net use * /del /y
net use \\cn-sha-rdfs01 Welcome@2018 /user:ni\nishrfsts /persistent:yes
net use \\cn-sha-argo Welcome@2018 /user:ni\nishrfsts  /persistent:yes
net use \\cn-sha-argo\NISoftwarePrerelease Welcome@2018 /user:ni\nishrfsts  /persistent:yes

python GhostAgent.py