
#--------------
#class Step
#--------------
package Step;
{
    use strict;
    use warnings;
    use Time::localtime;    #Time and date

    #-------------------------------------------
    #Constructor
    #-------------------------------------------

    sub new {
        my ($class,$name) = @_;
        my $self = {
            _name  => $name,                #Name of the step
            _type  => $class,               #Type of the step (class)
            _enabled => 0,                  #Whether the step will run or not
            _always_run =>0                 #True if the step will not disable itself after running
        };
        bless $self, $class;
        return $self;
    }

    #-------------------------------------------
    #Accesor Methods
    #-------------------------------------------

    #accessor method for step's enabled status
    sub enabled {
        my ( $self, $enabled ) = @_;
        $self->{_enabled} = $enabled if defined($enabled);
        return $self->{_enabled};
    }

    #accessor method for step's name
    sub name {
        my ( $self, $name ) = @_;
        $self->{_name} = $name if defined($name);
        return $self->{_name};
    }

    #accessor method for step's type
    sub type {
        my ( $self) = @_;
        return $self->{_type};
    }

    #accessor method for step's always_run flag
    sub always_run {
        my ( $self, $always_run ) = @_;
        $self->{_name} = $always_run if defined($always_run);
        return $self->{_always_run};
    }

    #-------------------------------------------
    #Member methods
    #-------------------------------------------

    #Member function to enable the step
    sub enable {
        my ( $self) = @_;
        $self->enabled(1);
    }

    #Member function to disable the step
    sub disable {
        my ($self) = @_;
        $self->enabled(0);
    }

    #Member function to print the step's type. Should be overridden
    sub print_type {
        my ($self) = @_;
        return $self->{_type};
    }

    #Member function to execute the step. Should be overridden
    sub execute {
        #Do nothing for now. Log generic info here in the future
        return;
    }

    #Member function to fill the rest of the parameters of the step
    sub fill_parameters {
        my ($self, %parameter_map)=@_;
        my @keys = keys %parameter_map;
        foreach my $key(@keys)
        {
            my $modified_key="_" . $key;
            if (!(exists $self->{$modified_key}))
            {
                print "[" . ctime() . "][ERROR]: Parameter " . $key .  " is not found in type " . type($self) . "\n";
                return 0;
            }
            else
            {
                $self->{$modified_key} = %parameter_map->{$key};
            }
        }
        return 1;
    }

    #Member function to check that all parameters are defined
    sub check_parameters {
        my ($self)=@_;
        my @keys = keys %{$self};
        foreach my $key(@keys)
        {
            if (!(defined $self->{$key}))
            {
                print "[" . ctime() . "][ERROR]: " . $key . " is undefined in type " . type($self) . "\n";
                return 1;
            }
        }
        return 0;
    }

    #Member function to print all of the object's parameters
    sub print_settings {
        my ($self)=@_;
        my @keys = keys %{$self};
        print "These are the settings for step " . name($self) . ":\n";
        print @keys;
        print "\n";
        foreach my $key(@keys)
        {
            if (defined $self->{$key})
            {
                print "[" . ctime() . "][INFO]: " . $key . "=" . $self->{$key} . "\n";
            }
            else
            {
                print "[" . ctime() . "][INFO]: " . $key . "=Undefined\n";
            }
        }
    }

    #-------------------------------------------
    #Class Globals
    #-------------------------------------------


    $Step::log_file = undef;
    $Step::simulation_mode = 0;
    $Step::rebooting=0;

    #-------------------------------------------
    #Class Methods. Can be called without an object
    #-------------------------------------------

    #Initialize Step Class
    sub initialize_step_class {
        my ($log_file, $simulation_mode) = @_;
        $Step::log_file = $log_file if defined ($log_file);
        $Step::simulation_mode = $simulation_mode if defined ($simulation_mode);;
    }

    #Log message out to file or STDOUT
    sub log_out {
        my $log_line = "[" . ctime() . "]" . $_[0] . "\n";
        print $log_line;
        if (defined $Step::log_file)
        {
            print $Step::log_file $log_line;
        }
    }

    sub rebooting_flag {
        return $Step::rebooting;
    }

    #Wrapper that allows clients to dynamically create a step, or Step sub-class object, by providing the class name
    sub new_step {
        my ($step_class,$name) = @_;

        format_class_name($step_class);
        if ($step_class->can('new'))
        {
            my $dynamically_created_step = $step_class->new ($name);
            if ($dynamically_created_step->isa('Step'))
            {
                return $dynamically_created_step;
            }
            else
            {
                return 0;
            }
        }
        else
        {
            return 0;
        }
    }

    #This function will take the string and operate on it to assure that it
    #conforms to the naming conventions of the classes that inheret from Step
    sub format_class_name {
        my ($string) = @_;
        my $original_length = length($string);          #remember the original length for future sanity check
        my @words = split (/_/,$string);                #split into string subsets, words, separated by underscores
        for my $word (@words)                           #for each of the words in the string
        {
            $word=ucfirst(lc($word));                   #make everything lower-case, then uppercase the first letter in it
        }
        $string = join ('_',@words);                    #then put all the words back together, joined by underscores
        $_[0]=$string;                                  #then replace the value directly in the reference that was passed in
        if (length ($string) == $original_length)
        {
            return 1;
        }
        return 0;
    }
}


