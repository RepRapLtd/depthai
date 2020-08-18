#!/usr/bin/env python3

import argparse
try:
    import argcomplete
except ImportError:
    raise ImportError('argcomplete module not found, run python3 -m pip install -r requirements.txt ')
from argcomplete.completers import ChoicesCompleter

from enum import Enum
import os
import consts.resource_paths

def _get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]

_stream_choices = ("metaout", "previewout", "jpegout", "left", "right", "depth_raw", "disparity", "disparity_color", "meta_d2h", "object_tracker")
_CNN_choices = _get_immediate_subdirectories(consts.resource_paths.nn_resource_path)

def _stream_type(option):
    max_fps = None
    option_list = option.split(",")
    option_args = len(option_list)
    if option_args not in [1, 2]:
        msg_string = "{0} format is invalid. See --help".format(option)
        cli_print(msg_string, PrintColors.WARNING)
        raise ValueError(msg_string)


    deprecated_choices = ("depth_sipp", "depth_color_h")
    transition_map = {"depth_sipp" : "disparity_color", "depth_color_h" : "disparity_color"}
    stream_name = option_list[0]
    if stream_name in deprecated_choices:
        cli_print("Stream option " + stream_name + " is deprecated, use: " + transition_map[stream_name], PrintColors.WARNING)
        stream_name = transition_map[stream_name]

    if stream_name not in _stream_choices:
        msg_string = "{0} is not in available stream list: \n{1}".format(stream_name, _stream_choices)
        cli_print(msg_string, PrintColors.WARNING)
        raise ValueError(msg_string)

    if option_args == 1:
        stream_dict = {"name": stream_name}
    else:
        try:
            max_fps = float(option_list[1])
        except ValueError:
            msg_string = "In option: {0} {1} is not a number!".format(option, option_list[1])
            cli_print(msg_string, PrintColors.WARNING)

        stream_dict = {"name": stream_name, "max_fps": max_fps}
    return stream_dict


class RangeFloat(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __eq__(self, other):
        return self.start <= other <= self.end

    def __contains__(self, item):
        return self.__eq__(item)

    def __iter__(self):
        yield self

    def __str__(self):
        return '[{0},{1}]'.format(self.start, self.end)


class PrintColors(Enum):
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    WARNING = "\033[1;5;31m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def cli_print(msg, print_color):
    """
    Prints to console with input print color type
    """
    if not isinstance(print_color, PrintColors):
        raise ValueError("Must use PrintColors type in cli_print")
    print("{0}{1}{2}".format(print_color.value, msg, PrintColors.ENDC.value))

