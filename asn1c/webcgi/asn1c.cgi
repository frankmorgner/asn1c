#!/usr/bin/perl -w
#
# $Id$
#

############################################################################
# The following preferences may be modified to match the local environment #
############################################################################

# Directory with the users data.
$TMPDIR = '/tmp/asn1c-cgi-jail/';
$SUIDHelper = './asn1c-suid-helper';
$SkeletonsDir = '/usr/local/share/asn1c';	# Will be needed only once
$MD5ProgramPath = 'md5';
$DM = 0750;	# Directory mode for all mkdirs.

$warn = '<CENTER><FONT SIZE=+1><B>';
$unwarn = '</B></FONT></CENTER>';

$OpEnvFailed = 'Failed to create the operations\' environment:';
$RandFailed = 'No source of randomness';
$SandBoxInitFailed = 'User playground initialization failed';

$myName = $ENV{SCRIPT_NAME};	# URL of this particular script (without args)

$homePath = "<FONT FACE=Courier SIZE=-1>"
	. "<A HREF=http://lionet.info/>Home</A>"
	. " &gt;&gt; <A HREF=http://lionet.info/asn1c/>asn1c</A>"
	. " &gt;&gt; <A HREF=http://lionet.info/asn1c/asn1c.cgi>Online ASN.1 Compiler</A>"
	. "</FONT><P>";

###################################################
# The code below rarely requires any modification #
###################################################

my $content = '';	# Default content is empty

use CGI qw/param cookie header upload escapeHTML/;

$|=1;	# Enable AutoFlush (for older versions of Perl)

# If something goes wrong, this function is invoked to display the error message
sub bark($@) {
	local $_ = join("<BR>\n", @_);
	$content = $warn . $_ . $unwarn;
	goto PRINTOUT;
}

# Make the directory name containing session files for the given Session ID
sub makeSessionDirName($$) {
	local $pfx = shift;	# Prefix is the name of the top-level directory
	local $sid = shift;	# Session identifier (md5)
	$pfx . '/sessions/' . $sid . '/';
}

# Create ISO 8601 time string: "YYYY-MM-DDThh:mm:ss"
my $cachedTime;
sub isoTime() {
	return $cachedTime if $cachedTime;
	local @tm = localtime(time);

	$tm[5] += 1900;
	$tm[4] += 1;

	# Insert leading zeros
	for(my $i = 0; $i < 5; $i++) {
		$tm[$i] =~ s/^(.)$/0$1/;
	}

	$cachedTime = "$tm[5]-$tm[4]-$tm[3]T$tm[2]:$tm[1]:$tm[0]";
}