#--------------
# class Reboot, inherits from class Step
#--------------
package Reboot;
{
    use strict;
    our @ISA = qw(Step);    # inherits from Step

    #-------------------------------------------
    #Constructor
    #-------------------------------------------

    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Step
        my $self = $class->SUPER::new($name);
        bless $self, $class;
        return $self;
    }

    #-------------------------------------------
    #Member methods
    #-------------------------------------------


    #-------------------------------------------
    # Execute. Member function to execute the step. Overrides parent's
    # execute ();
    #-------------------------------------------
    #
    sub execute {
        my ($self) = @_;
        if ($self->check_parameters())
        {
            Step::log_out ("[ERROR]: Step " . $self->name() . " has undefined parameters, check INI file.");
            return 1;
        }
        else
        {
            if ($self->enabled())
            {
                return (rebootself());
            }
            else
            {
                Step::log_out ("[ERROR]: Tried to execute a step that was marked as disabled. Step's name: " . $self->name());
                return 1;
            }
        }
    }

    sub rebootself{
        my $command = 'shutdown -r -f -t 30 -c "Rebooting System in 30s. Type shutdown -a on the shell to abort"';
        if ( $^O ne 'MSWin32' )
        {
            $command = '/sbin/shutdown -r +1 "Rebooting System in 60s. Type shutdown -c on the shell to abort"';
        }
        my $ret_val = 0;
        if (!($Step::simulation_mode))          #if not in simulation mode
        {
            $ret_val =(system ($command))/256;
        }
        if ($ret_val)
        {
                Step::log_out ("[ERROR]: Return value: ". $ret_val);
        }
        $Step::rebooting =1;
        return $ret_val;
    }
}

#--------------
# class Email, inherits from class Step
#--------------
package Email;
{
    use strict;
    our @ISA = qw(Step);    # inherits from Step

    #-------------------------------------------
    #Constructor
    #-------------------------------------------

    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Step
        my $self = $class->SUPER::new($name);
        bless $self, $class;
        return $self;
    }
}

