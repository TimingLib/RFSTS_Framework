#!/usr/bin/perl

use strict;             #Strict syntax checking
use warnings;           #Show warnings
use StepClass;          #Include the Step classes
use Config::IniFiles;   #INI files
use IO::File;           #Log file
use Time::localtime;    #Time and date
BEGIN {                 #Windows registry
    require Win32::TieRegistry if $^O eq 'MSWin32';
    import Win32::TieRegistry;
}
use constant IsWin32 => ( $^O eq 'MSWin32' );
use constant IsLinux => ( $^O eq 'linux' );
use constant IsMacOS => ( ( $^O eq 'darwin' ) || ( $^O eq 'MacOS' ) );

if ( $^O ne 'MSWin32' )
{
    use vars qw ($Registry);
}

#For debugging purposes
use Carp ();            #to get a call stack
local $SIG{__WARN__} = \&Carp::cluck;;
use Data::Dumper;       #Useful for debugging, to see inside objects and structures


########################################################################################
#---------------------------------------------------------------------------------------
#       Global Definitions
#---------------------------------------------------------------------------------------
########################################################################################

my $endl             = "\n";
my $blankspace       = " ";
my $step_type_name   = "type";
my $section_steps    = "steps";
my $steps_order_list = "orderlist";
my $simulation_mode  = 0;

my $win_ini_file     = 'script.ini';
my $linux_ini_file   = '/mnt/mainboot/script.ini';
my $mac_ini_file     = '/Volumes/Storage/Testfarm/script.ini';

#get rid of these at some point. create auto-log-in class and auto-run class or something
my $Auto_Admin_Login_State_name  = "AutoAdminLoginOriginalState";
my $Auto_Admin_Login_User_name   = "AutoAdminLoginOriginalUserName";
my $Auto_Admin_Login_Domain_name = "AutoAdminLoginOriginalDomainName";
my $setttings_section_name       = "settings";
my $run_key_value_name           = 'run_key_value';

########################################################################################
#---------------------------------------------------------------------------------------
#       Main
#---------------------------------------------------------------------------------------
########################################################################################

# Open log file
my $log_file = new IO::File "Script_Log.txt", O_CREAT | O_RDWR | O_APPEND;
if (defined $log_file) {
    &log_out ("[INFO]: Log file opened succesfully.");
}
else
{
    &log_out ("[WARNING]: Unable to create or open log file.");
}
&log_out ("[INFO]: Script started.");

#Initialize step class
Step::initialize_step_class($log_file,$simulation_mode);

#run the autotests for the Step class and subclasses
if (StepClassTest::step_class_autotest ())
{
    &log_out ("[INFO]: Step class autotests passed.");               #All is OK
}
else                                                        #Trouble...
{
    print "Step class autotests failed\n";                  # Print out the tests that failed
    for my $failed_test_number (StepClassTest::failed_tests())
    {
        print "Test: " . $failed_test_number . " failed\n";
    }
}

# Open configuration INI file
my $cfg = undef;

if (IsWin32)
{
    $cfg = new Config::IniFiles( -file => $win_ini_file );
}
elsif (IsLinux)
{
    $cfg = new Config::IniFiles( -file => $linux_ini_file );
}
elsif (IsMacOS)
{
    $cfg = new Config::IniFiles( -file => $mac_ini_file );
}

if (!$cfg)
{
    &log_out ("[ERROR]: Failed to open or parse INI file\n");
    if (!(defined ($cfg)))
    {
        &log_out ("[ERROR]:" . @Config::IniFiles::errors);
    }
    die;
}

#&AutoAdminLoginSet(1);
&AutoRunOnBootEnable(1);

my @step_names = $cfg->Parameters($section_steps);          #Create an array of all the step names in the 'steps' section
my $lists = $cfg->val($section_steps, $steps_order_list);   #ordered step list string, joined by step names with ';' as SEP
my @steps_to_execute = ();                                  #This is where we'll store all the executable steps

#foreach my $step_name(@step_names)                         #for each step listed in the 'steps' section
foreach my $step_name (split('&', $lists))                  #for each step listed in the 'orderlist'
{
    &log_out ("[INFO]: Creating " . $step_name);
    $step_name =~ s/^\s+//;
    $step_name =~ s/\s+$//;
    push (@steps_to_execute, create_step($step_name));      #Create the step object and push it into the array
}

