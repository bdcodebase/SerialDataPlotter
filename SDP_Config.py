
# Project: Serial Data Plotter
# provides default config for SerialDataPlotter.py
# Author: Benno Dömer

import json

def parseconfig(file):
    # parse the config file
    # check if all keys are present
    with open(file) as f:
        config = json.load(f)
        default_config = getdefaultconfig()
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]
                print(F'SDP_Config: Added missing key "{key}" to config') 
    return config

def getdefaultconfig():
    # config file is a json file with the following structure:
    default_config = """
    {
        "title": "Liveplot of serial data",
        "background": "k",
        "foreground": "w",
        "framecolor": null,
        "com": "COM3",
        "plots": 3,
        "samples": 500,
        "refresh": 40,
        "delimiter": ";",
        "autoscaleinterval": 150,
        "csvpath": "<home>/Documents/data_<date>_<time>.csv",
        "channels": [
            {
                "label": "Channel 1",
                "color": "#FF00FF",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            },
            {
                "label": "Channel 2",
                "color": "#FF0000",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            },
            {
                "label": "Channel 3",
                "color": "#00FF00",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            },
            {
                "label": "Channel 4",
                "color": "#0000FF",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            },
            {
                "label": "Channel 5",
                "color": "#FFFF00",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            },
            {
                "label": "Channel 6",
                "color": "#00FFFF",
                "offset": 0,
                "scale_factor": 1,
                "min": null,
                "max": null
            }
        ]
    }
    """
    return json.loads(default_config)