#--------------
# class Command, inherits from class Step
#--------------
package Command;
{
    use strict;
    use File::Spec;
    our @ISA = qw(Step);    # inherits from Step
    #-------------------------------------------
    #constructor
    #-------------------------------------------

    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Step.
        my $self = $class->SUPER::new($name);
        $self->{_path}                  = "";        #executable's path
        $self->{_command}               = "";        #executable's name
        $self->{_flags}                 = "";        #executable's flags
        $self->{_sleep_until_reboot}    = 0;         #Whether we wait for someone else to reboot the machine or keep going
        bless ($self, $class);
        return $self;
    }

    #-------------------------------------------
    #Accessor methods
    #-------------------------------------------

    #Accessor method for Command's command name
    sub command {
        my ($self) = @_;
        return $self->{_command};
    }

    #Accessor method for Command's flags
    sub flags {
        my ($self,$flags) = @_;
        $self->{_flags} = $flags if defined($flags);
        return $self->{_flags};
    }

    sub sleep_until_reboot {
        my ($self) = @_;
        return $self->{_sleep_until_reboot};
    }

    #Accessor method for Command's path
    sub path {
        my ($self,$path) = @_;
        $self->{_path} = $path if defined($path);
        return $self->{_path};
    }

    #-------------------------------------------
    #Member methods
    #-------------------------------------------


    #-------------------------------------------
    # Execute. Member function to execute the step. Overrides parent's
    # execute ();
    #-------------------------------------------
    #
    sub execute {
        my ($self) = @_;
        if ($self->check_parameters())
        {
            Step::log_out ("[ERROR]: Step " . $self->{_name} . " has undefined parameters, check INI file.");
            return 1;
        }
        else
        {

            if ($self->enabled())
            {
                if ($self->sleep_until_reboot())                   #if this step will reboot the system
                {
                     $Step::rebooting =1;                          #Set the global flag for an inminent reboot
                }
                return ($self->build_and_run_command());           #call helper function to assemble the command and run it
            }
            else
            {
                Step::log_out ("[ERROR] Tried to execute a step that was marked as disabled. Step's name: " . $self->name());
                return 1;
            }
        }
    }

    #-------------------------------------------
    # Build & Execute Command
    #-------------------------------------------

    sub build_and_run_command {
        my ($self) = @_;

        my $tmppath = $self->path();
        $tmppath =~ s/^\s+//;        #Trim left space.
        $tmppath =~ s/\s+$//;        #Trim right space. The drawbacks: it can not handle the situation that a path indeed has leading and trailing spaces in its name.

        my $tmpcmd = $self->command();
        $tmpcmd =~ s/^[\\\/\ \t]+//;        #Trim left
        $tmpcmd =~ s/[\\\/\ \t]+$//;        #Trim right

        my $tmpfullcmd = '';
        if ($tmppath eq '')
        {
            $tmpfullcmd = $tmpcmd;          #Current path
        }
        else
        {
            $tmpfullcmd = File::Spec->catfile($tmppath, $tmpcmd);
        }
        $tmpfullcmd =~ s/[\\\/]+$//;        #Trim trailing forward slash and back slash
        my $command = '"' . $tmpfullcmd . '" ' . $self->flags();
        &execute_command($command);
    }

    #-------------------------------------------
    # Execute Command
    # execute_command(command);
    #-------------------------------------------

    sub execute_command {
        my ($command) = @_;
        my $ret_val = 0;

        Step::log_out ("[INFO]: Executing:". $command);

        if (!($Step::simulation_mode))          #if not in simulation mode
        {
            $ret_val =(system ($command))/256;
        }

        my @validcodes = qw / 0 4 105 194 /;      # These ret-codes are indicative of a success.
        if (!exists {map { $_ => 1 } @validcodes}->{$ret_val})
        {
            Step::log_out ("[ERROR]: Return value: ". $ret_val);
        }

        return $ret_val;
    }

}

