#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
from datetime import date, datetime, timedelta
from shutil import copyfile
import os
import subprocess
import syslog
import time
import re

URL = "http://downloads.alienvault.cloud/usm-anywhere/sensor-images/usm-anywhere-sensor-vmware.zip"

# Run a curl command to see when the ZIP file containing the sensor was last updated
# http://stackoverflow.com/questions/4256107/running-bash-commands-in-python
bashCommand = 'curl -s -I ' + URL
process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
curloutput = process.communicate()[0]

# http://stackoverflow.com/questions/2557808/search-and-get-a-line-in-python
# Read the output and find the Date.
for item in curloutput.split("\n"):
   if "Last-Modified" in item:
#    print item
     match = re.search('Last-Modified:\s\w{3},\s(\d\d)\s(\w\w\w)\s(\d\d\d\d)\s\d\d:\d\d:\d\d\s\w\w\w', item)
     if match:
        day = match.group(1)
        month = match.group(2)
        year = match.group(3)
        current_date = day + "-" + month + "-" + year
        current_sensor_date = datetime.strptime(current_date, '%d-%b-%Y')
        current_sensor = current_sensor_date.strftime('%Y-%m-%d')
	print "Latest Sensor is",current_sensor
   else:
      print ""
      print "Error: Unable to locate the string \"Last Modified\" in", URL
      print ""