foreach my $step (@steps_to_execute)                        #for each executable step we have found
{
    #print Dumper($step);
    if ($step->enabled())                                   #If the step is enabled
    {
        disable_step($step);                                #Try to disable the step in the INI file, if the step can be disabled
        &log_out ("[INFO]: Executing step: " . $step->name());
        $step->execute();                                   #execute the step
        &log_out ("[INFO]: Finished step: " . $step->name());
        if (Step::rebooting_flag())                         #if this step requires a reboot
        {
            &log_out ("[INFO]: Waiting for reboot... sleep for 2 min");
            sleep(60 * 2);
            &log_out ("[INFO]: No reboot happen, are u make fun of me? force reboot...give you some color see see");
            &force_reboot();
            sleep(120);
            exit;
        }
        # if there's no sleep between steps, it may result in interrupted step. for
        # example, there are two steps, A and B. suppose A would result in a
        # unexpected (no sleep_until_reboot flag specified, but do lead to reboot) reboot,
        # If B starts, after A finishes, but before the reboot really happens, then B will
        # probably be interrupted. Hopefully, sleep a while here will avoid the above case.
        sleep(30);
    }
}
if (IsWin32)
{
    &script_cleanup();
}
&log_out ("[INFO]: Script is Done.");
close $log_file;
exit;

########################################################################################
#---------------------------------------------------------------------------------------
#       Subroutines
#---------------------------------------------------------------------------------------
########################################################################################

#-------------------------------------------
#       create_step (Step's name)
#-------------------------------------------
#This usesthe appropriate section of the INI file to figure out the type of the step
#and dynamically creates the step object of the right type.

sub create_step {
    my ($step_name) = @_;                                                               #The name is needed find the respective INI section
    my $new_step = Step::new_step ($cfg->val($step_name,$step_type_name),$step_name);   #The step's type is specified in the INI file
    $new_step->enabled($cfg->val($section_steps,$step_name));                           #Set the step's enabled status, also fromthe INI file
    my %the_parameters = step_parameters($step_name);                                   #read the whole INI section with the same name as the step's
    $new_step->fill_parameters(%the_parameters);                                        #pass that parameter map to the object, it'll take care of filling itself up
    #print Dumper($new_step);
    return $new_step;                                                                   #return the newly-created step
}

#-------------------------------------------
#       step_parameters (Step's name)
#-------------------------------------------
#This function knows reads the appropriate section from the INI file for the given step name,
#returns a MAP structure with all the parameters under the step's section

sub step_parameters {
    my ($step_name) = @_;
    my %parameter_map;
    my @step_parameters = $cfg->Parameters($step_name);


    foreach my $parameter(@step_parameters)
    {
        %parameter_map->{$parameter} = $cfg->val($step_name,$parameter);
        #print $parameter . " " . $parameter_map{$parameter} . "\n";
    }
    return %parameter_map;
}

#--------------------------------------------------------
# Disable the step if possible
#--------------------------------------------------------
sub disable_step {
    my ($step)=@_;
    if ($step->always_run())
    {
        return 1;
    }
    else
    {
        &write_setting($section_steps, $step->name(), 0);
    }
}

#--------------------------------------------------------
# Generic INI file setting read
#--------------------------------------------------------
sub read_setting {
    my $section = $_[0];
    my $setting = $_[1];
    my $value   = $cfg->val($section, $setting);
    return ($value);
}

#--------------------------------------------------------
# Generic INI file setting write
#--------------------------------------------------------
sub write_setting {
    my $section = $_[0];
    my $setting = $_[1];
    my $value = $_[2];
    $cfg->setval($section, $setting, $value);
    if (!($cfg->RewriteConfig))
    {
        &log_out ("[ERROR]: writing INI file");
        return 0;
    }
}

#--------------------------------------------------------
# Log to std out and file
#--------------------------------------------------------
sub log_out {
    my $log_line = "[" . ctime() . "]" . $_[0] . "\n";
    print $log_line;
    print $log_file $log_line;
}

#--------------------------------------------------------
# Log to std out and file
#--------------------------------------------------------
sub script_cleanup() {
    auto_admin_logon_cleanup();
}

#--------------------------------------------------------
# reboot
#--------------------------------------------------------
sub force_reboot() {
    my $command = '';
    if (IsWin32)
    {
        $command = 'shutdown -r -f -t 30 -c "force rebooting system in 30s. type shutdown -a on the shell to abort"';
    }
    else
    {
        $command = '/sbin/shutdown -r +1 "force rebooting system in 60s, type shutdown -c on the shell to abort"';
    }
    system($command);
}