#-------------------------------------------
# class Scripted_Copy, inherits from class Command
#-------------------------------------------
package Scripted_Copy;
{
    use strict;
    our @ISA = qw(Command);    # inherits from Command

    #constructor
    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Command.
        my $self = $class->SUPER::new($name);

        $self->{script_from_path_name} = 'script_from_path';   #Naming convetion for the parameter names
        $self->{script_to_path_name}   = 'script_to_path';     #Naming convetion for the parameter names
        $self->{_script_from_path}     = ();                   #Origin paths array
        $self->{_script_to_path}       = ();                   #Destination paths array

        bless $self, $class;
        return $self;
    }

    #-------------------------------------------
    #Accessor methods
    #-------------------------------------------

    #Accessor method to add a FROM path to the list
    sub push_from_path {
        my ($self,$new_from_path) = @_;
        push (@{$self->{'_' . $self->{script_from_path_name}}},$new_from_path);
        return;
    }

    #Accessor method to add a TO path to the list
    sub push_to_path {
        my ($self,$new_to_path) = @_;
        push (@{$self->{'_' . $self->{script_to_path_name}}},$new_to_path);
        return;
    }

    #-------------------------------------------
    #Member methods
    #-------------------------------------------

    #-------------------------------------------
    # Execute. Member function to execute the step. Overrides parent's
    # execute ();
    #$command = $command . $blankspace . $double_quote . $from_path . $double_quote . $blankspace . $double_quote . $to_path . $double_quote . $blankspace . $flags;
    #-------------------------------------------
    #
    sub execute {
        my ($self) = @_;
        my $original_flags= $self->flags();
        my $counter=0;

        foreach my $from_path (@{$self->{_script_from_path}})
        {
            $self->flags($original_flags . ' "' . $from_path . '"  "' . (@{$self->{_script_to_path}}[$counter]). '"');
            $self->SUPER::execute();
            $counter++;
        }
        return; #TODO: ADD SOME RETURN CODE HERE
    }

    #-------------------------------------------
    #Member function to fill the rest of the parameters of the step# we override the parent's call to intercept some special parameters
    #-------------------------------------------

    sub fill_parameters {
        my ($self, %parameter_map)=@_;
        my $iterator=1;

        while (                                                                         #  Loop for each pair of FROM-TO paths IF:
        (exists %parameter_map->{$self->{script_from_path_name} . '_' . $iterator}      # FROM path key exists
        &&                                                                              # AND
        (exists %parameter_map->{$self->{script_to_path_name} . '_' . $iterator}))      # TO path key exists
        &&                                                                              # AND
        ($self->{script_to_path_name})                                                  # FROM path has a value
        &&                                                                              # AND
        ($self->{script_to_path_name})                                                  # TO path has a value
        )
        {
            #print  $self->{script_from_path_name} . '_' . $iterator . " : " . (%parameter_map->{$self->{script_from_path_name} . '_' . $iterator}) . "\n";
            #print  $self->{script_to_path_name} . '_' . $iterator . " : " . (%parameter_map->{$self->{script_to_path_name} . '_' . $iterator}) . "\n";

            $self->push_from_path(%parameter_map->{$self->{script_from_path_name} . '_' . $iterator});
            $self->push_to_path(%parameter_map->{$self->{script_to_path_name} . '_' . $iterator});

            delete $parameter_map{$self->{script_from_path_name} . '_' . $iterator};
            delete $parameter_map{$self->{script_to_path_name} . '_' . $iterator};

            $iterator++;
        }
        $self->SUPER::fill_parameters(%parameter_map);

        return 1;
    }
}




#-------------------------------------------
# class Installer, inherits from class Command
#-------------------------------------------
package Installer;
{
    use strict;
    our @ISA = qw(Command);    # inherits from Command

    #constructor
    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Command.
        my $self = $class->SUPER::new($name);
        bless $self, $class;
        return $self;
    }
}


