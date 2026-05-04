     1|# Low level unix utility functions
     2|#
     3|# Copyright (C) 2016-2020  Kevin O'Connor <kevin@koconnor.net>
     4|#
     5|# This file may be distributed under the terms of the GNU GPLv3 license.
     6|import sys, os, pty, fcntl, termios, signal, logging, json, time
     7|import subprocess, traceback, shlex
     8|
     9|
    10|######################################################################
    11|# Low-level Unix commands
    12|######################################################################
    13|
    14|# Return the SIGINT interrupt handler back to the OS default
    15|def fix_sigint():
    16|    signal.signal(signal.SIGINT, signal.SIG_DFL)
    17|fix_sigint()
    18|
    19|# Set a file-descriptor as non-blocking
    20|def set_nonblock(fd):
    21|    fcntl.fcntl(fd, fcntl.F_SETFL
    22|                , fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)
    23|
    24|# Clear HUPCL flag
    25|def clear_hupcl(fd):
    26|    attrs = termios.tcgetattr(fd)
    27|    attrs[2] = attrs[2] & ~termios.HUPCL
    28|    try:
    29|        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    30|    except termios.error:
    31|        pass
    32|
    33|# Support for creating a pseudo-tty for emulating a serial port
    34|def create_pty(ptyname):
    35|    mfd, sfd = pty.openpty()
    36|    try:
    37|        os.unlink(ptyname)
    38|    except os.error:
    39|        pass
    40|    filename = os.ttyname(sfd)
    41|    os.chmod(filename, 0o660)
    42|    os.symlink(filename, ptyname)
    43|    set_nonblock(mfd)
    44|    old = termios.tcgetattr(mfd)
    45|    old[3] = old[3] & ~termios.ECHO
    46|    termios.tcsetattr(mfd, termios.TCSADRAIN, old)
    47|    return mfd
    48|
    49|
    50|######################################################################
    51|# Helper code for extracting mcu build info
    52|######################################################################
    53|
    54|def _try_read_file(filename, maxsize=32*1024):
    55|    try:
    56|        with open(filename, 'r') as f:
    57|            return f.read(maxsize)
    58|    except (IOError, OSError) as e:
    59|        logging.debug("Exception on read %s: %s", filename,
    60|                      traceback.format_exc())
    61|        return None
    62|
    63|def dump_file_stats(build_dir, filename):
    64|    fname = os.path.join(build_dir, filename)
    65|    try:
    66|        mtime = os.path.getmtime(fname)
    67|        fsize = os.path.getsize(fname)
    68|        timestr = time.asctime(time.localtime(mtime))
    69|        logging.info("Build file %s(%d): %s", fname, fsize, timestr)
    70|    except:
    71|        logging.info("No build file %s", fname)
    72|
    73|# Try to log information on the last mcu build
    74|def dump_mcu_build():
    75|    build_dir = os.path.join(os.path.dirname(__file__), '..')
    76|    # Try to log last mcu config
    77|    dump_file_stats(build_dir, '.config')
    78|    data = _try_read_file(os.path.join(build_dir, '.config'))
    79|    if data is not None:
    80|        logging.info("========= Last MCU build config =========\n%s"
    81|                     "=======================", data)
    82|    # Try to log last mcu build version
    83|    dump_file_stats(build_dir, 'out/klipper.dict')
    84|    try:
    85|        data = _try_read_file(os.path.join(build_dir, 'out/klipper.dict'))
    86|        data = json.loads(data)
    87|        logging.info("Last MCU build version: %s", data.get('version', ''))
    88|        logging.info("Last MCU build tools: %s", data.get('build_versions', ''))
    89|        cparts = ["%s=%s" % (k, v) for k, v in data.get('config', {}).items()]
    90|        logging.info("Last MCU build config: %s", " ".join(cparts))
    91|    except:
    92|        pass
    93|    dump_file_stats(build_dir, 'out/klipper.elf')
    94|
    95|
    96|######################################################################
    97|# Python2 wrapper hacks
    98|######################################################################
    99|
   100|
######################################################################
# Structured logging helpers
######################################################################

def log_with_context(level, message, context=None):
    """Log a message with optional structured context data.
    
    Args:
        level: Logging level (logging.INFO, logging.ERROR, etc.)
        message: Human-readable message string
        context: Optional dict of additional context data
    """
    if context:
        # Format context as key=value pairs
        ctx_str = " ".join("%s=%s" % (k, v) for k, v in context.items())
        logging.log(level, "%s [%s]", message, ctx_str)
    else:
        logging.log(level, message)


def log_operation_start(operation, **kwargs):
    """Log the start of an operation with context."""
    log_with_context(logging.INFO, "Starting operation: %s" % operation, kwargs)


def log_operation_complete(operation, duration=None, **kwargs):
    """Log successful completion of an operation."""
    if duration is not None:
        kwargs['duration_ms'] = int(duration * 1000)
    log_with_context(logging.INFO, "Completed operation: %s" % operation, kwargs)


def log_operation_error(operation, error, **kwargs):
    """Log an error during an operation."""
    kwargs['error_type'] = type(error).__name__
    log_with_context(logging.ERROR, "Error in operation: %s - %s" % (operation, str(error)), kwargs)


