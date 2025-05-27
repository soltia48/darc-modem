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
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import osmosdr
import time




class darc_demod(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "DARC Demodulator", catch_exceptions=True)

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
        self.frequency = frequency = 82.5e6
        self.darc_low_pass_filter_taps = darc_low_pass_filter_taps = firdes.low_pass(1.0, wbfm_sampling_rate, 8e3,4e3, window.WIN_HAMMING, 6.76)

        ##################################################
        # Blocks
        ##################################################

        self.osmosdr_source_0 = osmosdr.source(
            args="numchan=" + str(1) + " " + "rtl_tcp=127.0.0.1:1234,bias=1"
        )
        self.osmosdr_source_0.set_time_unknown_pps(osmosdr.time_spec_t())
        self.osmosdr_source_0.set_sample_rate(source_sampling_rate)
        self.osmosdr_source_0.set_center_freq((frequency-0.25e6), 0)
        self.osmosdr_source_0.set_freq_corr(0, 0)
        self.osmosdr_source_0.set_dc_offset_mode(0, 0)
        self.osmosdr_source_0.set_iq_balance_mode(0, 0)
        self.osmosdr_source_0.set_gain_mode(False, 0)
        self.osmosdr_source_0.set_gain(10, 0)
        self.osmosdr_source_0.set_if_gain(20, 0)
        self.osmosdr_source_0.set_bb_gain(20, 0)
        self.osmosdr_source_0.set_antenna('', 0)
        self.osmosdr_source_0.set_bandwidth(0, 0)
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
        self.connect((self.digital_gmsk_demod_0, 0), (self.blocks_file_sink_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.digital_gmsk_demod_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0_0, 0), (self.analog_quadrature_demod_cf_0, 0))
        self.connect((self.osmosdr_source_0, 0), (self.freq_xlating_fir_filter_xxx_0_0, 0))


    def get_wbfm_sampling_rate(self):
        return self.wbfm_sampling_rate

    def set_wbfm_sampling_rate(self, wbfm_sampling_rate):
        self.wbfm_sampling_rate = wbfm_sampling_rate
        self.set_darc_low_pass_filter_taps(firdes.low_pass(1.0, self.wbfm_sampling_rate, 8e3, 4e3, window.WIN_HAMMING, 6.76))
        self.analog_quadrature_demod_cf_0.set_gain((self.wbfm_sampling_rate/(2*math.pi*self.wbfm_deviation)))

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
        self.osmosdr_source_0.set_sample_rate(self.source_sampling_rate)

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

    def get_frequency(self):
        return self.frequency

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.osmosdr_source_0.set_center_freq((self.frequency-0.25e6), 0)

    def get_darc_low_pass_filter_taps(self):
        return self.darc_low_pass_filter_taps

    def set_darc_low_pass_filter_taps(self, darc_low_pass_filter_taps):
        self.darc_low_pass_filter_taps = darc_low_pass_filter_taps
        self.freq_xlating_fir_filter_xxx_0.set_taps(self.darc_low_pass_filter_taps)




def main(top_block_cls=darc_demod, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