#-------------------------------------------
# class Latest_Installer, inherits from class Installer
#-------------------------------------------
package Latest_Installer;
{
    use strict;
    use File::Spec;
    use File::Temp qw/ tempdir /;
    use File::Path qw/ rmtree /;
    use Digest::MD5 qw/ md5_hex /;
    our @ISA = qw(Installer);    # inherits from Installer

    #constructor
    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Installer.
        my $self = $class->SUPER::new($name);
        $self->{_find_latest}           = 1;        #Whether finding the latest installer folder is enabled or not
        $self->{_path_suffix}           = "";       #Additional path string to append once the latest folder has been found
        bless $self, $class;
        return $self;
    }

    #-------------------------------------------
    #Accessor methods
    #-------------------------------------------

    #Accessor method for Latest_Installer's find_latest flag
    sub find_latest {
        my ($self) = @_;
        return $self->{_find_latest};
    }

    #Accessor method for Latest_Installer's find_latest flag
    sub path_suffix {
        my ($self) = @_;
        return $self->{_path_suffix};
    }

    #-------------------------------------------
    #Member methods
    #-------------------------------------------

    #-------------------------------------------
    # Execute. Member function to execute the step. Overrides parent's
    # execute ();
    #-------------------------------------------
    #
    sub execute {
        my ($self) = @_;

        if ($self->find_latest())
        {
            Step::log_out ("[INFO]: Trying to find the latest installer folder. Starting from: " . $self->path());
            my $latest = $self->latest_path ($self->path());
            Step::log_out ("[INFO]: Latest installer folder detected is: " . $latest);
            my $built_path = File::Spec->catdir($self->path(), $latest, $self->path_suffix());
            my $fullcmd_path = File::Spec->catfile($built_path, $self->command());
            $self->path($built_path);
            #
            # There is time delay for the Panzura system to sync files among
            # Argo servers, especially during the release peaks when lots of
            # files need sync. Long time delay of sync will cause installation
            # errors (Consider the case that we're running an installer on local
            # Argo server, but it's not fully synced from remote Argo server
            # yet). To avoid this, we do an explicit robocopy here. If the
            # installer is already on local server, the copy operation should
            # complete quickly. But if the installer is not fully synced yet,
            # robocopy will do wait and retries to ensure the installer is
            # ready before we run it.
            #
            # We only care Windows valid prerelease installers on local Argo.
            if (($^O eq 'MSWin32')
                && ($built_path =~ /cn-sha-argo.*prerelease/i)
                && (-e $fullcmd_path))
            {
                my $md5_hash = md5_hex(lc($built_path));
                my $cache_root = "\\\\cn-sha-rdfs04\\NIInstallers\\Prerelease\\ArgoCache";
                mkdir $cache_root unless (-e $cache_root);
                my $cache_index = substr $md5_hash, 0, 2;
                my $index_dir = File::Spec->catdir($cache_root, $cache_index);
                my $cookiefile = File::Spec->catfile($index_dir, $md5_hash);

                unless (-e $cookiefile)  # did not robocopy this installer yet
                {
                    my $tmpdir = tempdir();
                    my $ret_val = $self->robo_copy($built_path, $tmpdir);
                    if (!$ret_val)
                    {
                        mkdir $index_dir unless (-e $index_dir);
                        open(MYFILE, ">>$cookiefile");
                        print MYFILE "$built_path\n";
                        close(MYFILE);
                    }
                    rmtree($tmpdir);
                }
            }
        }

        # TODO: Move this into a common private method of command later on.
        if ($self->sleep_until_reboot())                  #if this step will reboot the system
        {
            $Step::rebooting =1;                          #Set the global flag for an inminent reboot
        }

        $self->build_and_run_command();
    }

    #--------------------------------------------------------
    # Call Windows Robocopy to copy folders
    #--------------------------------------------------------
    sub robo_copy {
        my ($self, $copyfrom, $copyto) = @_;

        #   /E :: copy subdirectories, including Empty ones.
        #  /NP :: No Progress - don't display % copied.
        # /NFL :: No File List - don't log file names.
        # /NDL :: No Directory List - don't log directory names.
        # /R:n :: number of Retries on failed copies
        # /W:n :: Wait time between retries
        my $command = '"\\\\cn-sha-rdfs01\\RD\\SAST\\Installer_Services\\Tools\\Installer Tools\\robocopy.exe" "' . $copyfrom . '" "' . $copyto . '" /E /NP /NFL /NDL /R:120 /W:10';
        my $ret_val = system($command) / 256;
        # robocopy Exit Codes, http://ss64.com/nt/robocopy-exit.html
        Step::log_out("[INFO]: Robocopy exit code: " . $ret_val);
        if ($ret_val == 4 || $ret_val == 8)
        {
            return 1;
        }
        return 0;
    }

    #--------------------------------------------------------
    # Find latest installer folder
    #--------------------------------------------------------

    sub latest_path {
        my ($self,$base_path) = @_;
        my @dir_contents;
        opendir(DNAME, $base_path) || die "Unable to access directory...Sorry";
        @dir_contents = grep (!/^\./ && (-d "$base_path/$_"), readdir(DNAME));
        closedir(DNAME);
        my $TmpDateTime = 0;
        my $ResultDir = "";

        for my $dirname(@dir_contents)
        {
            my $modtime = (stat(File::Spec->catfile($base_path, $dirname)))[9];
            if ($modtime > $TmpDateTime)
            {
                $TmpDateTime = $modtime;
                $ResultDir = $dirname
            }
        }

        return ($ResultDir);
    }

}

