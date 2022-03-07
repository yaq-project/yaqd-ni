"""Qt based GUI client for ni-daqmx-tmux."""

import sys
import pathlib

from qtpy import QtCore, QtGui, QtWidgets  # type: ignore
import pyqtgraph as pg  # type: ignore
import qtypes  # type: ignore
import yaqc  # type: ignore
import toml
import numpy as np  # type: ignore


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


class Channel:
    def __init__(
        self,
        channel,
        enabled,
        name,
        invert,
        signal_start,
        signal_stop,
        signal_presample,
        signal_method,
        use_baseline,
        baseline_start,
        baseline_stop,
        baseline_presample,
        baseline_method,
        range,
        nsamples,
    ):
        self.enabled = qtypes.Bool("Enabled", True, value={"value": enabled})
        self.name = qtypes.String(channel, True, value={"value": name})
        self.physical_correspondance = qtypes.Integer(
            "Physical correspondance", True, value={"minimum": 0, "maximum": 7}
        )
        allowed_ranges = ["%0.1f (%0.1f)" % (r, resolution[r]) for r in ranges]
        self.range = qtypes.Enum("Range", True, value={"allowed": allowed_ranges})
        # TODO: resolution display
        self.invert = qtypes.Bool("invert", True, value={"value": invert})
        sample_limits = value = {"minimum": 0, "maximum": nsamples - 1}
        self.signal_start_index = qtypes.Integer(
            "signal start index", True, value={"value": signal_start, **sample_limits}
        )
        self.signal_stop_index = qtypes.Integer(
            "signal stop index", True, value={"value": signal_stop, **sample_limits}
        )
        self.signal_pre_index = qtypes.Integer(
            "signal pre index", True, value={"value": signal_presample, **sample_limits}
        )

        processing_methods = ["Average", "Sum", "Min", "Max"]  # TODO: source from avpr
        self.signal_method = qtypes.Enum(
            "processing", True, value={"allowed": processing_methods, "value": signal_method}
        )
        self.use_baseline = qtypes.Bool("Use Baseline", True, value={"value": use_baseline})
        self.baseline_start_index = qtypes.Integer(
            "baseline start index", True, value={"value": baseline_start, **sample_limits}
        )
        self.baseline_stop_index = qtypes.Integer(
            "baseline stop index", True, value={"value": baseline_stop, **sample_limits}
        )
        self.baseline_pre_index = qtypes.Integer(
            "baseline pre index", True, value={"value": baseline_presample, **sample_limits}
        )
        self.baseline_method = qtypes.Enum(
            "processing", True, value={"allowed": processing_methods, "value": baseline_method}
        )
        # signals
        self.use_baseline.updated.connect(lambda x: self.on_use_baseline())
        self.on_use_baseline()

    @property
    def baseline_start(self):
        return self.baseline_start_index.get_value() - self.baseline_pre_index.get_value()

    @property
    def baseline_stop(self):
        return self.baseline_stop_index.get_value()

    def get_range(self):
        """
        Returns
        -------
        tuple
            (minimum_voltage, maximum_voltage)
        """
        allowed = self.range.get()["allowed"]
        r = ranges[allowed.index(self.range.get_value())]
        return -r, r

    def get_widget(self, tree):
        self.tree_widget = tree
        self.tree_widget.append(self.name)
        self.name.append(self.range)
        # TODO: resolution display
        self.name.append(self.invert)
        self.name.append(self.signal_start_index)
        self.name.append(self.signal_stop_index)
        self.name.append(self.signal_pre_index)
        self.name.append(self.signal_method)
        self.name.append(self.use_baseline)
        self.name.append(self.baseline_start_index)
        self.name.append(self.baseline_stop_index)
        self.name.append(self.baseline_pre_index)
        self.name.append(self.baseline_method)
        return self.name

    def on_use_baseline(self):
        self.baseline_method.setDisabled(not self.use_baseline.get_value())
        self.baseline_start_index.setDisabled(not self.use_baseline.get_value())
        self.baseline_stop_index.setDisabled(not self.use_baseline.get_value())
        self.baseline_pre_index.setDisabled(not self.use_baseline.get_value())

    @property
    def signal_start(self):
        return self.signal_start_index.get_value() - self.signal_pre_index.get_value()

    @property
    def signal_stop(self):
        return self.signal_stop_index.get_value()


