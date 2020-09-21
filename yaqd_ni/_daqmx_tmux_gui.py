# type: ignore
import pathlib


# --- define --------------------------------------------------------------------------------------


__here__ = pathlib.Path(__file__).parent

app = g.app.read()
ini = Ini(os.path.join(__here__, "PCI-6251.ini"))

DAQ_device_name = ini.read("DAQ", "device name")

# TODO: actually read these values from the driver ---Blaise 2017-01-06
ranges = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]  # V
resolution = {}  # uV
resolution[0.1] = 3.2
resolution[0.2] = 6.4
resolution[0.5] = 16.0
resolution[1.0] = 32.0
resolution[2.0] = 64.0
resolution[5.0] = 160.0
resolution[10.0] = 320.0


# --- data mutex objects --------------------------------------------------------------------------


data = pc.Data()
shots = pc.Data()
samples = pc.Mutex()


# --- special objects -----------------------------------------------------------------------------


rest_channel = pc.Number(
    decimals=0,
    ini=ini,
    section="DAQ",
    option="rest channel",
    limits=pc.NumberLimits(0, 7, None),
    import_from_ini=True,
    save_to_ini_at_shutdown=True,
)


class Channel:
    def __init__(self, index):
        self.index = index
        ini_section = " ".join(["Channel", str(self.index)])
        self.section = ini_section
        self.active = pc.Bool(ini=ini, section=ini_section, option="active")
        self.name = pc.String(inital_value="Name", ini=ini, section=ini_section, option="name")
        self.physical_correspondance = pc.Number(
            decimals=0,
            limits=pc.NumberLimits(0, 7, None),
            ini=ini,
            section=ini_section,
            option="physical correspondance",
        )
        allowed_ranges = ["%0.1f (%0.1f)" % (r, resolution[r]) for r in ranges]
        self.range = pc.Combo(
            allowed_values=allowed_ranges, ini=ini, section=ini_section, option="range"
        )
        # TODO: resolution display
        self.invert = pc.Bool(ini=ini, section=ini_section, option="invert")
        sample_limits = pc.NumberLimits(0, 899, None)
        self.signal_start_index = pc.Number(
            decimals=0, limits=sample_limits, ini=ini, section=ini_section, option="signal start",
        )
        self.signal_stop_index = pc.Number(
            decimals=0, limits=sample_limits, ini=ini, section=ini_section, option="signal stop",
        )
        self.signal_pre_index = pc.Number(
            decimals=0,
            limits=sample_limits,
            ini=ini,
            section=ini_section,
            option="signal presample",
        )
        processing_methods = ["Average", "Sum", "Min", "Max"]
        self.signal_method = pc.Combo(
            allowed_values=processing_methods,
            ini=ini,
            section=ini_section,
            option="signal method",
        )
        self.use_baseline = pc.Bool(ini=ini, section=ini_section, option="use baseline")
        self.baseline_start_index = pc.Number(
            decimals=0,
            limits=sample_limits,
            ini=ini,
            section=ini_section,
            option="baseline start",
        )
        self.baseline_stop_index = pc.Number(
            decimals=0, limits=sample_limits, ini=ini, section=ini_section, option="baseline stop",
        )
        self.baseline_pre_index = pc.Number(
            decimals=0,
            limits=sample_limits,
            ini=ini,
            section=ini_section,
            option="baseline presample",
        )
        self.baseline_method = pc.Combo(
            allowed_values=processing_methods,
            ini=ini,
            section=ini_section,
            option="baseline method",
        )
        # a list of all properties
        self.properties = [
            self.active,
            self.name,
            self.physical_correspondance,
            self.range,
            self.invert,
            self.signal_start_index,
            self.signal_stop_index,
            self.signal_method,
            self.signal_pre_index,
            self.use_baseline,
            self.baseline_method,
            self.baseline_pre_index,
            self.baseline_start_index,
            self.baseline_stop_index,
        ]
        # call get saved on self
        self.get_saved()
        # signals
        self.use_baseline.updated.connect(lambda: self.on_use_baseline())
        self.on_use_baseline()

    def get_range(self):
        """
        Returns
        -------
        tuple
            (minimum_voltage, maximum_voltage)
        """
        r = ranges[self.range.read_index()]
        return -r, r

    def get_saved(self):
        for obj in self.properties:
            obj.get_saved()

    def get_widget(self):
        self.input_table = pw.InputTable()
        self.input_table.add("Name", self.name)
        self.input_table.add("Physical Channel", self.physical_correspondance)
        self.input_table.add("Range +/-V, (uV/level)", self.range)
        # TODO: resolution display
        self.input_table.add("Invert", self.invert)
        self.input_table.add("Signal Start", self.signal_start_index)
        self.input_table.add("Signal Stop", self.signal_stop_index)
        self.input_table.add("Signal Presample", self.signal_pre_index)
        self.input_table.add("Signal Method", self.signal_method)
        self.input_table.add("Use Baseline", self.use_baseline)
        self.input_table.add("Baseline Start", self.baseline_start_index)
        self.input_table.add("Baseline Stop", self.baseline_stop_index)
        self.input_table.add("Baseline Presample", self.baseline_pre_index)
        self.input_table.add("Baseline Method", self.baseline_method)
        return self.input_table

    def on_use_baseline(self):
        self.baseline_method.set_disabled(not self.use_baseline.read())
        self.baseline_start_index.set_disabled(not self.use_baseline.read())
        self.baseline_stop_index.set_disabled(not self.use_baseline.read())
        self.baseline_pre_index.set_disabled(not self.use_baseline.read())

    def save(self):
        for obj in self.properties:
            obj.save()