#-------------------------------------------
# class Notifier, inherits from class Command
#-------------------------------------------
package Notifier;
{
    use strict;
    use IO::Socket;
    our @ISA = qw(Command);    # inherits from Command

    #constructor
    sub new {
        my ($class,$name) = @_;

        #call the constructor of the parent class, Command.
        my $self = $class->SUPER::new($name);
        $self->{_host}    = undef;
        $self->{_port}    = undef;
        $self->{_message} = "";
        bless $self, $class;
        return $self;
    }

    #-------------------------------------------
    #Accessor methods
    #-------------------------------------------

    #Accessor method for Notifier's host flag
    sub host {
        my ($self) = @_;
        return $self->{_host};
    }

    #Accessor method for Notifier's port flag
    sub port {
        my ($self) = @_;
        return $self->{_port};
    }

    #Accessor method for Notifier's message flag
    sub message {
        my ($self) = @_;
        return $self->{_message};
    }

    #-------------------------------------------
    # Execute. Member function to execute the step. Overrides parent's
    # execute ();
    #-------------------------------------------
    #
    sub execute {
        my ($self) = @_;
        Step::log_out ("[INFO]: Trying to connect: " . $self->host(). ":" . $self->port());
        my $sock = new IO::Socket::INET ( PeerAddr => $self->host(), PeerPort => $self->port(), Proto => 'tcp',);
        #die "Could not create socket: $!\n" unless $sock;
        Step::log_out ("[ERROR]: Could not create socket: $!") unless $sock;
        return 1 unless $sock;
        Step::log_out ("[INFO]: Trying to send message: " . $self->message());
        print $sock "" . $self->message();
        Step::log_out ("[INFO]: Message send out!");
        close($sock);
    }
}

#-------------------------------------------
#Special namespace designed to hold all the self-tests for the Step class family
#-------------------------------------------

package StepClassTest;
{
    $test_result = 1;
    $test_counter = 0;
    my @failed_tests=();
    #print "overall result: " . $StepClassTest::test_result . "\n";

    #Function to keep track of the test overall test results
    sub result {
        my ($new_result)=@_;
        if (!$new_result)
        {
            push (@failed_tests,$StepClassTest::test_counter);
        }
        $StepClassTest::test_counter++;
        $StepClassTest::test_result = $StepClassTest::test_result && $new_result;
        #print "new result: " . $new_result . "\n";
        #print "overall result: " . $StepClassTest::test_result . "\n";
    }

    sub failed_tests {
        return @failed_tests;
    }

    #------------
    #Tests
    #------------
    sub step_class_autotest {

        #Static creation tests
        my @steps = ();
        result($steps[@steps]=new Step('step1'));
        result($steps[@steps]=new Step('step2'));
        result($steps[@steps]=new Command('MyCommand step'));
        result($steps[@steps]=new Reboot('MyReboot'));
        result($steps[@steps]=new Installer('MyInstaller'));
        result($steps[@steps]=new Scripted_Copy('MyScriptedCopy'));
        result($steps[@steps]=new Latest_Installer('MyLatestInstaller'));

        # Test dynamic creation, e.g. when we don't know the type ahead of time
        my $step_class = 'Command';
        my $dynamically_created_step;

        #Try the case where things are ok
        result ($dynamically_created_step = Step::new_step($step_class,'My First Dynamic step'));

        #Try the case where the class name is invalid
        $step_class = 'TheCommand';
        result (!($dynamically_created_step = Step::new_step($step_class,'My-should-have-failed-step')));

         #Try the case where the name is correct but the case is incorrect (we want to be case-insensitive)
        $step_class = 'lAtest_iNSTaller';
        result ($dynamically_created_step = Step::new_step($step_class,'My First Dynamic step'));

        return result(1);
    }
}

sub DESTROY {
}

1;
__END__
