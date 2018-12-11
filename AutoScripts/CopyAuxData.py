'''
Description :   Python script is intent to move the calbration data for the RFPM related tests.
Author  :   Yang
Date    :   7/4
'''

#-*- coding: utf-8 -*-

from __future__ import print_function
import shutil
import stat
import os


def copy_AuxData(source, destination):
    '''
    Copy the file in the source folder to the destination folder
    '''
    if not os.path.exists(source):
        return  "******No existed source %s********" % source
    if os.path.isdir(source):
        for file in os.listdir(source):
            srcFile = os.path.join(source,file)
            tarFile = os.path.join(destination,file)
            if os.path.exists(srcFile) and os.path.exists(tarFile):
                try:
                    os.chmod(tarFile, stat.S_IWRITE)
                    os.remove(tarFile)
                    shutil.copyfile(srcFile, tarFile)
                except Exception as err:
                    raise err
            elif os.path.exists(srcFile) and not os.path.exists(tarFile):
                if not os.path.exists(destination):
                    os.makedirs(destination)
                try:
                    shutil.copyfile(srcFile, tarFile)
                except Exception as err:
                    raise err
            else:
                return "*******No existed files in %s*********" % source
    else:
        try:
            shutil.copyfile(source, destination)
        except Exception as err:
            raise err

    return "========%s has been copied successfully========" % source

def main():
    '''
    Execute the main function for the specified files. 
    '''
    testerName = os.getenv('COMPUTERNAME')
    workingDir = os.path.abspath(os.path.join(__file__, r"..\..\..\TestAssets"))
    calDataDir = os.path.join(workingDir, "CalibrationData\\")
    generalCalData = (calDataDir + testerName + r'\System Calibration')
    calDestination = r"C:\ProgramData\National Instruments\NI-5530\System Calibration"
    result = copy_AuxData(generalCalData, calDestination)
    print(result)
    userCalData = (calDataDir + testerName + r'\User-Defined Calibration')
    userCalDestination = calDataDir
    result = copy_AuxData(userCalData, userCalDestination)
    print(result)
    mswDefinition = (calDataDir + testerName + r'\Maintenance Software')
    mswDestination = r'C:\ProgramData\National Instruments\NI STS Maintenance'
    result = copy_AuxData(mswDefinition, mswDestination)
    print(result)
    limitFileDir = os.path.join(workingDir, "LimitSetting\\")
    VSTlimitFile = (limitFileDir + "TestLimitonVST.txt")
    TesterlimitFile = (limitFileDir + "TestLimitonTester.txt")
    limitFileDestinantion = os.path.join(workingDir, "..\FunctionTests\TestLimit.txt")
    if "VST" in testerName:
        result = copy_AuxData(VSTlimitFile, limitFileDestinantion)
        print(result)
    else:
        result = copy_AuxData(TesterlimitFile, limitFileDestinantion)
        print(result)
    return 0

if __name__ == '__main__':
    '''
    Move the calibration data from the hostname folder
    Move the user-define calbration data from the hostname folder
    '''
    exit(main())