channels = pc.Mutex([Channel(i) for i in range(8)])
destination_channels = pc.Mutex([Channel(i) for i in range(8)])


class Chopper:
    def __init__(self, index):
        self.index = index
        ini_section = " ".join(["Chopper", str(self.index)])
        self.section = ini_section
        self.active = pc.Bool(ini=ini, section=ini_section, option="active")
        self.name = pc.String(inital_value="Name", ini=ini, section=ini_section, option="name")
        self.physical_correspondance = pc.Number(
            decimals=0,
            limits=pc.NumberLimits(0, 7, None),
            ini=ini,
            section=ini_section,
            option="physical correspondance",
        )
        self.invert = pc.Bool(ini=ini, section=ini_section, option="invert")
        sample_limits = pc.NumberLimits(0, 899, None)
        self.index = pc.Number(
            decimals=0, limits=sample_limits, ini=ini, section=ini_section, option="index",
        )
        # a list of all properties
        self.properties = [
            self.active,
            self.name,
            self.physical_correspondance,
            self.invert,
            self.index,
        ]
        # call get saved on self
        self.get_saved()

    def get_saved(self):
        for obj in self.properties:
            obj.get_saved()

    def get_widget(self):
        self.input_table = pw.InputTable()
        self.input_table.add("Name", self.name)
        self.input_table.add("Physical Channel", self.physical_correspondance)
        self.input_table.add("Invert", self.invert)
        self.input_table.add("Index", self.index)
        return self.input_table

    def save(self):
        for obj in self.properties:
            obj.save()


choppers = pc.Mutex([Chopper(i) for i in range(7)])
destination_choppers = pc.Mutex([Chopper(i) for i in range(7)])


# shots
shot_channel_combo = pc.Combo()
shots_processing_module_path = pc.Filepath(
    ini=ini,
    section="DAQ",
    option="shots processing module path",
    import_from_ini=True,
    save_to_ini_at_shutdown=True,
    options=["*.py"],
)
seconds_for_shots_processing = pc.Number(initial_value=np.nan, display=True, decimals=3)
save_shots_bool = pc.Bool(
    ini=ini,
    section="DAQ",
    option="save shots",
    display=True,
    import_from_ini=True,
    save_to_ini_at_shutdown=True,
)

axes = pc.Mutex()

origin = pc.Mutex()