class Chopper:
    def __init__(self, channel, index, enabled, invert, name, nsamples):
        self.enabled = qtypes.Bool("Enabled", True, value={"value": enabled})
        self.name = qtypes.String(channel, True, value={"value": name})
        self.invert = qtypes.Bool("Invert", True, value={"value": invert})
        self.index = qtypes.Integer(
            "Index", True, value={"value": index, "minimum": 0, "maxiumum": nsamples - 1}
        )

    def get_widget(self, tree):
        self.tree_widget = tree
        self.tree_widget.append(self.name)
        self.name.append(self.invert)
        self.name.append(self.index)
        return self.name

    def save(self):
        for obj in self.properties:
            obj.save()


class ConfigWidget(QtWidgets.QWidget):
    def __init__(self, port, host="localhost"):
        super().__init__()
        self.host = host
        self.port = port
        self.client = yaqc.Client(self.port, host)
        self.client.measure(loop=True)
        config = toml.loads(self.client.get_config())
        self.nsamples = config["nsamples"]
        self.channels = {}
        for k, d in config["channels"].items():
            if d["name"] is None:
                d["name"] = k
            self.channels[k] = Channel(k, **d, nsamples=self.nsamples)
        self.choppers = {}
        for k, d in config["choppers"].items():
            if d["name"] is None:
                d["name"] = k
            self.choppers[k] = Chopper(k, **d, nsamples=self.nsamples)
        self.create_frame()
        self.rest_channel.set_value(config["rest_channel"])
        self.poll_timer = QtCore.QTimer()
        self.poll_timer.start(100)  # milliseconds
        self.poll_timer.timeout.connect(self.update)

    def create_frame(self):
        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 10, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        # samples tab
        samples_widget = QtWidgets.QSplitter()
        self.tabs.addTab(samples_widget, "Samples")
        self.create_samples_tab(samples_widget)
        # shots tab
        shots_widget = QtWidgets.QSplitter()
        self.tabs.addTab(shots_widget, "Shots")
        self.create_shots_tab(shots_widget)
        # finish
        self.layout().addWidget(self.tabs)
        self.samples_channel_combo.updated.connect(self.update_samples_tab)
        self.samples_chopper_combo.updated.connect(self.update_samples_tab)
        self.update_samples_tab()

    def create_samples_tab(self, layout):
        # container widget
        display_container_widget = QtWidgets.QWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        layout.addWidget(display_container_widget)
        # plot
        self.samples_plot_widget = Plot1D(yAutoRange=False)
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
        # settings area -------------------------------------------------------
        # container widget / scroll area
        tree_widget = qtypes.TreeWidget()
        heading = qtypes.Null("Settings")
        tree_widget.append(heading)
        heading.setExpanded(True)
        self.rest_channel = qtypes.String("Rest Channel", True)
        heading.append(self.rest_channel)
        layout.addWidget(tree_widget)
        # channel_combobox
        allowed_values = list(self.channels.keys())
        self.samples_channel_combo = qtypes.Enum("Channels", value={"allowed": allowed_values})
        heading.append(self.samples_channel_combo)
        self.samples_channel_combo.setExpanded(True)
        # channel widgets
        self.channel_widgets = []
        for channel in self.channels.values():
            widget = channel.get_widget(self.samples_channel_combo)
            self.channel_widgets.append(widget)
        self.channel_widgets[0].setExpanded(True)
        # apply button
        # self.apply_channel_button = qtypes.widgets.PushButton("APPLY CHANGES", background="green")
        # self.apply_channel_button.clicked.connect(self.write_config)
        # layout.addWidget(self.apply_channel_button)
        # chopper_combobox
        allowed_values = list(self.choppers.keys())
        self.samples_chopper_combo = qtypes.Enum("Chopper", value={"allowed": allowed_values})
        heading.append(self.samples_chopper_combo)
        self.samples_chopper_combo.setExpanded(True)
        # chopper widgets
        self.chopper_widgets = []
        for chopper in self.choppers.values():
            widget = chopper.get_widget(self.samples_chopper_combo)
            self.chopper_widgets.append(widget)
        self.chopper_widgets[0].setExpanded(True)
        # apply button
        # self.apply_chopper_button = qtypes.widgets.PushButton("APPLY CHANGES", background="green")
        # self.apply_chopper_button.clicked.connect(self.write_config)
        # layout.addWidget(self.apply_chopper_button)
        self.sample_xi = np.arange(self.nsamples)

    def create_shots_tab(self, layout):
        # container widget
        display_container_widget = QtWidgets.QWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(display_container_widget)
        # plot
        self.shots_plot_widget = Plot1D()
        self.shots_plot_scatter = self.shots_plot_widget.add_scatter()
        self.shots_plot_widget.set_labels(xlabel="shot", ylabel="volts")
        display_layout.addWidget(self.shots_plot_widget)
        # settings
        # container widget / scroll area
        # input table
        tree_widget = qtypes.TreeWidget()
        self.shot_channel_combo = qtypes.Enum(
            "Channel", value={"allowed": list(self.channels.keys()) + list(self.choppers.keys())}
        )
        tree_widget.append(self.shot_channel_combo)
        self.shot_channel_combo.updated.connect(self.on_shot_channel_updated)
        self.nshots = qtypes.Integer(
            "Shots", value={"value": self.client.get_nshots(), "minimum": 0}
        )
        self.nshots.updated.connect(self.on_nshots_updated)
        tree_widget.append(self.nshots)
        # self.shots_processing_module_path = qtypes.Filepath(name="Shots Processing")
        # tree_widget.append(self.shots_processing_module_path)
        layout.addWidget(tree_widget)
        # finish
        self.shot_channel_combo.updated.emit({})

    def write_config(self):
        # create dictionary, starting from existing
        config = toml.loads(self.client.get_config())
        # channels
        for k, c in config["channels"].items():
            channel = self.channels[k]
            config["channels"][k]["name"] = channel.name.get_value()
            config["channels"][k]["range"] = channel.range.get_value()
            config["channels"][k]["enabled"] = channel.enabled.get_value()
            config["channels"][k]["invert"] = channel.invert.get_value()
            config["channels"][k]["signal_start"] = channel.signal_start.get_value()
            config["channels"][k]["signal_stop"] = channel.signal_stop.get_value()
            config["channels"][k]["signal_presample"] = channel.signal_presample.get_value()
            config["channels"][k]["signal_method"] = channel.signal_method.get_value()
            config["channels"][k]["use_baseline"] = channel.use_baseline.get_value()
            config["channels"][k]["baseline_start"] = channel.baseline_start.get_value()
            config["channels"][k]["baseline_stop"] = channel.baseline_stop.get_value()
            config["channels"][k]["baseline_presample"] = channel.baseline_presample.get_value()
            config["channels"][k]["baseline_method"] = channel.baseline_method.get_value()
        # choppers
        for k, c in config["channels"].items():
            channel = self.channels[k]
            config["channels"][k]["name"] = channel.name.get_value()
            config["channels"][k]["range"] = channel.range.get_value()
            config["channels"][k]["enabled"] = channel.enabled.get_value()
            config["channels"][k]["invert"] = channel.invert.get_value()
            config["channels"][k]["signal_start"] = channel.signal_start.get_value()
            config["channels"][k]["signal_stop"] = channel.signal_stop.get_value()
            config["channels"][k]["signal_presample"] = channel.signal_presample.get_value()
            config["channels"][k]["signal_method"] = channel.signal_method.get_value()
            config["channels"][k]["use_baseline"] = channel.use_baseline.get_value()
            config["channels"][k]["baseline_start"] = channel.baseline_start.get_value()
            config["channels"][k]["baseline_stop"] = channel.baseline_stop.get_value()
            config["channels"][k]["baseline_presample"] = channel.baseline_presample.get_value()
            config["channels"][k]["baseline_method"] = channel.baseline_method.get_value()
        # write config
        # TODO:
        # recreate client
        while True:
            try:
                self.client = yaqc.Client(self.port)
            except:
                time.sleep(0.1)

    def on_nshots_updated(self):
        new = int(self.nshots.get_value())
        self.client.set_nshots(new)
        self.nshots.set_value(self.client.get_nshots())  # read back

    def on_shot_channel_updated(self, value=None):
        # update y range to be range of channel
        if not value:
            value = self.shot_channel_combo.get()
        channel_index = value["allowed"].index(value["value"])
        active_channels = [
            channel for channel in self.channels.values() if channel.enabled.get_value()
        ]
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
        # all samples
        yi = self.client.get_measured_samples()[:, 0]
        self.samples_plot_scatter.clear()
        self.samples_plot_scatter.setData(self.sample_xi, yi)
        # active samples
        # self.samples_plot_active_scatter.hide()
        current_channel_object = self.channels[self.samples_channel_combo.get_value()]
        if current_channel_object.enabled.get_value():
            self.samples_plot_active_scatter.show()
            s = slice(current_channel_object.signal_start, current_channel_object.signal_stop, 1)
            xi = self.sample_xi[s]
            yyi = yi[:][s]
            if current_channel_object.use_baseline.get_value():
                s = slice(
                    current_channel_object.baseline_start, current_channel_object.baseline_stop, 1
                )
                xi = np.hstack([xi, self.sample_xi[s]])
                yyi = np.hstack([yyi, yi[s]])
            self.samples_plot_active_scatter.setData(xi, yyi)
        # shots
        shot_channel_options = self.shot_channel_combo.get()["allowed"]
        yi = self.client.get_measured_shots()[
            int(shot_channel_options.index(self.shot_channel_combo.get_value()))
        ]
        xi = np.arange(len(yi))
        self.shots_plot_scatter.clear()
        self.shots_plot_scatter.setData(xi, yi)

    def update_samples_tab(self):
        # buttons
        allowed = self.samples_channel_combo.get()["allowed"]
        num_channels = len(allowed)
        # channel ui
        channel_index = allowed.index(self.samples_channel_combo.get_value())
        for widget in self.channel_widgets:
            continue
            widget.hide()
        # self.channel_widgets[channel_index].show()
        # chopper ui
        chopper_allowed = self.samples_chopper_combo.get()["allowed"]
        chopper_index = chopper_allowed.index(self.samples_chopper_combo.get_value())
        for widget in self.chopper_widgets:
            continue
            widget.hide()
        # self.chopper_widgets[chopper_index].show()
        # lines on plot
        self.samples_plot_max_voltage_line.hide()
        self.samples_plot_min_voltage_line.hide()
        self.samples_plot_signal_start_line.hide()
        self.samples_plot_signal_stop_line.hide()
        self.samples_plot_baseline_start_line.hide()
        self.samples_plot_baseline_stop_line.hide()
        self.samples_plot_chopper_line.hide()
        current_channel_object = list(self.channels.values())[channel_index]
        if current_channel_object.enabled.get_value():
            channel_min, channel_max = current_channel_object.get_range()
            self.samples_plot_max_voltage_line.show()
            self.samples_plot_max_voltage_line.setValue(channel_max * 1.05)
            self.samples_plot_min_voltage_line.show()
            self.samples_plot_min_voltage_line.setValue(channel_min * 1.05)
            self.samples_plot_signal_start_line.show()
            self.samples_plot_signal_start_line.setValue(
                current_channel_object.signal_start_index.get_value()
            )
            self.samples_plot_signal_stop_line.show()
            self.samples_plot_signal_stop_line.setValue(
                current_channel_object.signal_stop_index.get_value()
            )
            if current_channel_object.use_baseline.get_value():
                self.samples_plot_baseline_start_line.show()
                self.samples_plot_baseline_start_line.setValue(
                    current_channel_object.baseline_start_index.get_value()
                )
                self.samples_plot_baseline_stop_line.show()
                self.samples_plot_baseline_stop_line.setValue(
                    current_channel_object.baseline_stop_index.get_value()
                )
        current_chopper_object = list(self.choppers.values())[chopper_index]
        if current_chopper_object.enabled.get_value():
            self.samples_plot_chopper_line.show()
            self.samples_plot_chopper_line.setValue(current_chopper_object.index.get_value())
        # finish
        ymin, ymax = current_channel_object.get_range()
        self.samples_plot_widget.set_ylim(ymin, ymax)


