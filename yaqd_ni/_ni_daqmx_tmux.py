import asyncio
import os
import imp
import time
import copy
import pathlib
from dataclasses import dataclass
from typing import Dict, Any, List

import numpy as np  # type: ignore

from yaqd_core import Sensor


def process_samples(method, samples):
    # samples arry shape: (sample, shot)
    if method == "average":
        shots = np.mean(samples, axis=0)
    elif method == "sum":
        shots = np.sum(samples, axis=0)
    elif method == "min":
        shots = np.min(samples, axis=0)
    elif method == "max":
        shots = np.max(samples, axis=0)
    else:
        raise KeyError("sample processing method not recognized")
    return shots


@dataclass
class Channel:
    name: str
    range: str
    enabled: bool
    physical_channel: str
    invert: bool
    signal_start: int
    signal_stop: int
    signal_method: str
    use_baseline: bool
    baseline_start: int
    baseline_stop: int
    baseline_method: str
    baseline_presample: int = 0
    signal_presample: int = 0


@dataclass
class Chopper:
    name: str
    enabled: bool
    physical_channel: str
    invert: bool
    index: int


class NiDaqmxTmux(Sensor):
    _kind = "ni-daqmx-tmux"

    def __init__(self, name, config, config_filepath):
        super().__init__(name, config, config_filepath)
        # channels
        self._channels = []
        for k, d in self._config["channels"].items():
            channel = Channel(**d, physical_channel=k)
            self._channels.append(channel)
        self._channel_names = [c.name for c in self._channels if c.enabled]  # expected by parent
        self._channel_units = {k: "V" for k in self._channel_names}  # expected by parent
        # choppers
        self._choppers = []
        for k, d in self._config["choppers"].items():
            chopper = Chopper(**d, physical_channel=k)
            if chopper.enabled:
                self._choppers.append(chopper)
        # check that all physical channels are unique
        x = []
        x += [c.physical_channel for c in self._channels]
        x += [c.physical_channel for c in self._choppers]
        assert len(set(x)) == len(x)
        # finish
        self._stale_task = True
        self._create_sample_correspondances()
        self._create_task()
        self.measure()

    def _create_sample_correspondances(self):
        self._sample_correspondances = np.zeros(self._config["nsamples"])
        # channels
        for sample_index in range(self._config["nsamples"]):
            channel_idxs = []  # contains indicies of all channels that want to read at this sample
            for channel_index, channel in enumerate(self._channels):
                if not channel.enabled:
                    continue
                if (
                    channel.signal_start - channel.signal_presample
                    < sample_index
                    < channel.signal_stop
                ):
                    channel_idxs.append(channel_index + 1)
                if channel.use_baseline and (
                    channel.baseline_start - channel.baseline_presample
                    < sample_index
                    < channel.baseline_stop
                ):
                    channel_idxs.append(channel_index + 1)
            if len(channel_idxs) == 1:
                self._sample_correspondances[sample_index] = channel_idxs[0]
            elif len(channel_idxs) > 1:
                self._sample_correspondances[sample_index] = channel_idxs[
                    sample_index % len(channel_idxs)
                ]
        # choppers
        for chopper_index, chopper in enumerate(self._choppers):
            if not chopper.enabled:
                continue
            self._sample_correspondances[chopper.index] = -chopper_index

    def _create_task(self):
        import PyDAQmx  # type: ignore

        # ensure previous task closed
        if hasattr(self, "_task_handle"):
            PyDAQmx.DAQmxStopTask(self._task_handle)
            PyDAQmx.DAQmxClearTask(self._task_handle)
        # create task
        try:
            self._task_handle = PyDAQmx.TaskHandle()
            self._read = PyDAQmx.int32()  # ??? --BJT 2017-06-03
            PyDAQmx.DAQmxCreateTask("", PyDAQmx.byref(self._task_handle))
        except PyDAQmx.DAQError as err:
            PyDAQmx.DAQmxStopTask(self._task_handle)
            PyDAQmx.DAQmxClearTask(self._task_handle)
            return
        # initialize channels
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # The daq is addressed in a somewhat non-standard way. A total of ~1000
        # virtual channels are initialized (depends on DAQ speed and laser rep
        # rate). These virtual channels are evenly distributed over the physical
        # channels addressed by the software. When the task is run, it round
        # robins over all the virtual channels, essentially oversampling the
        # analog physical channels.
        #
        # self.virtual_samples contains the oversampling factor.
        #
        # Each virtual channel must have a unique name.
        #
        # The sample clock is supplied by the laser output trigger.
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        try:
            # sample correspondances holds an array of integers
            # zero : rest sample
            # positive : channel
            # negative : chopper
            name_index = 0  # something to keep channel names unique
            for correspondance in list(self._sample_correspondances):
                correspondance = int(correspondance)
                if correspondance == 0:
                    physical_channel = (
                        "/" + self._config["device_name"] + "/" + self._config["rest_channel"]
                    )
                    min_voltage = -10.0
                    max_voltage = 10.0
                elif correspondance > 0:
                    channel = self._channels[correspondance - 1]
                    physical_channel = (
                        "/" + self._config["device_name"] + "/" + channel.physical_channel
                    )
                    min_voltage, max_voltage = -10, 10  # TODO
                    # min_voltage, max_voltage = channel.get_range()
                elif correspondance < 0:
                    chopper = self._choppers[-correspondance - 1]
                    physical_channel = (
                        "/" + self._config["device_name"] + "/" + chopper.physical_channel
                    )
                    min_voltage = -10.0
                    max_voltage = 10.0
                channel_name = "sample_" + str(name_index).zfill(3)
                PyDAQmx.DAQmxCreateAIVoltageChan(
                    self._task_handle,  # task handle
                    physical_channel,  # physical channel
                    channel_name,  # name to assign to channel
                    PyDAQmx.DAQmx_Val_Diff,  # the input terminal configuration
                    min_voltage,
                    max_voltage,
                    PyDAQmx.DAQmx_Val_Volts,  # units
                    None,  # reserved
                )
                name_index += 1
        except PyDAQmx.DAQError as err:
            print(err)
            PyDAQmx.DAQmxStopTask(self._task_handle)
            PyDAQmx.DAQmxClearTask(self._task_handle)
            return
        # define timing
        try:
            PyDAQmx.DAQmxCfgSampClkTiming(
                self._task_handle,  # task handle
                "/"
                + self._config["device_name"]
                + "/"
                + self._config["trigger_source"],  # sorce terminal
                1000.0,  # sampling rate (samples per second per channel) (float 64) (in externally clocked mode, only used to initialize buffer)
                PyDAQmx.DAQmx_Val_Rising,  # acquire samples on the rising edges of the sample clock
                PyDAQmx.DAQmx_Val_FiniteSamps,  # acquire a finite number of samples
                int(self._state["nshots"]),  # samples per channel to acquire
            )
        except PyDAQmx.DAQError as err:
            PyDAQmx.DAQmxStopTask(self._task_handle)
            PyDAQmx.DAQmxClearTask(self._task_handle)
            return
        self._stale_task = False

    def get_measured_samples(self):
        return self._samples

    def get_measured_shots(self):
        return self._shots

    def get_nshots(self):
        return self._state["nshots"]

    def get_sample_correspondances(self):
        return self._sample_correspondances

    async def _measure(self):
        samples = await self._loop.run_in_executor(None, self._measure_samples)
        shots = np.empty(
            [
                len(self._channel_names) + len([c for c in self._choppers if c.enabled]),
                self._state["nshots"],
            ]
        )
        # channels
        i = 0
        for channel_index, channel in enumerate(self._channels):
            if not channel.enabled:
                continue
            # signal
            idxs = self._sample_correspondances == channel_index + 1
            idxs[channel.signal_stop + 1 :] = False
            signal_samples = samples[idxs]
            signal_shots = process_samples(channel.signal_method, signal_samples)
            # baseline
            if not channel.use_baseline:
                baseline = 0
                continue
            idxs = self._sample_correspondances == channel_index + 1
            idxs[: channel.signal_stop + 1] = False
            baseline_samples = samples[idxs]
            baseline_shots = process_samples(channel.baseline_method, baseline_samples)
            # math
            shots[i] = signal_shots - baseline_shots
            if channel.invert:
                shots[i] *= 1
            i += 1
        # choppers
        for chopper in self._choppers:
            if not chopper.enabled:
                continue
            cutoff = 1.0  # volts
            out = samples[chopper.index]
            out[out <= cutoff] = -1.0
            out[out > cutoff] = 1.0
            if chopper.invert:
                out *= -1
            shots[i] = out
            i += 1
        # process
        path = self._config["shots_processing_path"]
        name = os.path.basename(path).split(".")[0]
        directory = os.path.dirname(path)
        f, p, d = imp.find_module(name, [directory])
        processing_module = imp.load_module(name, f, p, d)
        kinds = ["channel" for _ in self._channel_names] + [
            "chopper" for c in self._choppers if c.enabled
        ]
        names = self._channel_names + [c.name for c in self._choppers if c.enabled]
        out = processing_module.process(shots, names, kinds)
        if len(out) == 3:
            out, out_names, out_signed = out
        else:
            out, out_names = out
            out_signed = False
        # finish
        self._samples = samples
        self._shots = shots
        out = {k: v for k, v in zip(self._channel_names, out)}
        return out

    def _measure_samples(self):
        import PyDAQmx  # type: ignore

        samples = np.zeros(int(self._state["nshots"] * self._config["nsamples"]), dtype=np.float64)
        for wait in np.geomspace(0.01, 60, 10):  # exponential backoff for retrying measurement
            try:
                self._read = PyDAQmx.int32()
                PyDAQmx.DAQmxStartTask(self._task_handle)
                PyDAQmx.DAQmxReadAnalogF64(
                    self._task_handle,  # task handle
                    int(self._state["nshots"]),  # number of samples per channel
                    self._config["timeout"],  # timeout (seconds) for each read operation
                    PyDAQmx.DAQmx_Val_GroupByScanNumber,  # fill mode
                    samples,  # read array
                    len(samples),  # size of the array, in samples, into which samples are read
                    PyDAQmx.byref(self._read),  # reference of thread
                    None,  # reserved by NI
                )
                PyDAQmx.DAQmxStopTask(self._task_handle)
            except PyDAQmx.DAQError as err:
                print(err)
                PyDAQmx.DAQmxStopTask(self._task_handle)
                time.sleep(wait)
            else:
                break
        else:
            PyDAQmx.DAQmxClearTask(self._task_handle)
        samples = samples.reshape((self._config["nsamples"], -1), order="F")
        if self._stale_task:
            self._create_task()
            return self._measure_samples
        else:
            return samples

    def set_nshots(self, nshots):
        """Set number of shots."""
        assert nshots > 0
        self._create_task(nshots)
        self._stale_task = True
