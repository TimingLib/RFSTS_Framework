"""
This class is supposed to hold all the variables that are needed by the rest of the quick validation process
This serves as documentation for what we intend each machine to do during the daily testing and,
it is a functional way to pass these data to and from other classes.
"""

import re

FDATS_V5 = "ATS-ABRAHAM"
FDATS_ZYNQ = "FDATS-ATS9"
FDATS_K7 = "FDATS-ATS3"
FDATS_GEN3 = "FDATS-ATS7"
FDATS_COMP_A = "FPGA-QV-COMP1"
FDATS_COMP_B = "FPGA-QV-COMP2"
FDATS_COMPILE_SERVER = FDATS_COMP_A
FPGA_PERF = "FPGA-PERF1"


class MachineContext:
    def __init__ (self, machineName):
        #common default values
        self.serveraddress='localhost'
        self.username='admin'
        self.password=None
        self.numworkers=1
        self.templateLVINIPath="LabVIEW.ini"
        self.templateATSINIPath="atsEngine.ini"
        self.platformVersion = "2018"
        self.trunkVersion = re.compile("20(?P<version>\d\d)").match(self.platformVersion).group('version') + '.0'
        self.args = []

            #locale
            #currently no variance for dst or not
            #according the the windows documentation for tzutil /?
            #_dstoff will disable dst adjustments, which I don't think is necessary to compute
            #we always want those adjustments to be taken into account
        self.timezone="Central Standard Time"

        if(machineName == None):
            return
        if(machineName.lower() == FDATS_V5.lower()):
            print "Found Host - {0} - using V5 quick validation variables".format(FDATS_V5)
            #testing V5
            self.targetFamily = "V5"
            self.targetClass = "PXI-7851R"
            self.targetAddress = "RIO0"
            self.targetRoot = None
            self.targetNetworkAddress = None
            # ID Sanity
            self.sanityTestName = 'Sanity'
            # ID Quick Validation 80%
            self.quickVal80TestName = 'Quick Validation 80%'
            # ID Quick Validation 100%
            self.quickVal100TestName = 'Quick Validation 100%'

            # use 2 compile workers to speed up compiles
            # requires [configure_compile_worker] task
            self.numworkers=2

        elif(machineName.lower() == FDATS_ZYNQ.lower()):
            print "Found Host - {0} - using ZYNQ quick validation variables".format(FDATS_ZYNQ)
            #testing ZYNQ
            self.targetFamily = "ZYNQ"
            self.targetClass = "cRIO-9068"
            self.targetAddress = "RIO0"
            self.targetRoot = "Networked Computer/Device"
            self.targetNetworkAddress = "fdats-crio2"
            self.rtSoftwareInstallFilePath = self.targetFamily + "/rt_software_install_config.txt"

            # ID Sanity
            self.sanityTestName = 'Sanity'
            # ID Quick Validation 80%
            self.quickVal80TestName = 'Quick Validation 80%'
            # ID Quick Validation 100%
            self.quickVal100TestName = 'Quick Validation 100%'

            #compileserver info
            self.serveraddress=FDATS_COMPILE_SERVER
            self.username='admin'
            self.password=None

        elif(machineName.lower() == FDATS_K7.lower()):
            print "Found Host - {0} - using K7 quick validation variables".format(FDATS_K7)
            #testing K7
            self.targetFamily = "K7"
            self.targetClass = "PXIe-7975R"
            self.targetAddress = "RIO0"
            self.targetRoot = None
            self.targetNetworkAddress = None

            # ID Sanity
            self.sanityTestName = 'Sanity'
            # ID Quick Validation 80%
            self.quickVal80TestName = '80%'
            # ID Quick Validation 100%
            self.quickVal100TestName = '100%'

            #compileserver info
            self.serveraddress=FDATS_COMPILE_SERVER
            self.username='admin'
            self.password=None

        elif(machineName.lower() == FDATS_GEN3.lower()):
            print "Found Host - {0} - using GEN3 quick validation variables".format(FDATS_GEN3)
            #testing GEN3
            self.targetFamily = "GEN3"
            self.targetClass = "PXIe-5840RevA"
            self.targetAddress = "PXI1Slot2"
            self.targetRoot = None
            self.targetNetworkAddress = None

            # ID Sanity
            self.sanityTestName = 'sanity'
            # ID Quick Validation 80%
            self.quickVal80TestName = 'quickVal80'
            # ID Quick Validation 100%
            self.quickVal100TestName = 'quickVal100'

            #compileserver info
            self.serveraddress=FDATS_COMP_A
            self.username='admin'
            self.password=None

        elif(machineName.lower() == 'FDATS-ATS4'.lower()):
            print "Found Host - FDATS-ATS4 - using NATIVE_SIM quick validation variables"
            #testing NATIVE_SIM
            self.targetFamily = "NATIVE_SIM"
            self.targetClass = "PXI-7851R"
            self.targetAddress = "RIO0"
            self.targetRoot = None
            self.targetNetworkAddress = None

            # ID Sanity
            self.sanityTestName = 'sanity'
            # ID Quick Validation 80%
            self.quickVal80TestName = 'quickVal80'
            # ID Quick Validation 100%
            self.quickVal100TestName = 'quickVal100'

        elif(machineName.lower() in [FDATS_COMP_A.lower(),FDATS_COMP_B.lower()]):
            print "Found Host - {0} - using compile server variables".format(machineName.lower())

            #compileworker defaults
            self.numworkers=6
            self.serveraddress='localhost'
            self.username='admin'
            self.password=None

        elif(machineName.lower() == FPGA_PERF.lower()):
            print "Found Host - {0} - using performance testing variables".format(FPGA_PERF)
            self.templateLVINIPath = "\\\\us-aus-rtweb1\\Resources\\Scripts\\LabVIEW.ini"
        else:
            #default
            print "Unknown host - using default quick validation variables"
            return