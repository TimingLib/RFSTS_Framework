
REM Setting up SQL client setup

echo off
echo 
eCHO 

SET SERVER="\\in-ban-fs5"

IF "%PROCESSOR_ARCHITECTURE%"=="x86" (GOTO 32BIT) else (GOTO 64BIT)

REM for 64 bit system call 64 bit installer

:64BIT

echo Installing  ODBC driver(64bit) for MySQL .....
msiexec /i  "\\in-ban-fs5\RF\Arcadia\Arcadia Dependencies\Installers\mysql-connector-odbc-5.2.5-winx64.msi" /qn

echo Installing  ODBC driver(32bit) for MySQL .....
msiexec /i  "\\in-ban-fs5\RF\Arcadia\Arcadia Dependencies\Installers\mysql-connector-odbc-5.2.5-win32.msi" /qn
echo Completed successfully
GOTO END

For 32 bit installer call 32 bit installer
:32BIT
echo Installing  ODBC driver(32bit) for MySQL .....
msiexec /i  "\\in-ban-fs5\RF\Arcadia\Arcadia Dependencies\Installers\mysql-connector-odbc-5.2.5-win32.msi" /qn
echo Completed successfully
GOTO END

:END




echo Creating a new user ODBC data source 
ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=BAN-RFMXTESTGSM;description=Use this connection to communicate with BAN-RFMXTESTGSM database;SERVER=RFMXTESTSPECAN;user=admin;password=RF@niRocks;database=rfmx_test_db"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=RFMXTESTWCDMA;description=Use this connection to communicate with RFMXTESTWCDMA database;SERVER=RFMXTESTSPECAN;user=admin;password=RF@niRocks;database=rfmx_test_db"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=RFMXTESTLTE;description=Use this connection to communicate with RFMXTESTLTE database;SERVER=RFMXTESTSPECAN;user=admin;password=RF@niRocks;database=rfmx_test_db"

 
ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=RFMXTESTDEMOD;description=Use this connection to communicate with RFMXTESTDEMOD database;SERVER=RFMXTESTDEMOD;user=admin;password=RF@niRocks;database=rfmx_test_db"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=RFMXTESTSPECAN;description=Use this connection to communicate with RFMXTESTSPECAN database;SERVER=RFMXTESTSPECAN;user=admin;password=RF@niRocks;database=rfmx_test_db"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=rfmxtest_cdma2k;description=Use this connection to communicate with rfmxtest_cdma2k database;SERVER=rfmxtest_cdma2k;user=RFmx_Tester;password=halo.2004;database=test_cdma2k"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=RFMXTESTWLAN;description=Use this connection to communicate with rfmxtest_cdma2k database;SERVER=RFMXTESTSPECAN;user=admin;password=RF@niRocks;database=rfmx_test_db"



echo Creating a new user ODBC data source 
ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=rfmxtest_evdo;description=Use this connection to communicate with rfmxtest_evdo database;SERVER=rfmxtest_evdo;user=RFmx_Tester;password=halo.2004;database=test_evdo"

ODBCCONF.exe CONFIGDSN "MYSQL ODBC 5.2 Unicode Driver" "DSN=rfmxtest_tdscdma;description=Use this connection to communicate with rfmxtest_tdscdma database;SERVER=rfmxtest_tdscdma;user=RFmx_Tester;password=halo.2004;database=test_tdscdma"

