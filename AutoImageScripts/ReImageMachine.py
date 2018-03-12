import sys,getopt,time,os,glob
sys.path.append(r'c:\PerforceRoot\sa\ss\TSTools\tstools\export\2.0\2.0.5b1\apis\python')
from tstools.constants import *
from tstools.remote import Remote

def main(argv):

    #Initializing all the required variables
    machineName = ''
    machineIP = ''
    shouldReImage = ''
    imageName = ''
    jenkinsURL = ''
    statusMessage = ''
    statusCode = 0
    
    #Obtaining the arguments passed
    try:
        opts, args = getopt.getopt(argv,"h",["machineName=","machineIP=","shouldReImage=","imageName=","jenkinsURL=","help"])
    except getopt.GetoptError:
        print 'Usage: ReImageMachine.py --machineName <MACHINENAME> --machineIP <IPaddress> --shouldReImage <true OR false> --imageName <NAMEOFIMAGE> --jenkinsURL <JENKINSURL>'
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h","--help"):
            print 'Usage: ReImageMachine.py --machineName <MACHINENAME> --machineIP <IPaddress> --shouldReImage <true OR false> --imageName <NAMEOFIMAGE> --jenkinsURL <JENKINSURL>'
            sys.exit(0)
        elif opt == '--shouldReImage':
            shouldReImage = arg
            if shouldReImage.lower() not in ("false","true"):
                print r'Invalid value for shouldReImage.It should be either "true" or "false".'
                sys.exit(0)
            elif shouldReImage.lower() == 'false':
                print '\t-----------------------------------------------------------\n\n\t\t\tReImage process disabled\n\n\t-----------------------------------------------------------'
                sys.exit(0)
        elif opt == '--jenkinsURL':
            jenkinsURL = arg                
        elif opt == '--machineName':
            machineName = arg
        elif opt == '--machineIP':
            machineIP = arg
        elif opt == '--imageName':
            imageName = arg
    if shouldReImage.lower() == 'true' and (machineName == '' or imageName == ''):
        print 'Missing Argument(s)..\nUsage: ReImageMachine.py --machineName <MACHINENAME> --machineIP <IPaddress> --shouldReImage <true OR false> --imageName <NAMEOFIMAGE> --jenkinsURL <JENKINSURL>'
        sys.exit(0)
        
    #Check if Image exists
    imagePath = '\\\\de-dre-fs1.emea.corp.natinst.com\\Imaging$\\Ghost\\'
    imageNames = [os.path.basename(x) for x in glob.glob(imagePath + '*.gho')]
    if imageName not in imageNames:
         print time.strftime("%d/%b/%Y %I:%M%p") + '\tRequested image is not available at ' + imagePath + '\n'
         sys.exit(1)
    
    jenkinsCLIPath = r'java -jar "C:\TestSuiteDeviceData\jenkins-cli.jar" -s ' + jenkinsURL
    
    #Creating instance of "Remote" object    
    print time.strftime("%d/%b/%Y %I:%M%p")+'\tTry connection with host name: <' + machineName + '>'
    TestMachine = Remote(machineName)
    
    # First try connection with host name, second try with IPaddress
    commnd = r'echo.'
    try:
        (statusMessage,statusCode) = TestMachine.batch_script(commnd)
    except:
        print time.strftime("%d/%b/%Y %I:%M%p")+'\tTry connection with IPaddress: <' + machineIP + '>'
        TestMachine = Remote(machineIP)
        try:
            (statusMessage,statusCode) = TestMachine.batch_script(commnd)
        except:
            print time.strftime("%d/%b/%Y %I:%M%p")+'\tConnection failed!!!'
            sys.exit(1)
    
    #Writing image name to D:\currentImageName.txt
    commnd = r'echo ' + imageName + r' > D:\currentImageName.txt'
    (statusMessage,statusCode) = TestMachine.batch_script(commnd)
    print 'Write Image Name Status: ' + statusMessage
    
    #Calling the ReImage Command
    print time.strftime("%d/%b/%Y %I:%M%p")+'\tTriggering the Re-Imaging process..'
    commnd = r'D:\auto_win_reimage.cmd'
    (statusMessage,statusCode) = TestMachine.execute(commnd,imageName)
    if statusCode == 0:
        commnd = jenkinsCLIPath+' wait-node-offline '+machineName
        os.system(commnd)
        print time.strftime("%d/%b/%Y %I:%M%p")+'\tRe-Imaging process started..'
        commnd = jenkinsCLIPath+' wait-node-online '+machineName
        os.system(commnd)
        print time.strftime("%d/%b/%Y %I:%M%p")+'\tRe-Imaging process Complete..'
    else:
        print 'Error while triggering Re-Image process..\n'+statusMessage
    sys.exit(0)
    
if __name__ == "__main__":
    main(sys.argv[1:])