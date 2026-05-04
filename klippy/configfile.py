     1|# Code for reading and writing the Klipper config file
     2|#
     3|# Copyright (C) 2016-2024  Kevin O'Connor <kevin@koconnor.net>
     4|#
     5|# This file may be distributed under the terms of the GNU GPLv3 license.
     6|import sys, os, glob, re, time, logging, configparser, io
     7|
     8|error = configparser.Error
     9|
    10|
    11|######################################################################
    12|# Config section parsing helper
    13|######################################################################
    14|
    15|class sentinel:
    16|    pass
    17|
    18|class ConfigWrapper:
    19|    error = configparser.Error
    20|    def __init__(self, printer, fileconfig, access_tracking, section):
    21|        self.printer = printer
    22|        self.fileconfig = fileconfig
    23|        self.access_tracking = access_tracking
    24|        self.section = section
    25|    def get_printer(self):
    26|        return self.printer
    27|    def get_name(self):
    28|        return self.section
    29|    def _get_wrapper(self, parser, option, default, minval=None, maxval=None,
    30|                     above=None, below=None, note_valid=True):
    31|        if not self.fileconfig.has_option(self.section, option):
    32|            if default is not sentinel:
    33|                if note_valid and default is not None:
    34|                    acc_id = (self.section.lower(), option.lower())
    35|                    self.access_tracking[acc_id] = default
    36|                return default
    37|            raise error("Option '%s' in section '%s' must be specified"
    38|                        % (option, self.section))
    39|        try:
    40|            v = parser(self.section, option)
    41|        except self.error as e:
    42|            raise
    43|        except:
    44|            raise error("Unable to parse option '%s' in section '%s'"
    45|                        % (option, self.section))
    46|        if note_valid:
    47|            self.access_tracking[(self.section.lower(), option.lower())] = v
    48|        if minval is not None and v < minval:
    49|            raise error("Option '%s' in section '%s' must have minimum of %s"
    50|                        % (option, self.section, minval))
    51|        if maxval is not None and v > maxval:
    52|            raise error("Option '%s' in section '%s' must have maximum of %s"
    53|                        % (option, self.section, maxval))
    54|        if above is not None and v <= above:
    55|            raise error("Option '%s' in section '%s' must be above %s"
    56|                        % (option, self.section, above))
    57|        if below is not None and v >= below:
    58|            raise self.error("Option '%s' in section '%s' must be below %s"
    59|                             % (option, self.section, below))
    60|        return v
    61|    def get(self, option, default=sentinel, note_valid=True):
    62|        return self._get_wrapper(self.fileconfig.get, option, default,
    63|                                 note_valid=note_valid)
    64|    def getint(self, option, default=sentinel, minval=None, maxval=None,
    65|               note_valid=True):
    66|        return self._get_wrapper(self.fileconfig.getint, option, default,
    67|                                 minval, maxval, note_valid=note_valid)
    68|    def getfloat(self, option, default=sentinel, minval=None, maxval=None,
    69|                 above=None, below=None, note_valid=True):
    70|        return self._get_wrapper(self.fileconfig.getfloat, option, default,
    71|                                 minval, maxval, above, below,
    72|                                 note_valid=note_valid)
    73|    def getboolean(self, option, default=sentinel, note_valid=True):
    74|        return self._get_wrapper(self.fileconfig.getboolean, option, default,
    75|                                 note_valid=note_valid)
    76|    def getchoice(self, option, choices, default=sentinel, note_valid=True):
    77|        if type(choices) == type([]):
    78|            choices = {i: i for i in choices}
    79|        if choices and type(list(choices.keys())[0]) == int:
    80|            c = self.getint(option, default, note_valid=note_valid)
    81|        else:
    82|            c = self.get(option, default, note_valid=note_valid)
    83|        if c not in choices:
    84|            raise error("Choice '%s' for option '%s' in section '%s'"
    85|                        " is not a valid choice" % (c, option, self.section))
    86|        return choices[c]
    87|    def getlists(self, option, default=sentinel, seps=(',',), count=None,
    88|                 parser=str, note_valid=True):
    89|        def lparser(value, pos):
    90|            if len(value.strip()) == 0:
    91|                # Return an empty list instead of [''] for empty string
    92|                parts = []
    93|            else:
    94|                parts = [p.strip() for p in value.split(seps[pos])]
    95|            if pos:
    96|                # Nested list
    97|                return tuple([lparser(p, pos - 1) for p in parts if p])
    98|            res = [parser(p) for p in parts]
    99|            if count is not None and len(res) != count:
   100|                raise error("Option '%s' in section '%s' must have %d elements"
   101|                            % (option, self.section, count))
   102|            return tuple(res)
   103|        def fcparser(section, option):
   104|            return lparser(self.fileconfig.get(section, option), len(seps) - 1)
   105|        return self._get_wrapper(fcparser, option, default,
   106|                                 note_valid=note_valid)
   107|    def getlist(self, option, default=sentinel, sep=',', count=None,
   108|                note_valid=True):
   109|        return self.getlists(option, default, seps=(sep,), count=count,
   110|                             parser=str, note_valid=note_valid)
   111|    def getintlist(self, option, default=sentinel, sep=',', count=None,
   112|                   note_valid=True):
   113|        return self.getlists(option, default, seps=(sep,), count=count,
   114|                             parser=int, note_valid=note_valid)
   115|    def getfloatlist(self, option, default=sentinel, sep=',', count=None,
   116|                     note_valid=True):
   117|        return self.getlists(option, default, seps=(sep,), count=count,
   118|                             parser=float, note_valid=note_valid)
   119|    def getsection(self, section):
   120|        return ConfigWrapper(self.printer, self.fileconfig,
   121|                             self.access_tracking, section)
   122|    def has_section(self, section):
   123|        return self.fileconfig.has_section(section)
   124|    def get_prefix_sections(self, prefix):
   125|        return [self.getsection(s) for s in self.fileconfig.sections()
   126|                if s.startswith(prefix)]
   127|    def get_prefix_options(self, prefix):
   128|        return [o for o in self.fileconfig.options(self.section)
   129|                if o.startswith(prefix)]
   130|    def deprecate(self, option, value=None):
   131|        if not self.fileconfig.has_option(self.section, option):
   132|            return
   133|        pconfig = self.printer.lookup_object("configfile")
   134|        pconfig.deprecate(self.section, option, value)
   135|
   136|
   137|######################################################################
   138|# Config file parsing (with include file support)
   139|######################################################################
   140|
   141|class ConfigFileReader:
   142|    def read_config_file(self, filename):
   143|        try:
   144|            f = open(filename, 'r')
   145|            data = f.read()
   146|            f.close()
   147|        except:
   148|            msg = "Unable to open config file %s" % (filename,)
   149|            logging.exception(msg)
   150|            raise error(msg)
   151|        return data.replace('\r\n', '\n')
   152|    def build_config_string(self, fileconfig):
   153|        sfile = io.StringIO()
   154|        fileconfig.write(sfile)
   155|        return sfile.getvalue().strip()
   156|    def append_fileconfig(self, fileconfig, data, filename):
   157|        if not data:
   158|            return
   159|        # Strip trailing comments
   160|        lines = data.split('\n')
   161|        for i, line in enumerate(lines):
   162|            pos = line.find('#')
   163|            if pos >= 0:
   164|                lines[i] = line[:pos]
   165|        sbuffer = io.StringIO('\n'.join(lines))
   166|        if sys.version_info.major >= 3:
   167|            fileconfig.read_file(sbuffer, filename)
   168|        else:
   169|            fileconfig.readfp(sbuffer, filename)
   170|    def _create_fileconfig(self):
   171|        if sys.version_info.major >= 3:
   172|            fileconfig = configparser.RawConfigParser(
   173|                strict=False, inline_comment_prefixes=(';', '#'))
   174|        else:
   175|            fileconfig = configparser.RawConfigParser()
   176|        return fileconfig
   177|    def build_fileconfig(self, data, filename):
   178|        fileconfig = self._create_fileconfig()
   179|        self.append_fileconfig(fileconfig, data, filename)
   180|        return fileconfig
   181|    def _resolve_include(self, source_filename, include_spec, fileconfig,
   182|                         visited):
   183|        dirname = os.path.dirname(source_filename)
   184|        include_spec = include_spec.strip()
   185|        include_glob = os.path.join(dirname, include_spec)
   186|        include_filenames = glob.glob(include_glob)
   187|        if not include_filenames and not glob.has_magic(include_glob):
   188|            # Empty set is OK if wildcard but not for direct file reference
   189|            raise error("Include file '%s' does not exist" % (include_glob,))
   190|        include_filenames.sort()
   191|        for include_filename in include_filenames:
   192|            include_data = self.read_config_file(include_filename)
   193|            self._parse_config(include_data, include_filename, fileconfig,
   194|                               visited)
   195|        return include_filenames
   196|    def _parse_config(self, data, filename, fileconfig, visited):
   197|        path = os.path.abspath(filename)
   198|        if path in visited:
   199|            raise error("Recursive include of config file '%s'" % (filename))
   200|        visited.add(path)
   201|        lines = data.split('\n')
   202|        # Buffer lines between includes and parse as a unit so that overrides
   203|        # in includes apply linearly as they do within a single file
   204|        buf = []
   205|        for line in lines:
   206|            # Strip trailing comment
   207|            pos = line.find('#')
   208|            if pos >= 0:
   209|                line = line[:pos]
   210|            # Process include or buffer line
   211|            mo = configparser.RawConfigParser.SECTCRE.match(line)
   212|            header = mo and mo.group('header')
   213|            if header and header.startswith('include '):
   214|                self.append_fileconfig(fileconfig, '\n'.join(buf), filename)
   215|                del buf[:]
   216|                include_spec = header[8:].strip()
   217|                self._resolve_include(filename, include_spec, fileconfig,
   218|                                      visited)
   219|            else:
   220|                buf.append(line)
   221|        self.append_fileconfig(fileconfig, '\n'.join(buf), filename)
   222|        visited.remove(path)
   223|    def build_fileconfig_with_includes(self, data, filename):
   224|        fileconfig = self._create_fileconfig()
   225|        self._parse_config(data, filename, fileconfig, set())
   226|        return fileconfig
   227|
   228|
   229|######################################################################
   230|# Config auto save helper
   231|######################################################################
   232|
   233|AUTOSAVE_HEADER = """
   234|#*# <---------------------- SAVE_CONFIG ---------------------->
   235|#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.
   236|#*#
   237|"""
   238|
   239|class ConfigAutoSave:
   240|    def __init__(self, printer):
   241|        self.printer = printer
   242|        self.fileconfig = None
   243|        self.status_save_pending = {}
   244|        self.save_config_pending = False
   245|        gcode = self.printer.lookup_object('gcode')
   246|        gcode.register_command("SAVE_CONFIG", self.cmd_SAVE_CONFIG,
   247|                               desc=self.cmd_SAVE_CONFIG_help)
   248|    def _find_autosave_data(self, data):
   249|        regular_data = data
   250|        autosave_data = ""
   251|        pos = data.find(AUTOSAVE_HEADER)
   252|        if pos >= 0:
   253|            regular_data = data[:pos]
   254|            autosave_data = data[pos + len(AUTOSAVE_HEADER):].strip()
   255|        # Check for errors and strip line prefixes
   256|        if "\n#*# " in regular_data or autosave_data.find(AUTOSAVE_HEADER) >= 0:
   257|            logging.warning("Can't read autosave from config file"
   258|                            " - autosave state corrupted")
   259|            return data, ""
   260|        out = [""]
   261|        for line in autosave_data.split('\n'):
   262|            if ((not line.startswith("#*#")
   263|                 or (len(line) >= 4 and not line.startswith("#*# ")))
   264|                and autosave_data):
   265|                logging.warning("Can't read autosave from config file"
   266|                                " - modifications after header")
   267|                return data, ""
   268|            out.append(line[4:])
   269|        out.append("")
   270|        return regular_data, "\n".join(out)
   271|    comment_r = re.compile('[#;].*$')
   272|    value_r = re.compile('[^A-Za-z0-9_].*$')
   273|    def _strip_duplicates(self, data, fileconfig):
   274|        # Comment out fields in 'data' that are defined in 'config'
   275|        lines = data.split('\n')
   276|        section = None
   277|        is_dup_field = False
   278|        for lineno, line in enumerate(lines):
   279|            pruned_line = self.comment_r.sub('', line).rstrip()
   280|            if not pruned_line:
   281|                continue
   282|            if pruned_line[0].isspace():
   283|                if is_dup_field:
   284|                    lines[lineno] = '#' + lines[lineno]
   285|                continue
   286|            is_dup_field = False
   287|            if pruned_line[0] == '[':
   288|                section = pruned_line[1:-1].strip()
   289|                continue
   290|            field = self.value_r.sub('', pruned_line)
   291|            if fileconfig.has_option(section, field):
   292|                is_dup_field = True
   293|                lines[lineno] = '#' + lines[lineno]
   294|        return "\n".join(lines)
   295|    def load_main_config(self):
   296|        filename = self.printer.get_start_args()['config_file']
   297|        cfgrdr = ConfigFileReader()
   298|        data = cfgrdr.read_config_file(filename)
   299|        regular_data, autosave_data = self._find_autosave_data(data)
   300|        regular_fileconfig = cfgrdr.build_fileconfig_with_includes(
   301|            regular_data, filename)
   302|        autosave_data = self._strip_duplicates(autosave_data,
   303|                                               regular_fileconfig)
   304|        self.fileconfig = cfgrdr.build_fileconfig(autosave_data, filename)
   305|        cfgrdr.append_fileconfig(regular_fileconfig,
   306|                                 autosave_data, '*AUTOSAVE*')
   307|        return regular_fileconfig, self.fileconfig
   308|    def get_status(self, eventtime):
   309|        return {'save_config_pending': self.save_config_pending,
   310|                'save_config_pending_items': self.status_save_pending}
   311|    def set(self, section, option, value):
   312|        if not self.fileconfig.has_section(section):
   313|            self.fileconfig.add_section(section)
   314|        svalue = str(value)
   315|        self.fileconfig.set(section, option, svalue)
   316|        pending = dict(self.status_save_pending)
   317|        if not section in pending or pending[section] is None:
   318|            pending[section] = {}
   319|        else:
   320|            pending[section] = dict(pending[section])
   321|        pending[section][option] = svalue
   322|        self.status_save_pending = pending
   323|        self.save_config_pending = True
   324|        logging.info("save_config: set [%s] %s = %s", section, option, svalue)
   325|    def remove_section(self, section):
   326|        if self.fileconfig.has_section(section):
   327|            self.fileconfig.remove_section(section)
   328|            pending = dict(self.status_save_pending)
   329|            pending[section] = None
   330|            self.status_save_pending = pending
   331|            self.save_config_pending = True
   332|        elif (section in self.status_save_pending and
   333|              self.status_save_pending[section] is not None):
   334|            pending = dict(self.status_save_pending)
   335|            del pending[section]
   336|            self.status_save_pending = pending
   337|            self.save_config_pending = True
   338|    def _disallow_include_conflicts(self, regular_fileconfig):
   339|        for section in self.fileconfig.sections():
   340|            for option in self.fileconfig.options(section):
   341|                if regular_fileconfig.has_option(section, option):
   342|                    msg = ("SAVE_CONFIG section '%s' option '%s' conflicts "
   343|                           "with included value" % (section, option))
   344|                    raise self.printer.command_error(msg)
   345|    cmd_SAVE_CONFIG_help = "Overwrite config file and restart"
   346|    def cmd_SAVE_CONFIG(self, gcmd):
   347|        if not self.fileconfig.sections():
   348|            return
   349|        # Create string containing autosave data
   350|        cfgrdr = ConfigFileReader()
   351|        autosave_data = cfgrdr.build_config_string(self.fileconfig)
   352|        lines = [('#*# ' + l).strip()
   353|                 for l in autosave_data.split('\n')]
   354|        lines.insert(0, "\n" + AUTOSAVE_HEADER.rstrip())
   355|        lines.append("")
   356|        autosave_data = '\n'.join(lines)
   357|        # Read in and validate current config file
   358|        cfgname = self.printer.get_start_args()['config_file']
   359|        try:
   360|            data = cfgrdr.read_config_file(cfgname)
   361|        except error as e:
   362|            msg = "Unable to read existing config on SAVE_CONFIG"
   363|            logging.exception(msg)
   364|            raise gcmd.error(msg)
   365|        regular_data, old_autosave_data = self._find_autosave_data(data)
   366|        regular_data = self._strip_duplicates(regular_data, self.fileconfig)
   367|        data = regular_data.rstrip() + autosave_data
   368|        new_regular_data, new_autosave_data = self._find_autosave_data(data)
   369|        if not new_autosave_data:
   370|            raise gcmd.error(
   371|                "Existing config autosave is corrupted."
   372|                " Can't complete SAVE_CONFIG")
   373|        try:
   374|            regular_fileconfig = cfgrdr.build_fileconfig_with_includes(
   375|                new_regular_data, cfgname)
   376|        except error as e:
   377|            msg = "Unable to parse existing config on SAVE_CONFIG"
   378|            logging.exception(msg)
   379|            raise gcmd.error(msg)
   380|        self._disallow_include_conflicts(regular_fileconfig)
   381|        # Determine filenames
   382|        datestr = time.strftime("-%Y%m%d_%H%M%S")
   383|        backup_name = cfgname + datestr
   384|        temp_name = cfgname + "_autosave"
   385|        if cfgname.endswith(".cfg"):
   386|            backup_name = cfgname[:-4] + datestr + ".cfg"
   387|            temp_name = cfgname[:-4] + "_autosave.cfg"
   388|        # Create new config file with temporary name and swap with main config
   389|        logging.info("SAVE_CONFIG to '%s' (backup in '%s')",
   390|                     cfgname, backup_name)
   391|        try:
   392|            f = open(temp_name, 'w')
   393|            f.write(data)
   394|            f.close()
   395|            os.rename(cfgname, backup_name)
   396|            os.rename(temp_name, cfgname)
   397|        except:
   398|            msg = "Unable to write config file during SAVE_CONFIG"
   399|            logging.exception(msg)
   400|            raise gcmd.error(msg)
   401|        # Request a restart
   402|        gcode = self.printer.lookup_object('gcode')
   403|        gcode.request_restart('restart')
   404|
   405|
   406|######################################################################
   407|# Config validation (check for undefined options)
   408|######################################################################
   409|
   410|class ConfigValidate:
   411|    def __init__(self, printer):
   412|        self.printer = printer
   413|        self.status_settings = {}
   414|        self.access_tracking = {}
   415|        self.autosave_options = {}
   416|    def start_access_tracking(self, autosave_fileconfig):
   417|        # Note autosave options for use during undefined options check
   418|        self.autosave_options = {}
   419|        for section in autosave_fileconfig.sections():
   420|            for option in autosave_fileconfig.options(section):
   421|                self.autosave_options[(section.lower(), option.lower())] = 1
   422|        self.access_tracking = {}
   423|        return self.access_tracking
   424|    def check_unused(self, fileconfig):
   425|        # Don't warn on fields set in autosave segment
   426|        access_tracking = dict(self.access_tracking)
   427|        access_tracking.update(self.autosave_options)
   428|        # Note locally used sections
   429|        valid_sections = { s: 1 for s, o in self.printer.lookup_objects() }
   430|        valid_sections.update({ s: 1 for s, o in access_tracking })
   431|        # Validate that there are no undefined parameters in the config file
   432|        for section_name in fileconfig.sections():
   433|            section = section_name.lower()
   434|            if section not in valid_sections:
   435|                raise error("Section '%s' is not a valid config section"
   436|                            % (section,))
   437|            for option in fileconfig.options(section_name):
   438|                option = option.lower()
   439|                if (section, option) not in access_tracking:
   440|                    raise error("Option '%s' is not valid in section '%s'"
   441|                                % (option, section))
   442|        # Setup get_status()
   443|        self._build_status_settings()
   444|        # Clear tracking state
   445|        self.access_tracking.clear()
   446|        self.autosave_options.clear()
   447|    def _build_status_settings(self):
   448|        self.status_settings = {}
   449|        for (section, option), value in self.access_tracking.items():
   450|            self.status_settings.setdefault(section, {})[option] = value
   451|    def get_status(self, eventtime):
   452|        return {'settings': self.status_settings}
   453|
   454|
   455|######################################################################
   456|# Main printer config tracking
   457|######################################################################
   458|
   459|class PrinterConfig:
   460|    def __init__(self, printer):
   461|        self.printer = printer
   462|        self.autosave = ConfigAutoSave(printer)
   463|        self.validate = ConfigValidate(printer)
   464|        self.deprecated = {}
   465|        self.status_raw_config = {}
   466|        self.status_warnings = []
   467|    def get_printer(self):
   468|        return self.printer
   469|    def read_config(self, filename):
   470|        cfgrdr = ConfigFileReader()
   471|        data = cfgrdr.read_config_file(filename)
   472|        fileconfig = cfgrdr.build_fileconfig(data, filename)
   473|        return ConfigWrapper(self.printer, fileconfig, {}, 'printer')
   474|    def read_main_config(self):
   475|        fileconfig, autosave_fileconfig = self.autosave.load_main_config()
   476|        access_tracking = self.validate.start_access_tracking(
   477|            autosave_fileconfig)
   478|        config = ConfigWrapper(self.printer, fileconfig,
   479|                               access_tracking, 'printer')
   480|        self._build_status_config(config)
   481|        return config
   482|    def log_config(self, config):
   483|        cfgrdr = ConfigFileReader()
   484|        lines = ["===== Config file =====",
   485|                 cfgrdr.build_config_string(config.fileconfig),
   486|                 "======================="]
   487|        self.printer.set_rollover_info("config", "\n".join(lines))
   488|    def check_unused_options(self, config):
   489|        self.validate.check_unused(config.fileconfig)
   490|    # Deprecation warnings
   491|    def _add_deprecated(self, data):
   492|        key = tuple(list(data.items()))
   493|        if key in self.deprecated:
   494|            return False
   495|        self.deprecated[key] = True
   496|        self.status_warnings = self.status_warnings + [data]
   497|        return True
   498|    def runtime_warning(self, msg):
   499|        res = {'type': 'runtime_warning', 'message': msg}
   500|        did_add = self._add_deprecated(res)
   501|