################################################################################################
# Move this stuff to its own class later on
################################################################################################


sub auto_admin_logon_cleanup {
    &AutoRunOnBootEnable (0);   #Delete Auto-Run Key. We don't need to reboot again.
    if (!(&read_setting ("settings", $Auto_Admin_Login_State_name)))        # If autologin was Disabled, reboot to restore machine to
    {                                                                       # original state (no one is logged in)
        #&AutoAdminLoginSet(0);      #Restore AutoAdminLogin State
        #Reboot::rebootself ();
    }
}


#--------------------------------------------------------
# AutoAdminLoginEnable
#--------------------------------------------------------

sub AutoAdminLoginSet {
    if (IsWin32)
    {
        WinAutoAdminLoginSet($_[0]);
    }
    elsif (IsLinux)
    {
        LinuxAutoAdminLoginSet($_[0]);
    }
    elsif (IsMacOS)
    {
        MacAutoAdminLoginSet($_[0]);
    }
}

sub WinAutoAdminLoginSet {
    my $set = $_[0];
    my $AutoAdminLogonKeyPath = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\';
    my $AutoAdminLogonKey = '\\AutoAdminLogon';
    my $DefaultPasswordKey = '\\DefaultPassword';
    my $DefaultUserNameKey = '\\DefaultUserName';
    my $DefaultDomainNameKey = '\\DefaultDomainName';
    my $TempKey1;
    my $TempKey2;
    my $DefaultPassword=    'labview===';
    my $DefaultUserName=    'administrator';
    my $DefaultDomainName=  'localhost';
    my $TempKeyStringValue= " ";
    my $step_to_check=      $setttings_section_name;
    my $AutoAdminLogonState=0;


    if ($set)       #Set AutoAdminLogon
    {
        $TempKey1 = $Registry->{$AutoAdminLogonKeyPath};                #Point to WinLogon
        $AutoAdminLogonState= $TempKey1->{$AutoAdminLogonKey};          #Read current AutoAdminLogin value
        &write_setting ($step_to_check, $Auto_Admin_Login_State_name,$AutoAdminLogonState);     #Remember original setting in INI file

        if ($AutoAdminLogonState)                                       #If it's enabled
        {
            &log_out("[INFO]: Auto Administrator Login currently enabled. Leaving it as is.");
        }
        else                                                            #If not enabled
        {
            &log_out("[INFO]: Auto Administrator Login currently disabled. Temporarily enabling it.");

            $TempKey1->{$AutoAdminLogonKey} =1;                                                     #Enable AutoAdminLogin

            $TempKey2 = $Registry->{$AutoAdminLogonKeyPath};                                        #Look for default password key
            $TempKey2->{$DefaultPasswordKey}= $DefaultPassword;                                     #Set or create&set default password key
            &log_out("[INFO]: Set DefaultPassword key.");

            $TempKeyStringValue = ($Registry->{$AutoAdminLogonKeyPath . $DefaultUserNameKey});      #Read current Default User

            &log_out("[INFO]: DefaultUserName: " . $TempKeyStringValue);

            if ($TempKeyStringValue)                                                                #If Default User Exists
            {
                &write_setting ($step_to_check, $Auto_Admin_Login_User_name, $TempKeyStringValue);      #Remember original setting in INI file
            }
            $TempKey2 = $Registry->{$AutoAdminLogonKeyPath};
            $TempKey2->{$DefaultUserNameKey}= $DefaultUserName;                                     #Set Default User
            &log_out("[INFO]: Set DefaultUser key.");

            $TempKeyStringValue = ($Registry->{$AutoAdminLogonKeyPath . $DefaultDomainNameKey});    #Read current Default Domain
            &log_out("[INFO]: DefaultDomainName: " . $TempKeyStringValue);

            if ($TempKeyStringValue)                                                                #If Default Domain Exists
            {
                &write_setting ($step_to_check, $Auto_Admin_Login_Domain_name, $TempKeyStringValue);    #Remember original setting in INI file
            }
            $TempKey2 = $Registry->{$AutoAdminLogonKeyPath};
            $TempKey2->{$DefaultDomainNameKey}= $DefaultDomainName;                                 #Set Default Domain
            &log_out("[INFO]: Set DefaultDomain key.");
        }
    }
    else            #Restore AutoAdminLogon to its previous state
    {

        $TempKey1 = $Registry->{$AutoAdminLogonKeyPath};
        &log_out("[INFO]: Restoring Auto Administrator Login to previous state");
        $TempKey1->{$AutoAdminLogonKey} = &read_setting ($step_to_check, $Auto_Admin_Login_State_name);         #Restore original AutoAdminLogin
        $TempKey1->{$DefaultUserNameKey} = &read_setting ($step_to_check, $Auto_Admin_Login_User_name);         #Restore original User Name
        $TempKey1->{$DefaultDomainNameKey} = &read_setting ($step_to_check, $Auto_Admin_Login_Domain_name);     #Restore original Domain Name
    }
}