# daq
nshots = pc.Number(
    initial_value=np.nan,
    ini=ini,
    section="DAQ",
    option="Shots",
    disable_under_module_control=True,
    decimals=0,
)
nsamples = pc.Number(
    initial_value=np.nan, ini=ini, section="DAQ", option="samples", decimals=0, display=True,
)
scan_index = pc.Number(initial_value=0, display=True, decimals=0)

# sample correspondances holds an array of integers
# zero : rest sample
# positive : channel
# negative : chopper
sample_correspondances = pc.Mutex(initial_value=np.zeros(nsamples.read()))

freerun = pc.Bool(initial_value=False)

# additional
seconds_since_last_task = pc.Number(initial_value=np.nan, display=True, decimals=3)
seconds_for_acquisition = pc.Number(initial_value=np.nan, display=True, decimals=3)


class GUI(BaseGUI):
    samples_tab_initialized = False

    def create_frame(self, parent_widget):
        # get layout
        parent_widget.setLayout(QtWidgets.QHBoxLayout())
        parent_widget.layout().setContentsMargins(0, 10, 0, 0)
        layout = parent_widget.layout()
        # create tab structure
        self.tabs = QtWidgets.QTabWidget()
        # samples tab
        samples_widget = QtWidgets.QWidget()
        samples_box = QtWidgets.QHBoxLayout()
        samples_box.setContentsMargins(0, 10, 0, 0)
        samples_widget.setLayout(samples_box)
        self.tabs.addTab(samples_widget, "Samples")
        self.create_samples_tab(samples_box)
        # shots tab
        shots_widget = QtWidgets.QWidget()
        shots_box = QtWidgets.QHBoxLayout()
        shots_box.setContentsMargins(0, 10, 0, 0)
        shots_widget.setLayout(shots_box)
        self.tabs.addTab(shots_widget, "Shots")
        self.create_shots_tab(shots_box)
        # finish
        layout.addWidget(self.tabs)
        self.samples_channel_combo.updated.connect(self.update_samples_tab)
        self.samples_chopper_combo.updated.connect(self.update_samples_tab)
        self.hardware.update_ui.connect(self.update)
        self.update_samples_tab()

    def create_samples_tab(self, layout):
        # display -------------------------------------------------------------
        # container widget
        display_container_widget = pw.ExpandingWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setMargin(0)
        layout.addWidget(display_container_widget)
        # plot
        self.samples_plot_widget = pw.Plot1D(yAutoRange=False)
        self.samples_plot_scatter = self.samples_plot_widget.add_scatter(color=0.25)
        self.samples_plot_active_scatter = self.samples_plot_widget.add_scatter()
        self.samples_plot_widget.set_labels(xlabel="sample", ylabel="volts")
        self.samples_plot_max_voltage_line = self.samples_plot_widget.add_infinite_line(
            color="y", angle=0
        )
        self.samples_plot_min_voltage_line = self.samples_plot_widget.add_infinite_line(
            color="y", angle=0
        )
        self.samples_plot_signal_stop_line = self.samples_plot_widget.add_infinite_line(color="r")
        self.samples_plot_signal_start_line = self.samples_plot_widget.add_infinite_line(color="g")
        self.samples_plot_baseline_stop_line = self.samples_plot_widget.add_infinite_line(
            color="r", style="dashed"
        )
        self.samples_plot_baseline_start_line = self.samples_plot_widget.add_infinite_line(
            color="g", style="dashed"
        )
        self.samples_plot_chopper_line = self.samples_plot_widget.add_infinite_line(color="b")
        display_layout.addWidget(self.samples_plot_widget)
        legend = self.samples_plot_widget.plot_object.addLegend()
        legend.addItem(self.samples_plot_active_scatter, "channel samples")
        legend.addItem(self.samples_plot_scatter, "other samples")
        style = pg.PlotDataItem(pen="y")
        legend.addItem(style, "voltage limits")
        style = pg.PlotDataItem(pen="g")
        legend.addItem(style, "signal start")
        style = pg.PlotDataItem(pen="r")
        legend.addItem(style, "signal stop")
        pen = pg.mkPen("g", style=QtCore.Qt.DashLine)
        style = pg.PlotDataItem(pen=pen)
        legend.addItem(style, "baseline start")
        pen = pg.mkPen("r", style=QtCore.Qt.DashLine)
        style = pg.PlotDataItem(pen=pen)
        legend.addItem(style, "baseline stop")
        style = pg.PlotDataItem(pen="b")
        legend.addItem(style, "chopper index")
        # vertical line -------------------------------------------------------
        line = pw.line("V")
        layout.addWidget(line)
        # settings area -------------------------------------------------------
        # container widget / scroll area
        settings_container_widget = QtWidgets.QWidget()
        settings_scroll_area = pw.scroll_area(130)
        settings_scroll_area.setWidget(settings_container_widget)
        settings_scroll_area.setMinimumWidth(300)
        settings_scroll_area.setMaximumWidth(300)
        settings_container_widget.setLayout(QtWidgets.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setMargin(5)
        layout.addWidget(settings_scroll_area)
        input_table = pw.InputTable()
        input_table.add("Display", None)
        self.sample_shots_displayed = pc.Number(
            initial_value=1, limits=pc.NumberLimits(1, 10), decimals=0, display=True
        )
        self.sample_shots_displayed.updated.connect(self.on_sample_shots_displayed_updated)
        input_table.add("Shots Displayed", self.sample_shots_displayed)
        input_table.add("Settings", None)
        input_table.add("Samples per Shot", nsamples)
        input_table.add("Rest Channel", rest_channel)
        settings_layout.addWidget(input_table)
        # channels
        line = pw.line("H")
        settings_layout.addWidget(line)
        # channel_combobox
        allowed_values = [channel.section for channel in channels.read() if channel.active.read()]
        self.samples_channel_combo = pc.Combo(allowed_values=allowed_values)
        self.samples_channel_combo.updated.connect(self.on_sample_shots_displayed_updated)
        self.on_sample_shots_displayed_updated()
        input_table = pw.InputTable()
        input_table.add("Channel", self.samples_channel_combo)
        settings_layout.addWidget(input_table)
        # add button
        self.add_channel_button = pw.SetButton("ADD CHANNEL")
        settings_layout.addWidget(self.add_channel_button)
        self.add_channel_button.clicked.connect(self.on_add_channel)
        # remove button
        self.remove_channel_button = pw.SetButton("REMOVE TRAILING CHANNEL", "stop")
        settings_layout.addWidget(self.remove_channel_button)
        self.remove_channel_button.clicked.connect(self.on_remove_channel)
        # channel widgets
        self.channel_widgets = []
        for channel in destination_channels.read():
            widget = channel.get_widget()
            settings_layout.addWidget(widget)
            widget.hide()
            self.channel_widgets.append(widget)
        # apply button
        self.apply_channel_button = pw.SetButton("APPLY CHANGES")
        self.apply_channel_button.clicked.connect(self.on_apply_channel)
        settings_layout.addWidget(self.apply_channel_button)
        # revert button
        self.revert_channel_button = pw.SetButton("REVERT CHANGES", "stop")
        self.revert_channel_button.clicked.connect(self.on_revert_channel)
        settings_layout.addWidget(self.revert_channel_button)
        # dividing line
        line = pw.line("H")
        settings_layout.addWidget(line)
        # chopper_combobox
        allowed_values = [
            chopper.section for chopper in destination_choppers.read() if chopper.active.read()
        ]
        self.samples_chopper_combo = pc.Combo(allowed_values=allowed_values)
        input_table = pw.InputTable()
        input_table.add("Chopper", self.samples_chopper_combo)
        settings_layout.addWidget(input_table)
        # add button
        self.add_chopper_button = pw.SetButton("ADD CHOPPER")
        settings_layout.addWidget(self.add_chopper_button)
        self.add_chopper_button.clicked.connect(self.on_add_chopper)
        # remove button
        self.remove_chopper_button = pw.SetButton("REMOVE TRAILING CHOPPER", "stop")
        settings_layout.addWidget(self.remove_chopper_button)
        self.remove_chopper_button.clicked.connect(self.on_remove_chopper)
        # chopper widgets
        self.chopper_widgets = []
        for chopper in destination_choppers.read():
            widget = chopper.get_widget()
            settings_layout.addWidget(widget)
            widget.hide()
            self.chopper_widgets.append(widget)
        # apply button
        self.apply_chopper_button = pw.SetButton("APPLY CHANGES")
        self.apply_chopper_button.clicked.connect(self.on_apply_chopper)
        settings_layout.addWidget(self.apply_chopper_button)
        # revert button
        self.revert_chopper_button = pw.SetButton("REVERT CHANGES", "stop")
        self.revert_chopper_button.clicked.connect(self.on_revert_chopper)
        settings_layout.addWidget(self.revert_chopper_button)
        # finish --------------------------------------------------------------
        settings_layout.addStretch(1)

    def create_shots_tab(self, layout):
        # display -------------------------------------------------------------
        # container widget
        display_container_widget = pw.ExpandingWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setMargin(0)
        layout.addWidget(display_container_widget)
        # plot
        self.shots_plot_widget = pw.Plot1D()
        self.shots_plot_scatter = self.shots_plot_widget.add_scatter()
        self.shots_plot_widget.set_labels(xlabel="shot", ylabel="volts")
        display_layout.addWidget(self.shots_plot_widget)
        # vertical line -------------------------------------------------------
        line = pw.line("V")
        layout.addWidget(line)
        # settings ------------------------------------------------------------
        # container widget / scroll area
        settings_container_widget = QtWidgets.QWidget()
        settings_scroll_area = pw.scroll_area()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_scroll_area.setMinimumWidth(300)
        settings_scroll_area.setMaximumWidth(300)
        settings_container_widget.setLayout(QtWidgets.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setMargin(5)
        layout.addWidget(settings_scroll_area)
        # input table
        input_table = pw.InputTable()
        input_table.add("Display", None)
        input_table.add("Channel", shot_channel_combo)
        shot_channel_combo.updated.connect(self.on_shot_channel_updated)
        input_table.add("Settings", None)
        input_table.add("Shots", nshots)
        input_table.add("Save Shots", save_shots_bool)
        input_table.add("Shot Processing", shots_processing_module_path)
        input_table.add("Processing Time", seconds_for_shots_processing)
        settings_layout.addWidget(input_table)
        # finish --------------------------------------------------------------
        settings_layout.addStretch(1)
        shot_channel_combo.updated.emit()

    def on_add_channel(self):
        allowed_values = [
            channel.section for channel in destination_channels.read() if channel.active.read()
        ]
        new_channel_section = "Channel %i" % len(allowed_values)
        allowed_values.append(new_channel_section)
        self.samples_channel_combo.set_allowed_values(allowed_values)
        self.samples_channel_combo.write(new_channel_section)
        # do not activate channel until changes are applied
        self.update_samples_tab()

    def on_add_chopper(self):
        allowed_values = [
            chopper.section for chopper in destination_choppers.read() if chopper.active.read()
        ]
        new_chopper_section = "Chopper %i" % len(allowed_values)
        allowed_values.append(new_chopper_section)
        self.samples_chopper_combo.set_allowed_values(allowed_values)
        self.samples_chopper_combo.write(new_chopper_section)
        # do not activate chopper until changes are applied
        self.update_samples_tab()

    def on_apply_channel(self):
        new_channel_index = int(self.samples_channel_combo.read()[-1])
        new_channel = destination_channels.read()[new_channel_index]
        new_channel.active.write(True)
        new_channels = copy.copy(channels.read())
        new_channels[new_channel_index] = new_channel
        self.hardware.update_sample_correspondances(new_channels, choppers.read())
        self.update_samples_tab()

    def on_apply_chopper(self):
        new_chopper_index = int(self.samples_chopper_combo.read()[-1])
        new_chopper = destination_choppers.read()[new_chopper_index]
        new_chopper.active.write(True)
        new_choppers = copy.copy(choppers.read())
        new_choppers[new_chopper_index] = new_chopper
        self.hardware.update_sample_correspondances(channels.read(), new_choppers)
        self.update_samples_tab()

    def on_remove_channel(self):
        # loop through channels backwards
        for channel in channels.read()[::-1]:
            if channel.active.read():
                channel.get_saved()  # revert to saved
                channel.active.write(False)
                channel.save()
                break
        self.hardware.update_sample_correspondances(channels.read(), choppers.read())
        allowed_values = [
            channel.section for channel in destination_channels.read() if channel.active.read()
        ]
        self.samples_channel_combo.set_allowed_values(allowed_values)
        self.samples_channel_combo.write(allowed_values[-1])
        self.update_samples_tab()

    def on_remove_chopper(self):
        # loop through choppers backwards
        for chopper in choppers.read()[::-1]:
            if chopper.active.read():
                chopper.get_saved()  # revert to saved
                chopper.active.write(False)
                chopper.save()
                break
        self.hardware.update_sample_correspondances(channels.read(), choppers.read())
        allowed_values = [
            chopper.section for chopper in destination_choppers.read() if chopper.active.read()
        ]
        self.samples_chopper_combo.set_allowed_values(allowed_values)
        self.samples_chopper_combo.write(allowed_values[-1])
        self.update_samples_tab()

    def on_revert_channel(self):
        channel_index = int(self.samples_channel_combo.read()[-1])
        destination_channels.read()[channel_index].get_saved()

    def on_revert_chopper(self):
        chopper_index = int(self.samples_chopper_combo.read()[-1])
        destination_choppers.read()[chopper_index].get_saved()

    def on_sample_shots_displayed_updated(self):
        # all samples
        self.sample_xi = list(range(nsamples.read())) * int(self.sample_shots_displayed.read())
        # signal samples
        current_channel_object = channels.read()[self.samples_channel_combo.read_index()]
        signal_start_index = int(current_channel_object.signal_start_index.read())
        signal_stop_index = int(current_channel_object.signal_stop_index.read())
        self.signal_indicies = np.array(
            [
                i
                for i in np.arange(signal_start_index, signal_stop_index)
                if sample_correspondances.read()[i] == self.samples_channel_combo.read_index() + 1
            ],
            dtype=np.int,
        )
        self.signal_xi = list(self.signal_indicies) * int(self.sample_shots_displayed.read())
        for i in range(1, int(self.sample_shots_displayed.read())):
            self.signal_indicies = np.hstack(
                (self.signal_indicies, self.signal_indicies + i * nsamples.read())
            )
        # baseline samples
        baseline_start_index = int(current_channel_object.baseline_start_index.read())
        baseline_stop_index = int(current_channel_object.baseline_stop_index.read())
        self.baseline_indicies = np.array(
            [
                i
                for i in np.arange(baseline_start_index, baseline_stop_index)
                if sample_correspondances.read()[i] == self.samples_channel_combo.read_index() + 1
            ],
            dtype=np.int,
        )
        self.baseline_xi = list(self.baseline_indicies) * int(self.sample_shots_displayed.read())
        for i in range(1, int(self.sample_shots_displayed.read())):
            self.baseline_indicies = np.hstack(
                (self.baseline_indicies, self.baseline_indicies + i * nsamples.read())
            )

    def on_shot_channel_updated(self):
        # update y range to be range of channel
        channel_index = shot_channel_combo.read_index()
        active_channels = [channel for channel in channels.read() if channel.active.read()]
        if channel_index > len(active_channels) - 1:
            # must be a chopper
            ymin = -1
            ymax = 1
        else:
            # is a channel
            channel = active_channels[channel_index]
            ymin, ymax = channel.get_range()
        self.shots_plot_widget.set_ylim(ymin * 1.05, ymax * 1.05)

    def set_slice_xlim(self, xmin, xmax):
        self.values_plot_widget.set_xlim(xmin, xmax)

    def update(self):
        """
        Runs each time an update_ui signal fires (basically every run_task)
        """
        # TODO: I need this check for a race condition during startup that I
        # do not understand. Eventually it should be removed.
        # - Blaise 2016.01.30
        if samples.read() is None:
            return
        # all samples
        yi = samples.read()[: nsamples.read() * self.sample_shots_displayed.read()]
        self.samples_plot_scatter.clear()
        self.samples_plot_scatter.setData(self.sample_xi, yi)
        # active samples
        self.samples_plot_active_scatter.hide()
        current_channel_object = channels.read()[self.samples_channel_combo.read_index()]
        if current_channel_object.active.read():
            self.samples_plot_active_scatter.show()
            xi = self.signal_xi
            yi = samples.read()[self.signal_indicies]
            if current_channel_object.use_baseline.read():
                xi = np.hstack((xi, self.baseline_xi))
                yi = np.hstack((yi, samples.read()[self.baseline_indicies]))
            self.samples_plot_active_scatter.setData(xi, yi)
        # shots
        yi = shots.read()[int(shot_channel_combo.read_index())]
        xi = np.arange(len(yi))
        self.shots_plot_scatter.clear()
        self.shots_plot_scatter.setData(xi, yi)
        # finish
        if not self.samples_tab_initialized:
            self.update_samples_tab()

    def update_samples_tab(self):
        # TODO: I need this check for a race condition during startup that I
        # do not understand. Eventually it should be removed.
        # - Blaise 2016-01-30
        if samples.read() is None:
            return
        else:
            self.samples_tab_initialized = True
        # buttons
        num_channels = len(self.samples_channel_combo.allowed_values)
        self.add_channel_button.setDisabled(False)
        self.remove_channel_button.setDisabled(False)
        if num_channels == 8:
            self.add_channel_button.setDisabled(True)
        elif num_channels == 1:
            self.remove_channel_button.setDisabled(True)
        # channel ui
        channel_index = int(self.samples_channel_combo.read()[-1])
        for widget in self.channel_widgets:
            widget.hide()
        self.channel_widgets[channel_index].show()
        # chopper ui
        chopper_index = int(self.samples_chopper_combo.read()[-1])
        for widget in self.chopper_widgets:
            widget.hide()
        self.chopper_widgets[chopper_index].show()
        # lines on plot
        self.samples_plot_max_voltage_line.hide()
        self.samples_plot_min_voltage_line.hide()
        self.samples_plot_signal_start_line.hide()
        self.samples_plot_signal_stop_line.hide()
        self.samples_plot_baseline_start_line.hide()
        self.samples_plot_baseline_stop_line.hide()
        self.samples_plot_chopper_line.hide()
        current_channel_object = channels.read()[channel_index]
        if current_channel_object.active.read():
            channel_min, channel_max = current_channel_object.get_range()
            self.samples_plot_max_voltage_line.show()
            self.samples_plot_max_voltage_line.setValue(channel_max * 1.05)
            self.samples_plot_min_voltage_line.show()
            self.samples_plot_min_voltage_line.setValue(channel_min * 1.05)
            self.samples_plot_signal_start_line.show()
            self.samples_plot_signal_start_line.setValue(
                current_channel_object.signal_start_index.read()
            )
            self.samples_plot_signal_stop_line.show()
            self.samples_plot_signal_stop_line.setValue(
                current_channel_object.signal_stop_index.read()
            )
            if current_channel_object.use_baseline.read():
                self.samples_plot_baseline_start_line.show()
                self.samples_plot_baseline_start_line.setValue(
                    current_channel_object.baseline_start_index.read()
                )
                self.samples_plot_baseline_stop_line.show()
                self.samples_plot_baseline_stop_line.setValue(
                    current_channel_object.baseline_stop_index.read()
                )
        current_chopper_object = choppers.read()[chopper_index]
        if current_chopper_object.active.read():
            self.samples_plot_chopper_line.show()
            self.samples_plot_chopper_line.setValue(current_chopper_object.index.read())
        # finish
        ymin, ymax = current_channel_object.get_range()
        self.samples_plot_widget.set_ylim(ymin, ymax)
        self.on_sample_shots_displayed_updated()
        if not freerun.read():
            self.update()

    def stop(self):
        pass
