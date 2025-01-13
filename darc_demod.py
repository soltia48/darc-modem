#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: DARC Demodulator
# Author: soltia48
# Copyright: Copyright (c) 2023 soltia48
# Description: Data Radio Channel (DARC) demodulator
# GNU Radio version: 3.10.9.2

from PyQt5 import Qt
from gnuradio import qtgui
from PyQt5 import QtCore
from gnuradio import analog
import math
from gnuradio import blocks
from gnuradio import digital
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import osmosdr
import time
import sip



class darc_demod(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "DARC Demodulator", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("DARC Demodulator")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "darc_demod")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)

        ##################################################
        # Variables
        ##################################################
        self.wbfm_sampling_rate = wbfm_sampling_rate = 512e3
        self.wbfm_bandwidth = wbfm_bandwidth = 125e3
        self.symbols_per_second = symbols_per_second = 16e3
        self.source_sampling_rate = source_sampling_rate = int(1.024e6)
        self.darc_sampling_rate = darc_sampling_rate = 512e3
        self.wbfm_low_pass_filter_taps = wbfm_low_pass_filter_taps = firdes.low_pass(1.0, source_sampling_rate, wbfm_bandwidth,wbfm_bandwidth*0.5, window.WIN_BLACKMAN, 6.76)
        self.wbfm_deviation = wbfm_deviation = 75e3
        self.samples_per_symbol = samples_per_symbol = int(darc_sampling_rate/symbols_per_second)
        self.gain = gain = 32.0
        self.frequency = frequency = 82.5e6
        self.darc_low_pass_filter_taps = darc_low_pass_filter_taps = firdes.low_pass(1.0, wbfm_sampling_rate, 8e3,4e3, window.WIN_HAMMING, 6.76)

        ##################################################
        # Blocks
        ##################################################

        self._gain_range = qtgui.Range(0.0, 64.0, 0.1, 32.0, 200)
        self._gain_win = qtgui.RangeWidget(self._gain_range, self.set_gain, "Gain", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._gain_win)
        self._frequency_range = qtgui.Range(76.1e6, 94.9e6, 0.1e6, 82.5e6, 200)
        self._frequency_win = qtgui.RangeWidget(self._frequency_range, self.set_frequency, "Frequency", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._frequency_win)
        self.rtlsdr_source_0 = osmosdr.source(
            args="numchan=" + str(1) + " " + "rtl_tcp=127.0.0.1:1234,bias=1"
        )
        self.rtlsdr_source_0.set_time_unknown_pps(osmosdr.time_spec_t())
        self.rtlsdr_source_0.set_sample_rate(source_sampling_rate)
        self.rtlsdr_source_0.set_center_freq((frequency-0.25e6), 0)
        self.rtlsdr_source_0.set_freq_corr((-5), 0)
        self.rtlsdr_source_0.set_dc_offset_mode(0, 0)
        self.rtlsdr_source_0.set_iq_balance_mode(0, 0)
        self.rtlsdr_source_0.set_gain_mode(True, 0)
        self.rtlsdr_source_0.set_gain(gain, 0)
        self.rtlsdr_source_0.set_if_gain(0.0, 0)
        self.rtlsdr_source_0.set_bb_gain(0.0, 0)
        self.rtlsdr_source_0.set_antenna('', 0)
        self.rtlsdr_source_0.set_bandwidth(source_sampling_rate, 0)
        self.qtgui_time_raster_sink_x_0 = qtgui.time_raster_sink_b(
            16e3,
            256,
            288,
            [],
            [],
            "",
            1,
            None
        )

        self.qtgui_time_raster_sink_x_0.set_update_time(0.10)
        self.qtgui_time_raster_sink_x_0.set_intensity_range(0, 1)
        self.qtgui_time_raster_sink_x_0.enable_grid(False)
        self.qtgui_time_raster_sink_x_0.enable_axis_labels(True)
        self.qtgui_time_raster_sink_x_0.set_x_label("")
        self.qtgui_time_raster_sink_x_0.set_x_range(0.0, 0.0)
        self.qtgui_time_raster_sink_x_0.set_y_label("")
        self.qtgui_time_raster_sink_x_0.set_y_range(0.0, 0.0)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        colors = [1, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_time_raster_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_raster_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_time_raster_sink_x_0.set_color_map(i, colors[i])
            self.qtgui_time_raster_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_time_raster_sink_x_0_win = sip.wrapinstance(self.qtgui_time_raster_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_time_raster_sink_x_0_win)
        self.qtgui_freq_sink_x_0 = qtgui.freq_sink_f(
            32768, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            wbfm_sampling_rate, #bw
            "", #name
            1,
            None # parent
        )
        self.qtgui_freq_sink_x_0.set_update_time(0.10)
        self.qtgui_freq_sink_x_0.set_y_axis((-140), 10)
        self.qtgui_freq_sink_x_0.set_y_label('Relative Gain', 'dB')
        self.qtgui_freq_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_x_0.enable_autoscale(False)
        self.qtgui_freq_sink_x_0.enable_grid(False)
        self.qtgui_freq_sink_x_0.set_fft_average(1.0)
        self.qtgui_freq_sink_x_0.enable_axis_labels(True)
        self.qtgui_freq_sink_x_0.enable_control_panel(False)
        self.qtgui_freq_sink_x_0.set_fft_window_normalized(False)


        self.qtgui_freq_sink_x_0.set_plot_pos_half(not False)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_freq_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_freq_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_freq_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_freq_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_freq_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_freq_sink_x_0_win = sip.wrapinstance(self.qtgui_freq_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_freq_sink_x_0_win)
        self.freq_xlating_fir_filter_xxx_0_0 = filter.freq_xlating_fir_filter_ccf((int(source_sampling_rate/wbfm_sampling_rate)), wbfm_low_pass_filter_taps, 0.25e6, source_sampling_rate)
        self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_fcc((int(wbfm_sampling_rate/darc_sampling_rate)), darc_low_pass_filter_taps, 76e3, wbfm_sampling_rate)
        self.digital_gmsk_demod_0 = digital.gmsk_demod(
            samples_per_symbol=int(samples_per_symbol),
            gain_mu=0.025,
            mu=0.5,
            omega_relative_limit=0.005,
            freq_error=0.0,
            verbose=False,log=False)
        self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_char*1, '/dev/stdout', False)
        self.blocks_file_sink_0.set_unbuffered(True)
        self.analog_quadrature_demod_cf_0 = analog.quadrature_demod_cf((wbfm_sampling_rate/(2*math.pi*wbfm_deviation)))


        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_quadrature_demod_cf_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.analog_quadrature_demod_cf_0, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.digital_gmsk_demod_0, 0), (self.blocks_file_sink_0, 0))
        self.connect((self.digital_gmsk_demod_0, 0), (self.qtgui_time_raster_sink_x_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.digital_gmsk_demod_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0_0, 0), (self.analog_quadrature_demod_cf_0, 0))
        self.connect((self.rtlsdr_source_0, 0), (self.freq_xlating_fir_filter_xxx_0_0, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "darc_demod")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_wbfm_sampling_rate(self):
        return self.wbfm_sampling_rate

    def set_wbfm_sampling_rate(self, wbfm_sampling_rate):
        self.wbfm_sampling_rate = wbfm_sampling_rate
        self.set_darc_low_pass_filter_taps(firdes.low_pass(1.0, self.wbfm_sampling_rate, 8e3, 4e3, window.WIN_HAMMING, 6.76))
        self.analog_quadrature_demod_cf_0.set_gain((self.wbfm_sampling_rate/(2*math.pi*self.wbfm_deviation)))
        self.qtgui_freq_sink_x_0.set_frequency_range(0, self.wbfm_sampling_rate)

    def get_wbfm_bandwidth(self):
        return self.wbfm_bandwidth

    def set_wbfm_bandwidth(self, wbfm_bandwidth):
        self.wbfm_bandwidth = wbfm_bandwidth
        self.set_wbfm_low_pass_filter_taps(firdes.low_pass(1.0, self.source_sampling_rate, self.wbfm_bandwidth, self.wbfm_bandwidth*0.5, window.WIN_BLACKMAN, 6.76))

    def get_symbols_per_second(self):
        return self.symbols_per_second

    def set_symbols_per_second(self, symbols_per_second):
        self.symbols_per_second = symbols_per_second
        self.set_samples_per_symbol(int(self.darc_sampling_rate/self.symbols_per_second))

    def get_source_sampling_rate(self):
        return self.source_sampling_rate

    def set_source_sampling_rate(self, source_sampling_rate):
        self.source_sampling_rate = source_sampling_rate
        self.set_wbfm_low_pass_filter_taps(firdes.low_pass(1.0, self.source_sampling_rate, self.wbfm_bandwidth, self.wbfm_bandwidth*0.5, window.WIN_BLACKMAN, 6.76))
        self.rtlsdr_source_0.set_sample_rate(self.source_sampling_rate)
        self.rtlsdr_source_0.set_bandwidth(self.source_sampling_rate, 0)

    def get_darc_sampling_rate(self):
        return self.darc_sampling_rate

    def set_darc_sampling_rate(self, darc_sampling_rate):
        self.darc_sampling_rate = darc_sampling_rate
        self.set_samples_per_symbol(int(self.darc_sampling_rate/self.symbols_per_second))

    def get_wbfm_low_pass_filter_taps(self):
        return self.wbfm_low_pass_filter_taps

    def set_wbfm_low_pass_filter_taps(self, wbfm_low_pass_filter_taps):
        self.wbfm_low_pass_filter_taps = wbfm_low_pass_filter_taps
        self.freq_xlating_fir_filter_xxx_0_0.set_taps(self.wbfm_low_pass_filter_taps)

    def get_wbfm_deviation(self):
        return self.wbfm_deviation

    def set_wbfm_deviation(self, wbfm_deviation):
        self.wbfm_deviation = wbfm_deviation
        self.analog_quadrature_demod_cf_0.set_gain((self.wbfm_sampling_rate/(2*math.pi*self.wbfm_deviation)))

    def get_samples_per_symbol(self):
        return self.samples_per_symbol

    def set_samples_per_symbol(self, samples_per_symbol):
        self.samples_per_symbol = samples_per_symbol

    def get_gain(self):
        return self.gain

    def set_gain(self, gain):
        self.gain = gain
        self.rtlsdr_source_0.set_gain(self.gain, 0)

    def get_frequency(self):
        return self.frequency

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.rtlsdr_source_0.set_center_freq((self.frequency-0.25e6), 0)

    def get_darc_low_pass_filter_taps(self):
        return self.darc_low_pass_filter_taps

    def set_darc_low_pass_filter_taps(self, darc_low_pass_filter_taps):
        self.darc_low_pass_filter_taps = darc_low_pass_filter_taps
        self.freq_xlating_fir_filter_xxx_0.set_taps(self.darc_low_pass_filter_taps)




def main(top_block_cls=darc_demod, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