def setup_python2_wrappers():
   101|    if sys.version_info.major >= 3:
   102|        return
   103|    # Add module hacks so that common Python3 module imports work in Python2
   104|    import ConfigParser, Queue, io, StringIO, time
   105|    sys.modules["configparser"] = ConfigParser
   106|    sys.modules["queue"] = Queue
   107|    io.StringIO = StringIO.StringIO
   108|    time.process_time = time.clock
   109|setup_python2_wrappers()
   110|
   111|
   112|######################################################################
   113|# General system and software information
   114|######################################################################
   115|
   116|def get_cpu_info():
   117|    data = _try_read_file('/proc/cpuinfo', maxsize=1024*1024)
   118|    if data is None:
   119|        return "?"
   120|    lines = [l.split(':', 1) for l in data.split('\n')]
   121|    lines = [(l[0].strip(), l[1].strip()) for l in lines if len(l) == 2]
   122|    core_count = [k for k, v in lines].count("processor")
   123|    model_name = dict(lines).get("model name", "?")
   124|    return "%d core %s" % (core_count, model_name)
   125|
   126|def get_device_info():
   127|    data = _try_read_file('/proc/device-tree/model')
   128|    if data is None:
   129|        data = _try_read_file("/sys/class/dmi/id/product_name")
   130|        if data is None:
   131|            return "?"
   132|    return data.rstrip(' \0').strip()
   133|
   134|def get_linux_version():
   135|    data = _try_read_file('/proc/version')
   136|    if data is None:
   137|        return "?"
   138|    return data.strip()
   139|
   140|def get_version_from_file(klippy_src):
   141|    data = _try_read_file(os.path.join(klippy_src, '.version'))
   142|    if data is None:
   143|        return "?"
   144|    return data.rstrip()
   145|
   146|def _get_repo_info(gitdir):
   147|    repo_info = {"branch": "?", "remote": "?", "url": "?"}
   148|    prog_branch = ('git', '-C', gitdir, 'branch', '--no-color')
   149|    try:
   150|        process = subprocess.Popen(prog_branch, stdout=subprocess.PIPE,
   151|                                   stderr=subprocess.PIPE)
   152|        branch_list, err = process.communicate()
   153|        retcode = process.wait()
   154|        if retcode != 0:
   155|            logging.debug("Error running git branch: %s", err)
   156|            return repo_info
   157|        lines = str(branch_list.strip().decode()).split("\n")
   158|        for line in lines:
   159|            if line[0] == "*":
   160|                repo_info["branch"] = line[1:].strip()
   161|                break
   162|        else:
   163|            logging.debug("Unable to find current branch:\n%s", branch_list)
   164|            return repo_info
   165|        if repo_info["branch"].startswith("(HEAD detached"):
   166|            parts = repo_info["branch"].strip("()").split()[-1].split("/", 1)
   167|            if len(parts) != 2:
   168|                return repo_info
   169|            repo_info["remote"] = parts[0]
   170|        else:
   171|            key = "branch.%s.remote" % (repo_info["branch"],)
   172|            prog_config = ('git', '-C', gitdir, 'config', '--get', key)
   173|            process = subprocess.Popen(prog_config, stdout=subprocess.PIPE,
   174|                                       stderr=subprocess.PIPE)
   175|            remote_info, err = process.communicate()
   176|            retcode = process.wait()
   177|            if retcode != 0:
   178|                logging.debug("Error running git config: %s", err)
   179|                return repo_info
   180|            repo_info["remote"] = str(remote_info.strip().decode())
   181|        prog_remote_url = (
   182|            'git', '-C', gitdir, 'remote', 'get-url', repo_info["remote"])
   183|        process = subprocess.Popen(prog_remote_url, stdout=subprocess.PIPE,
   184|                                   stderr=subprocess.PIPE)
   185|        remote_url, err = process.communicate()
   186|        retcode = process.wait()
   187|        if retcode != 0:
   188|            logging.debug("Error running git remote get-url: %s", err)
   189|            return repo_info
   190|        repo_info["url"] = str(remote_url.strip().decode())
   191|    except:
   192|        logging.debug("Error fetching repo info: %s", traceback.format_exc())
   193|    return repo_info
   194|
   195|def get_git_version(from_file=True):
   196|    git_info = {
   197|        "version": "?",
   198|        "file_status": [],
   199|        "branch": "?",
   200|        "remote": "?",
   201|        "url": "?"
   202|    }
   203|    klippy_src = os.path.dirname(__file__)
   204|
   205|    # Obtain version info from "git" program
   206|    gitdir = os.path.join(klippy_src, '..')
   207|    prog_desc = ('git', '-C', gitdir, 'describe', '--always',
   208|                 '--tags', '--long', '--dirty')
   209|    prog_status = ('git', '-C', gitdir, 'status', '--porcelain', '--ignored')
   210|    try:
   211|        process = subprocess.Popen(prog_desc, stdout=subprocess.PIPE,
   212|                                   stderr=subprocess.PIPE)
   213|        ver, err = process.communicate()
   214|        retcode = process.wait()
   215|        if retcode == 0:
   216|            git_info["version"] = str(ver.strip().decode())
   217|            process = subprocess.Popen(prog_status, stdout=subprocess.PIPE,
   218|                                       stderr=subprocess.PIPE)
   219|            stat, err = process.communicate()
   220|            status = [l.split(None, 1)
   221|                      for l in str(stat.strip().decode()).split('\n')]
   222|            retcode = process.wait()
   223|            if retcode == 0:
   224|                git_info["file_status"] = status
   225|            else:
   226|                logging.debug("Error getting git status: %s", err)
   227|            git_info.update(_get_repo_info(gitdir))
   228|            return git_info
   229|        else:
   230|            logging.debug("Error getting git version: %s", err)
   231|    except:
   232|        logging.debug("Exception on run: %s", traceback.format_exc())
   233|
   234|    if from_file:
   235|        git_info["version"] = get_version_from_file(klippy_src)
   236|    return git_info
   237|