# Create the necessary environment for chrooting into.
sub prepareChrootEnvironment() {
	return 1 if(-d $TMPDIR);	# Envuronment already exists
	mkdir $TMPDIR, $DM, or bark($OpEnvFailed, $!);	# Global directory
	mkdir $TMPDIR . 'sessions', $DM or bark($OpEnvFailed, $!); # sessions
	mkdir $TMPDIR . 'bin', $DM or bark($OpEnvFailed, $!);	# asn1c location
	mkdir $TMPDIR . 'skeletons', $DM or bark($OpEnvFailed, $!); # asn1c data
	my $compiler_location = `cd / && which asn1c 2>/dev/null`
		or bark($OpEnvFailed, $!);			# copy asn1c in
	$compiler_location =~ s/[^\/a-z1-9.-]//ig;
	bark($OpEnvFailed, $!) unless($compiler_location =~ /^\//);
	if(-d '/lib') {
		# Merge in dynamic libc
		mkdir $TMPDIR . 'lib', $DM or bark($OpEnvFailed, $!);
		system("cd $TMPDIR/lib && "
			. "for i in"
				. " /lib/libc.*"
				. " /lib/libm.*"
			. 'do ln $i; done');
	} elsif(-d '/usr/lib') {
		# There's no /lib on MacOS
		mkdir $TMPDIR . 'usr', $DM or bark($OpEnvFailed, $!);
		mkdir $TMPDIR . 'usr/lib', $DM or bark($OpEnvFailed, $!);
		mkdir $TMPDIR . 'usr/lib/system', $DM or bark($OpEnvFailed, $!);
		system("cd $TMPDIR/usr/lib && "
			. "for i in"
				. " /usr/lib/libc.*"
				. " /usr/lib/libSystem.*"
				. " /usr/lib/system/libmath*"
				. " /usr/lib/dy*"
			. '; do ln $i; done');
	}
	system("cp $compiler_location $TMPDIR/bin 2>/dev/null") == 0
		or bark($OpEnvFailed, $!);
	system("cp -r $SkeletonsDir/* $TMPDIR/skeletons >/dev/null 2>&1") == 0
			or bark($OpEnvFailed, $!);
	return 1;
}

my $EnvironmentSetOK = prepareChrootEnvironment();

#
# Prepare the session and create the session directory.
# If session exists, perfom arguments checking and execute historic views.
#
$session = cookie('SessionID');
unless($session) {
	$session = '';
	open(R, '/dev/urandom')
		or open(R, '/dev/random')
			or bark($RandFailed);
	read(R, $session, 16) == 16 or bark("Not enough randomness");
	if($ENV{HTTP_USER_AGENT}) {
		$session .= $ENV{HTTP_USER_AGENT};	# Add randomness
	}
	my $pid = open(R, "-|");
	if($pid == 0) {	# Child
		open(W, "| $MD5ProgramPath") or die;
		print W $session;
		exit(0);
	}
	$session = <R>;
	$session =~ s/[^a-f0-9]//ig;
	bark("md5 program is rotten here") if(length($session) != 32);
	$sessionDir = makeSessionDirName($TMPDIR, $session);
	mkdir($sessionDir, $DM) or bark($SandBoxInitFailed);
	my $ck = cookie(-name=>'SessionID', -value=>$session, -expires=>'+1y');
	print header(-cookie=>$ck);
} else {
	$session =~ s/[^a-f0-9]//ig;
	bark("Nope, try again") if(length($session) != 32);	# cool hacker?

	# Make sure the session directory exists
	$sessionDir = makeSessionDirName($TMPDIR, $session);
	mkdir($sessionDir, $DM) or bark($SandBoxInitFailed)
		unless(-d $sessionDir);

	local $t = param('time');
	local $trans = param('trans');
	local $fetch = param('fetch');
	local $show = param('show');

	unless($t =~ /^[0-9TZ:+-]{14,}$/ && $trans =~ /^[.a-z0-9_-]+$/i) {
		$fetch = '';
		$show = '';
	}
	if($fetch =~ /^[.a-z0-9_-]+$/i || $show =~ /^(log|tgz)$/) {
		local $fname = $sessionDir . '/' . $t . '--' . $trans;

		if($show eq 'tgz') {
			printf("Content-Type: application/x-tar\n");
			printf("Content-Encoding: gzip\n\n");
			exec("cd $fname && "
				. "for i in *.[ch]; do if [ -L \$i ]; then"
				. " cp $TMPDIR/skeletons/\$i \$i.-;"
				. " mv \$i.- \$i;"
				. " fi done && tar --dereference --owner nobody --group nobody -zcvf - ./*.[ch] ./Makefile*");
			exit(0);
		}

		if($show eq 'log') {
			$fname .= '/+Log';
		} else {
			$fname .= '/' . $fetch;
		}
		open(I, "< " . $fname)
			or bark("Invalid or outdated request: [$fname] [$show] $!");
		printf "Content-Type: text/plain\n\n";
		while(<I>) {
			print;
		}
		exit(0);
	}

	print header();
}
$HTTPHeaderGenerated = 1;

open(LOG, ">> $sessionDir/+logfile") or bark("Sandbox error: $!");
print LOG isoTime() . "\tIP=$ENV{REMOTE_ADDR}";

@gotSafeNames = ();
@gotNames = param('file');
if($#gotNames != -1 && $gotNames[0] ne "") {
	@gotFiles = upload('file');
} else {
	@gotNames = ();
	@gotFiles = ();
}

if($#gotNames == -1) {
	my $text = param('text');
	if($text) {
		push(@gotNames, 'module.asn1');
	}
}

# Make safe filenames
foreach my $fname (@gotNames) {
	local $_ = $fname;
	s/.*\///g;	# Strip directory components
	s/.*\\//g;	# Strip directory components (DOS version)
	s/^[.-]/_/g;	# Don't allow filenames starting with a dot or a dash
	s/[^._a-z0-9-]/_/gi;
	if(!length($_)) {
		print LOG "\n";
		bark("Too strange filename: \"$fname\"");
	}
	$_ .= '.asn1' unless(/asn[1]{0,1}$/i);
	@gotSafeNames = (@gotSafeNames, $_);
	print LOG "\t" . $_;
}

#
# Save the files and start compilation process.
#
if($#gotSafeNames >= 0) {
	$transactionDir = isoTime() . '--' . join("-", @gotSafeNames);
	print LOG "\tDST=$transactionDir";

	my $sandbox = $sessionDir . '/' . $transactionDir;
	mkdir($sandbox, $DM) or bark($SandBoxInitFailed);

	open(I, '> ' . $sandbox . '/+Names');
	print I join("\n", @gotNames);
	open(I, '> ' . $sandbox . '/+safeNames');
	print I join("\n", @gotSafeNames);
	for(my $i = 0; $i <= $#gotSafeNames; $i++) {
		local $name = $gotSafeNames[$i];
		open(I, '> ' . $sandbox . '/'. $name);
		if($#gotFiles == -1) {
			print I scalar(param('text'));
		} else {
			while(<$gotFiles[$I]>) {
				print I;
			}
		}
	}

	my $inChDir = makeSessionDirName("/", $session) . $transactionDir;
	my $options = '';
	$options .= " -Wdebug-lexer" if(param("optDebugL") eq "on");
	$options .= " -E" if(param("optE") eq "on");
	$options .= " -EF" if(param("optEF") eq "on");
	$options .= " -fnative-types" if(param("optNT") eq "on");
	system("$TMPDIR/bin/asn1c -v 2>&1 | sed -e 's/^/-- /' > $sandbox/\+Log && $SUIDHelper $TMPDIR $inChDir $options @gotSafeNames >> $sandbox/+Log 2>&1; "
		. "echo \$? > $sandbox/+ExitCode");
	bark("Failed to initiate compilation process: $!")
		if(!-r $sandbox . '/+ExitCode');
}

#print join("<BR>\n", `env`);

$form =
  "<FORM METHOD=POST ACTION=$myName ENCTYPE=\"multipart/form-data\">"
. "Pick the ASN.1 module file:<BR>\n"
. "<INPUT TYPE=file NAME=file SIZE=40><BR>\n"
. "Alternatively, enter the ASN.1 specification into the area below:<BR>\n"
. "<TEXTAREA NAME=text ROWS=15 COLS=60>\n"
. "/*\n"
. " * This ASN.1 specification is given for illustrative purposes\n"
. " */\n"
. "TestModule  { iso org(3) dod(6) internet(1) private(4)\n"
. "        1 spelio(9363) software(1) asn1c(5) webcgi(2) 1 }\n"
. "DEFINITIONS ::= BEGIN\n"
. "\n"
. "  TestType ::= SEQUENCE {\n"
. "      num INTEGER,\n"
. "      str UTF8String (SIZE(1..20)) OPTIONAL\n"
. "  }\n"
. "\n"
. "END\n"
. "</TEXTAREA><BR>\n"
. "<P>"
. "<FONT SIZE=-1>"
. "These options may be enabled to control the compiler's behavior:<BR>\n"
. "<INPUT TYPE=checkbox NAME=optDebugL> Debug lexer (<I>-Wdebug-lexer</I>)<BR>\n"
. "<INPUT TYPE=checkbox NAME=optE> Just parse and dump (do not compile) (<I>-E</I>)<BR>\n"
. "<INPUT TYPE=checkbox NAME=optEF> Parse, perform semantic checks, and dump (<I>-E -F</I>)<BR>\n"
. "<INPUT TYPE=checkbox NAME=optNT CHECKED=on> Employ native machine types (e.g. <b>double</b> instead of <b>REAL_t</b>) (<I>-fnative-types</I>)<BR>\n"
. "</FONT>"
. "<P>\n"
. "<INPUT TYPE=submit VALUE=\"Proceed with ASN.1 compilation\">\n"
. "</FORM>\n";
;

#
# Gather previous transactions to generate the history page.
# The history page contains a list of several last ASN.1 files
# which were uploaded for compilation into the system
# by this particular browser (cookie-tracked).
#
opendir(SD, $sessionDir) or bark("Cannot open sandbox: $!");
my @transactions = readdir(SD);
my $CountHistoryItems = 0;
foreach my $trans (sort { $b <=> $a } @transactions) {
	next unless($trans =~ /^([0-9TZ:+-]{14,})--([_.a-zA-Z0-9-]+)$/);

	local ($t, $f) = ($1, $2);
	local $origTime = $t;
	$t =~ s/T/ /;	# 1999-01-02T13:53:12 => 1999-01-02 13:53:12

	# Open the list of file names under which these files are known
	# at the remote system.
	open(I, '< ' . $sessionDir . '/' . $trans . '/+Names');
	local @Names = <I>;

	# Open the list of "safe" file names under which these files
	# are known to our file system.
	open(I, '< ' . $sessionDir . '/' . $trans . '/+safeNames');
	local @safeNames = <I>;

	# Create a list of real file names whith appropriate links to the
	# "safe" file names for subsequent file fetching.
	local @markedNames = ();
	for(my $i = 0; $i <= $#Names; $i++) {
		local $_ = "<A HREF=\"$myName?time="
			. escapeHTML($origTime)
			. "&trans=$f"
			. "&fetch=$safeNames[$i]\">$Names[$i]</A>";
		@markedNames = (@markedNames, $_);
	}

	open(I, '< ' . $sessionDir . '/' . $trans . '/+ExitCode');
	local $ec = int(<I>);

	if($ec == 0) {
		$results = "<FONT COLOR=darkgreen><B>"
			. "Compiled OK</B></FONT><BR>\n";
	} else {
		$results = "<FONT COLOR=darkred>"
			. "Error during compilation: $ec</FONT><BR>\n";
	}

	$results .= "<NOBR>"
		. (($ec == 0) ? '1. ' : '')
		. "<A HREF=\"$myName?time="
		. escapeHTML($origTime)
		. "&trans=$f"
		. "&show=log\">"
		. "Show compiler log</A></NOBR>";
	if($ec == 0) {
		$results .= "<BR>\n<NOBR>"
		. "2. <A HREF=\"$myName?time="
		. escapeHTML($origTime)
		. "&trans=$f"
		. "&show=tgz\">"
		. "Fetch results (.tgz)</A></NOBR>";
	}

	$history .=
		"<TR><TD BGCOLOR=white ALIGN=center><FONT FACE=Helvetica SIZE=-2>$t</FONT></TD>"
		. "<TD BGCOLOR=white ALIGN=center><FONT SIZE=-1 FACE=Helvetica>"
		. join(", ", @markedNames)
		. "</FONT></TD>"
		. "<TD BGCOLOR=white><FONT SIZE=-2 FACE=Helvetica>"
			. $results
			. "</TD>"
		. "</TR>";
	
	last unless(++$CountHistoryItems < 5);
}
if($history) {
	$history = "<H3>History</H3>"
	. "<TABLE CELLPADDING=0 CELLSPACING=0 BGCOLOR=#404040 WIDTH=100%><TR><TD>"
	. "<TABLE BORDER=0 CELLPADDING=5 CELLSPACING=1 WIDTH=100%>\n"
	. "<TR BGCOLOR=#e0f0d0>"
	. "<TH><FONT COLOR=#404040 FACE=Courier>Time</FONT></TH>"
	. "<TH><FONT COLOR=#404040 FACE=Courier>Files processed</FONT></TH>"
	. "<TH><FONT COLOR=#404040 FACE=Courier>Result</FONT></TH>"
	. "</TR>\n"
	. $history . "</TABLE></TD></TR></TABLE><BR>\n";
}

$content =
  "<TABLE WIDTH=100% BORDER=0 CELLPADDING=5><TR><TD VALIGN=top>\n"
. "<H3 ALIGN=center>ASN.1 Input</H3>\n"
. "$form\n"
. "</TD><TD WIDTH=50% ALIGN=center VALIGN=top>\n$history"
	. "<FONT SIZE=-2><B>Privacy Note 1:</B> this page is tailored "
	. "to your browser using a cryprographically strong cookie. "
	. "Other users will see different data. "
	. "However, the page is not secure against malicious users "
	. "if they are able to intercept your non-SSL Web traffic."
	. "<BR><B>Privacy Note 2:</B> The author reserves the right to collect any information directly or indirectly supplied by the user of this system. This information may only be used by the author or contributors to enhance the software product. No data is ever given, sold, or otherwise distributed to the third-parties."
	. "<BR><B>Privacy Note 3:</B> In no event shall the author or contributors be liable for any damages, however caused, even if advised of the possibility of such damage."
	. "</FONT>"
. "</TD></TR></TABLE>";

$ua = $ENV{HTTP_USER_AGENT};
$ua =~ s/\\/\\\\/;
$ua =~ s/"/\\"/;
print LOG "\tUA=\"$ua\"";
print LOG "\n";	# Finalize logging record

PRINTOUT:

print header() unless($HTTPHeaderGenerated);

# If environment has never been set up completely, remove it.
if($EnvironmentSetOK != 1 && $TMPDIR ne "/") {
	system("rm -rf $TMPDIR/ >/dev/null 2>&1");
}

print<<EOM;
<HTML>
<HEAD>
<META KEYWORDS="ASN.1, asn1c, compiler">
<TITLE>Online ASN.1 Compiler</TITLE>
</HEAD>
<BODY BGCOLOR=white>

$homePath

$content

<HR WIDTH=70%>
<CENTER><ADDRESS><FONT SIZE=-1 FACE=Courier COLOR=#404040>
<A HREF=http://lionet.info/asn1c>The ASN.1 Compiler</A>
	Copyright &copy; 2003, 2004
Lev Walkin &lt;<A HREF=mailto:vlm&#64;lionet.info>vlm&#64;lionet.info</A>&gt;
</FONT></ADDRESS></CENTER>
</BODY>
</HTML>
EOM