class Plot1D(pg.GraphicsView):
    def __init__(self, title=None, xAutoRange=True, yAutoRange=True):
        pg.GraphicsView.__init__(self)
        # create layout
        self.graphics_layout = pg.GraphicsLayout(border="w")
        self.setCentralItem(self.graphics_layout)
        self.graphics_layout.layout.setSpacing(0)
        self.graphics_layout.setContentsMargins(0.0, 0.0, 1.0, 1.0)
        # create plot object
        self.plot_object = self.graphics_layout.addPlot(0, 0)
        self.labelStyle = {"color": "#FFF", "font-size": "14px"}
        self.x_axis = self.plot_object.getAxis("bottom")
        self.x_axis.setLabel(**self.labelStyle)
        self.y_axis = self.plot_object.getAxis("left")
        self.y_axis.setLabel(**self.labelStyle)
        self.plot_object.showGrid(x=True, y=True, alpha=0.5)
        self.plot_object.setMouseEnabled(False, True)
        self.plot_object.enableAutoRange(x=xAutoRange, y=yAutoRange)
        # title
        if title:
            self.plot_object.setTitle(title)

    def add_scatter(self, color="c", size=3, symbol="o"):
        curve = pg.ScatterPlotItem(symbol=symbol, pen=(color), brush=(color), size=size)
        self.plot_object.addItem(curve)
        return curve

    def add_line(self, color="c", size=3, symbol="o"):
        curve = pg.PlotCurveItem(symbol=symbol, pen=(color), brush=(color), size=size)
        self.plot_object.addItem(curve)
        return curve

    def add_infinite_line(self, color="y", style="solid", angle=90.0, movable=False, hide=True):
        """
        Add an InfiniteLine object.
        Parameters
        ----------
        color : (optional)
            The color of the line. Accepts any argument valid for `pyqtgraph.mkColor <http://www.pyqtgraph.org/documentation/functions.html#pyqtgraph.mkColor>`_. Default is 'y', yellow.
        style : {'solid', 'dashed', dotted'} (optional)
            Linestyle. Default is solid.
        angle : float (optional)
            The angle of the line. 90 is vertical and 0 is horizontal. 90 is default.
        movable : bool (optional)
            Toggles if user can move the line. Default is False.
        hide : bool (optional)
            Toggles if the line is hidden upon initialization. Default is True.
        Returns
        -------
        InfiniteLine object
            Useful methods: setValue, show, hide
        """
        if style == "solid":
            linestyle = QtCore.Qt.SolidLine
        elif style == "dashed":
            linestyle = QtCore.Qt.DashLine
        elif style == "dotted":
            linestyle = QtCore.Qt.DotLine
        else:
            print("style not recognized in add_infinite_line")
            linestyle = QtCore.Qt.SolidLine
        pen = pg.mkPen(color, style=linestyle)
        line = pg.InfiniteLine(pen=pen)
        line.setAngle(angle)
        line.setMovable(movable)
        if hide:
            line.hide()
        self.plot_object.addItem(line)
        return line

    def set_labels(self, xlabel=None, ylabel=None):
        if xlabel:
            self.plot_object.setLabel("bottom", text=xlabel)
            self.plot_object.showLabel("bottom")
        if ylabel:
            self.plot_object.setLabel("left", text=ylabel)
            self.plot_object.showLabel("left")

    def set_xlim(self, xmin, xmax):
        self.plot_object.setXRange(xmin, xmax)

    def set_ylim(self, ymin, ymax):
        self.plot_object.setYRange(ymin, ymax)

    def clear(self):
        self.plot_object.clear()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app, port):
        super().__init__()
        self.app = app
        self.setWindowTitle("ni-daqmx-tmux")
        self.setCentralWidget(ConfigWidget(port))


def main():
    """Initialize application and main window."""
    port = int(sys.argv[1])
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow(app, port)
    main_window.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