sub LinuxAutoAdminLoginSet {

}

sub MacAutoAdminLoginSet {

}

#--------------------------------------------------------
# AutoRunOnBootEnable
#
# Enables or disables launches script at boot
#--------------------------------------------------------
sub AutoRunOnBootEnable {
    if (IsWin32)
    {
        WinAutoRunOnBootEnable($_[0]);
    }
    elsif (IsLinux)
    {
        LinuxAutoRunOnBootEnable($_[0]);
    }
    elsif (IsMacOS)
    {
        MacAutoRunOnBootEnable($_[0]);
    }
}

# Enables or disables registry key that launches the script at boot
sub WinAutoRunOnBootEnable {
    my $enable = $_[0];
    my $step_to_check=      $setttings_section_name;
    my $RunKeyValue = &read_setting($step_to_check, $run_key_value_name);
    my $RunKeyPath = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\';
    my $RunKey = '\\BootScript';
    my $TempKey1;

    if ($enable)
    {
        &log_out("[INFO]: Checking registry option to continue after reboot");
        if (!($Registry->{$RunKeyPath . $RunKey}))
        {
            &log_out("[INFO]: Setting registry option to continue after reboot");
            $TempKey1 = $Registry->{$RunKeyPath};
            #$TempKey1->{$RunKey}= $RunKeyValue;
            $TempKey1->{$RunKey} = [$RunKeyValue, "REG_EXPAND_SZ"];
            &log_out ("[INFO]: Succesfully created Auto-Run registry key");
        }
    }
    else
    {
        if (($Registry->{$RunKeyPath . $RunKey}))
        {
            $TempKey1= delete $Registry->{$RunKeyPath . $RunKey};
            &log_out ("[INFO]: Deleted Auto-Run registry key");
        }
    }

}

sub LinuxAutoRunOnBootEnable {
	my $_user = @ARGV ? $ARGV[0] : 'lvtest';
    my $_home = exists $ENV{'HOME'} ? $ENV{'HOME'} : '/home/'.$_user;
    if (  $_home eq '/root' ) {
        $_home = '/home/'.$_user;
    }
    my $_xdg_config_home = $_home . '/.config';
    if (exists $ENV{'XDG_CONFIG_HOME'})
    {
        $_xdg_config_home = $ENV{'XDG_CONFIG_HOME'};
    }

    my $_xdg_user_autostart = $_xdg_config_home . "/autostart";

    #get the filename of an autostart (.desktop) file
    my $_getfilename = sub {
        my $name = $_[0];
        return $_xdg_user_autostart . "/" . $name . '.desktop';
    };

    #add a new autostart entry
    my $_add = sub {
        my $name = $_[0];
        my $application = $_[1];
        my $desktop_entry = "[Desktop Entry]\n";
        $desktop_entry .= "Type=Application\n";
        $desktop_entry .= "Exec=" . $application . "\n";
        $desktop_entry .= "Hidden=false\n";
        #$desktop_entry .= "X-GNOME-Autostart-enabled=true\n";
        $desktop_entry .= "Name=" . $name ."\n";
        $desktop_entry .= "Comment=" . "Ghost BootScript for Linux/Mac\n";

        my $outfile = $_getfilename->($name);

        open(MYFILE, ">> $outfile") || die "problem opening $outfile\n";
        print MYFILE "$desktop_entry";
        close(MYFILE);
    };

    #check if an autostart entry exists
    my $_exists = sub {
        my $name = $_[0];
        return 1 if (-e $_getfilename->($name));
    };

    #delete an autostart entry
    my $_remove = sub {
        my $name = $_[0];
        return unlink($_getfilename->($name));
    };

    my $enable        = $_[0];
    my $step_to_check = $setttings_section_name;
    my $application   = &read_setting($step_to_check, $run_key_value_name);
    my $appname       = 'BootScript';

    if ($enable)
    {
        $_remove->($appname);
        $_add->($appname, $application);
    }
    else
    {
        $_remove->($appname);
    }
}

sub MacAutoRunOnBootEnable {

}
