@echo off
echo Begin to take snapshot
if (%1)==() (goto Error)
C:\Python26\python.exe TakeSnapshot.py %1 >> TakeSnapshot.log 2>&1
exit

:Error
echo Error parameters >> TakeSnapshot.log 2>&1
