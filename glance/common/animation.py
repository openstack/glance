# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import sys
import threading
import time

from glance.common import exception
from glance.common import utils


class UploadProgressStatus(threading.Thread):
    """
    A class for showing:
    1. progress;
    2. rate;
    3. ETA;
    4. and status, e.g. active or stalled.
    In order to sample the rate as closely as possible, this
    implementation uses two FIFO buffers (times and bytes)
    to record fine-grain transfer rate over a period of time.
    """
    NUM_OF_ELEMENTS = 20            # number of element in FIFO
    TIME_TO_STALL = 5               # if no data transfer longer this
                                    # time(secs), the network will be
                                    # considered as stalled.
    REFRESH_STATUS_INTERVAL = 0.1   # time interval to refresh screen
    MIN_SAMPLING_INTERVAL = 0.15    # Minimum sampling time for data
    CALC_ETA_WITH_AVE_RATE = True   # calc eta with average rate

    def __init__(self, transfer_info):
        self.current_size = 0L
        self.size = transfer_info['size']
        self.last_start = 0.0
        self.last_bytes = 0L
        self.elapsed_time = 0.0
        self.total_times = 0.0
        self.total_bytes = 0L
        self.nelements = self.NUM_OF_ELEMENTS
        self.times = [0.0, ] * self.nelements
        self.bytes = [0L, ] * self.nelements
        self.index = 0
        self.stalled = False
        self.transfer_info = transfer_info
        threading.Thread.__init__(self)

    def run(self):
        self.start = self.last_start = time.time()
        while self.current_size != self.size:
            time.sleep(self.REFRESH_STATUS_INTERVAL)
            bytes = self.transfer_info['so_far']
            self.sampling(bytes, time.time())
            self.render()
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _reset_buffer(self):
        self.times = [0.0, ] * self.nelements
        self.bytes = [0L, ] * self.nelements

    def _update(self, bytes, time):
        self.elapsed_time = time - self.last_start
        transferred_bytes = bytes - self.current_size
        self.last_bytes += transferred_bytes
        self.current_size += transferred_bytes

        if self.elapsed_time < self.MIN_SAMPLING_INTERVAL:
            return False

        if transferred_bytes == 0:
            if self.elapsed_time > self.TIME_TO_STALL:
                self.stalled = True
                self._reset_buffer()
                self.last_bytes = 0
            return False

        if self.stalled:
            self.stalled = False
            self.elapsed_time = 1.0

        return True

    def render(self):

        fraction = self.current_size / float(self.size)

        percentage = fraction * 100.0
        str_percent = "[%3d%%]" % percentage

        try:
            height, width = utils.get_terminal_size()
            sys.stdout.write("\b" * width)

            eta = self._calc_eta()
            rate = self._get_speed()
            width -= len(eta)
            width -= len(rate)

            bar = ('=' * int((width - len(str_percent)) * fraction)
                + str_percent)
            padding = ' ' * (width - len(bar))
            sys.stdout.write(bar + padding + rate + eta)
            sys.stdout.flush()

        except (exception.Invalid, NotImplementedError):

            sys.stdout.write("\b" * 6)  # use the len of [%3d%%]
            percent = (str_percent + ' '
                        if self.current_size == self.size else str_percent)
            percent += ' ' + self._get_speed() + 'ETA  ' + self._calc_eta()
            sys.stdout.write(percent)
            sys.stdout.write("\b" * len(percent))
            sys.stdout.flush()

    def _get_speed(self):
        speed, unit = self._calc_speed()
        if speed > 0.0:
            if speed >= 99.95:
                rate = "%4f" % speed
            elif speed >= 9.995:
                rate = "%4.1f" % speed
            else:
                rate = "%4.2f" % speed
            return " " + rate + unit + ", "
        else:
            return " ?B/s  "

    def _calc_eta(self):
        if self.stalled or self.current_size < self.size * 0.01:
            return "ETA  ??h ??m ??s"
        if self.CALC_ETA_WITH_AVE_RATE:
            eta = ((self.size - self.current_size)
                    * (time.time() - self.start) / self.current_size)
        else:
            eta = (((self.size - self.current_size)
                    * self.total_times) / (self.total_bytes))
        eta = int(eta)
        hrs = mins = secs = 0
        hrs = eta / 3600
        secs = eta - hrs * 3600
        if secs >= 60:
            mins = secs / 60
            secs = secs % 60

        return "ETA  %dh %2dm %2ds" % (hrs, mins, secs)

    def _calc_speed(self):
        idx = 0
        units = ('B/s', 'K/s', 'M/s', 'G/s')
        total_times = self.total_times + time.time() - self.last_start
        total_bytes = self.total_bytes + self.last_bytes

        if self.stalled or total_times == 0:
            return None, None
        speed = total_bytes / float(total_times)

        if speed < 1024:
            idx = 0
        elif speed < 1048576.:  # 1024*1024
            idx = 1
            speed /= 1024.
        elif speed < 1073741824.:  # 1024*1024*1024
            idx = 2
            speed /= 1048576.
        else:
            idx = 3
            speed /= 1073741824.

        return speed, units[idx]

    def sampling(self, bytes, time):
        if not self._update(bytes, time):
            return

        self.total_times -= self.times[self.index]
        self.total_bytes -= self.bytes[self.index]

        self.times[self.index] = self.elapsed_time
        self.bytes[self.index] = self.last_bytes

        self.total_times += self.elapsed_time
        self.total_bytes += self.last_bytes

        self.last_start = time
        self.last_bytes = 0L

        self.index += 1
        if self.index == self.nelements:
            self.index = 0
