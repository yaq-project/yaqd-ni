__all__ = ["DaqmxTmux"]

import asyncio
import os
import imp
import time
import copy
import pathlib
from typing import Dict, Any, List

import numpy as np
from PyDAQmx import *
from PyDAQmx import byref

from yaqd_core import Sensor


class NiDaqmxTmux(Sensor):
    _kind = "ni-daqmx-tmux"

    def __init__(self, name, config, config_filepath):
        super().__init__(name, config, config_filepath)
        # Perform any unique initialization

        self._channel_names = ["channel"]
        self._channel_units = {"channel": "units"}

    def _create_task(self):
        """
        Define a new DAQ task. This needs to be run once every time the
        parameters of the aquisition (channel correspondance, shots, etc.)
        change.
        """
        # ensure previous task closed
        if self.task_created:
            DAQmxStopTask(self.task_handle)
            DAQmxClearTask(self.task_handle)
        self.task_created = False
        # calculate the number of 'virtual samples' to take -------------------
        self.virtual_samples = self._state["nsamples"]
        # create task ---------------------------------------------------------
        try:
            self.task_handle = TaskHandle()
            self.read = int32()  # ??? --BJT 2017-06-03
            DAQmxCreateTask("", byref(self.task_handle))
        except DAQError as err:
            print("DAQmx Error: %s" % err)
            g.logger.log("error", "Error in task creation", err)
            DAQmxStopTask(self.task_handle)
            DAQmxClearTask(self.task_handle)
            return
        # initialize channels -------------------------------------------------
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
        #
        name_index = 0  # something to keep channel names unique
        try:
            # sample correspondances holds an array of integers
            # zero : rest sample
            # positive : channel
            # negative : chopper
            for correspondance in sample_correspondances.read():
                if correspondance == 0:
                    physical_channel = rest_channel.read()
                    min_voltage = -10.0
                    max_voltage = 10.0
                elif correspondance > 0:
                    channel = channels.read()[correspondance - 1]
                    physical_channel = channel.physical_correspondance.read()
                    min_voltage, max_voltage = channel.get_range()
                elif correspondance < 0:
                    physical_channel = choppers.read()[
                        -correspondance - 1
                    ].physical_correspondance.read()
                    min_voltage = -10.0
                    max_voltage = 10.0
                channel_name = "sample_" + str(name_index).zfill(3)
                DAQmxCreateAIVoltageChan(
                    self.task_handle,  # task handle
                    DAQ_device_name + "/ai%i" % physical_channel,  # physical chanel
                    channel_name,  # name to assign to channel
                    DAQmx_Val_Diff,  # the input terminal configuration
                    min_voltage,
                    max_voltage,  # minVal, maxVal
                    DAQmx_Val_Volts,  # units
                    None,
                )  # custom scale
                name_index += 1
        except DAQError as err:
            print("DAQmx Error: %s" % err)
            g.logger.log("error", "Error in virtual channel creation", err)
            DAQmxStopTask(self.task_handle)
            DAQmxClearTask(self.task_handle)
            return
        # define timing -------------------------------------------------------
        try:
            DAQmxCfgSampClkTiming(
                self.task_handle,  # task handle
                "/" + DAQ_device_name + "/PFI0",  # sorce terminal
                1000.0,  # sampling rate (samples per second per channel) (float 64) (in externally clocked mode, only used to initialize buffer)
                DAQmx_Val_Rising,  # acquire samples on the rising edges of the sample clock
                DAQmx_Val_FiniteSamps,  # acquire a finite number of samples
                int(self._state["shots"]),
            )  # samples per channel to acquire (unsigned integer 64)
        except DAQError as err:
            print("DAQmx Error: %s" % err)
            g.logger.log("error", "Error in timing definition", err)
            DAQmxStopTask(self.task_handle)
            DAQmxClearTask(self.task_handle)
            return
        # create arrays for task to fill --------------------------------------
        self.samples = np.zeros(
            int(self._state["shots"] * self._state["nsamples"]), dtype=np.float64
        )
        self.samples_len = len(self.samples)  # do not want to call for every acquisition
        # finish --------------------------------------------------------------
        self.task_created = True
        self.task_changed.emit()

    def measure(self):
        """
        Acquire once using the created task.
        """
        if len(self.data.cols) == 0:
            return BaseDriver.measure(self)
        ### measure ###########################################################
        # unpack inputs -------------------------------------------------------
        self.running = True
        # self.update_ui.emit()
        if not self.task_created:
            return
        start_time = time.time()
        # collect samples array -----------------------------------------------
        # Exponential backoff for retrying measurement
        for wait in np.geomspace(0.01, 60, 10):
            try:
                self.thread
                self.read = int32()
                DAQmxStartTask(self.task_handle)
                DAQmxReadAnalogF64(
                    self.task_handle,  # task handle
                    int(self._state["shots"]),  # number of samples per channel
                    10.0,  # timeout (seconds) for each read operation
                    DAQmx_Val_GroupByScanNumber,  # fill mode (specifies whether or not the samples are interleaved)
                    self.samples,  # read array
                    self.samples_len,  # size of the array, in samples, into which samples are read
                    byref(self.read),  # reference of thread
                    None,
                )  # reserved by NI, pass NULL (?)
                DAQmxStopTask(self.task_handle)
            except DAQError as err:
                print("DAQmx Error: %s" % err)
                g.logger.log("error", "Error in timing definition", err)
                DAQmxStopTask(self.task_handle)
                time.sleep(wait)
            else:
                break
        else:
            DAQmxClearTask(self.task_handle)
        # export samples
        samples.write(self.samples)
        ### process ###########################################################
        # calculate shot values for each channel, chopper ---------------------
        active_channels = [channel for channel in channels.read() if channel.active.read()]
        active_choppers = [chopper for chopper in choppers.read() if chopper.active.read()]
        shots_array = np.full(
            (len(active_channels) + len(active_choppers), int(self._state["shots"])), np.nan
        )
        folded_samples = self.samples.copy().reshape((self._state["nsamples"], -1), order="F")
        index = 0
        # channels
        for channel_index, channel in enumerate(active_channels):
            # get signal points
            signal_index_possibilities = range(
                int(channel.signal_start_index.read()), int(channel.signal_stop_index.read()) + 1,
            )
            signal_indicies = [
                i
                for i in signal_index_possibilities
                if sample_correspondances.read()[i] == channel_index + 1
            ]
            signal_indicies = signal_indicies[
                int(channel.signal_pre_index.read()) :
            ]  # remove pre points
            signal_samples = folded_samples[signal_indicies]
            # process signal
            if channel.signal_method.read() == "Average":
                signal = np.mean(signal_samples, axis=0)
            elif channel.signal_method.read() == "Sum":
                signal = np.sum(signal_samples, axis=0)
            elif channel.signal_method.read() == "Min":
                signal = np.min(signal_samples, axis=0)
            elif channel.signal_method.read() == "Max":
                signal = np.max(signal_samples, axis=0)
            # baseline
            if channel.use_baseline.read():
                # get baseline points
                baseline_index_possibilities = range(
                    int(channel.baseline_start_index.read()),
                    int(channel.baseline_stop_index.read()) + 1,
                )
                baseline_indicies = [
                    i
                    for i in baseline_index_possibilities
                    if sample_correspondances.read()[i] == channel_index + 1
                ]
                baseline_indicies = baseline_indicies[
                    int(channel.baseline_pre_index.read()) :
                ]  # remove pre points
                baseline_samples = folded_samples[baseline_indicies]
                # process baseline
                if channel.baseline_method.read() == "Average":
                    baseline = np.mean(baseline_samples, axis=0)
                elif channel.baseline_method.read() == "Sum":
                    baseline = np.sum(baseline_samples, axis=0)
                elif channel.baseline_method.read() == "Min":
                    baseline = np.min(baseline_samples, axis=0)
                elif channel.baseline_method.read() == "Max":
                    baseline = np.max(baseline_samples, axis=0)
            else:
                baseline = 0
            out = signal - baseline
            # invert
            if channel.invert.read():
                out *= -1
            # finish
            shots_array[index] = out
            index += 1
        # choppers
        for chopper in active_choppers:
            cutoff = 1.0  # volts
            out = folded_samples[int(chopper.index.read())]
            out[out <= cutoff] = -1.0
            out[out > cutoff] = 1.0
            if chopper.invert.read():
                out *= -1
            shots_array[index] = out
            index += 1
        # export shots
        channel_names = [channel.name.read() for channel in active_channels]
        chopper_names = [chopper.name.read() for chopper in active_choppers]
        shots.write(shots_array)  # TODO: can I remove this?
        shots.write_properties((1,), channel_names + chopper_names, shots_array)
        # do math -------------------------------------------------------------
        # pass through shots processing module
        with self.processing_timer:
            path = shots_processing_module_path.read()
            name = os.path.basename(path).split(".")[0]
            directory = os.path.dirname(path)
            f, p, d = imp.find_module(name, [directory])
            processing_module = imp.load_module(name, f, p, d)
            kinds = ["channel" for _ in channel_names] + ["chopper" for _ in chopper_names]
            names = channel_names + chopper_names
            out = processing_module.process(shots_array, names, kinds)
            if len(out) == 3:
                out, out_names, out_signed = out
            else:
                out, out_names = out
                out_signed = False

        seconds_for_shots_processing.write(self.processing_timer.interval)
        # export last data
        self.data.write_properties((1,), out_names, out, out_signed)
        self.update_ui.emit()
        ### finish ############################################################
        seconds_since_last_task.write(time.time() - self.previous_time)
        self.previous_time = time.time()
        self.running = False
        stop_time = time.time()
        seconds_for_acquisition.write(stop_time - start_time)
        self.measure_time.write(seconds_for_acquisition.read())

    def update_sample_correspondances(self, proposed_channels, proposed_choppers):
        """
        Parameters
        ----------
        channels : list of Channel objects
            The proposed channel settings.
        choppers : list of Chopper objects
            The proposed chopper settings.
        """
        # sections is a list of lists: [correspondance, start index, stop index]
        sections = []
        for i in range(len(proposed_channels)):
            channel = proposed_channels[i]
            if channel.active.read():
                correspondance = i + 1  # channels go from 1 --> infinity
                start = channel.signal_start_index.read()
                stop = channel.signal_stop_index.read()
                sections.append([correspondance, start, stop])
                if channel.use_baseline.read():
                    start = channel.baseline_start_index.read()
                    stop = channel.baseline_stop_index.read()
                    sections.append([correspondance, start, stop])
        # desired is a list of lists containing all of the channels
        # that desire to be read at a given sample
        desired = [[] for _ in range(self._state["nsamples"])]
        for section in sections:
            correspondance = section[0]
            start = int(section[1])
            stop = int(section[2])
            for i in range(start, stop + 1):
                desired[i].append(correspondance)
                desired[i] = [val for val in set(desired[i])]  # remove non-unique
                desired[i].sort()
        # samples is the proposed sample correspondances
        samples = np.full(self._state["nsamples"], 0, dtype=int)
        for i in range(len(samples)):
            lis = desired[i]
            if not len(lis) == 0:
                samples[i] = lis[i % len(lis)]
        # choppers
        for i, chopper in enumerate(proposed_choppers):
            if chopper.active.read():
                samples[int(chopper.index.read())] = -(i + 1)
        # check if proposed is valid
        # TODO: !!!!!!!!!!!!!!!
        # apply to channels
        channels.write(proposed_channels)
        for channel in channels.read():
            channel.save()
        choppers.write(proposed_choppers)
        for chopper in choppers.read():
            chopper.save()
        # update channel names
        channel_names = [
            channel.name.read() for channel in channels.read() if channel.active.read()
        ]
        chopper_names = [
            chopper.name.read() for chopper in choppers.read() if chopper.active.read()
        ]
        allowed_values = channel_names + chopper_names
        shot_channel_combo.set_allowed_values(allowed_values)
        # finish
        sample_correspondances.write(samples)
        self.update_task()

    async def update_state(self):
        """Continually monitor and update the current daemon state."""
        # If there is no state to monitor continuously, delete this function
        while True:
            # Perform any updates to internal state
            self._busy = False
            # There must be at least one `await` in this loop
            # This one waits for something to trigger the "busy" state
            # (Setting `self._busy = True)
            # Otherwise, you can simply `await asyncio.sleep(0.01)`
            await self._busy_sig.wait()
