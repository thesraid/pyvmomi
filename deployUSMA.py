#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# joriordan@alienvault.com
#
# A script to check for USM Anywhere Sensor updates, download it, deploy it to the sanbox and update the MAC Address
#
# 2017-03-08

import sys
from datetime import date, datetime, timedelta
from shutil import copyfile
import os
import subprocess
import syslog
import time
import re

#item = ""
#template = ""
#current_sensor = ""
#last_sensor = ""
templateList = []

# Run a curl command to see when the ZIP file containing the sensor was last updated
# http://stackoverflow.com/questions/4256107/running-bash-commands-in-python
bashCommand = 'curl -s -I http://downloads.alienvault.cloud/usm-anywhere/sensor-images/usm-anywhere-sensor-vmware.zip'
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
#        f = open("current_sensor.txt", "w")
#        f.write(current_sensor)
#        f.close()

# List all Production USMA sensor templates
# govc ls /*/vm/_Templates_/v6\ Templates/Production\ Sensor\ Image
bashCommand = 'govc ls /*/vm/_Templates_/v6_Templates/Production_Sensor_Image'
process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
listTemplates = process.communicate()[0]

# Search the results for the date portion of the template name
for template in listTemplates.split("\n"):
   match = re.search('\d\d\d\d-\d\d-\d\d', template)

# If it's a match add it to the list
   if match:
     date_string = match.group()
     date = datetime.strptime(date_string, '%Y-%m-%d')
     templateList.append(date)

# Find the latest date
last_sensor_date = max(templateList)
last_sensor = last_sensor_date.strftime('%Y-%m-%d')

print "Last sensor on VMware is: " + last_sensor
print "Current sensor online is: " + current_sensor

# Check to see if an update is required
if current_sensor_date > last_sensor_date:
  print "Update Required"
  print "Downloading sensor update to current directory..."
  print "Ths will OVERWRITE any previous sensor download"
  bashCommand = 'wget http://downloads.alienvault.cloud/usm-anywhere/sensor-images/usm-anywhere-sensor-vmware.zip'
  #bashCommand = 'curl -O http://downloads.alienvault.cloud/usm-anywhere/sensor-images/usm-anywhere-sensor-vmware.zip'
  #bashCommand = 'curl -O https://d3uhvsbmysq4iy.cloudfront.net/images/alienvault-logo-name.png'
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  curloutput = process.communicate()[0]

  print "Unzipping"
  bashCommand = 'unzip usm-anywhere-sensor-vmware.zip'
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  curloutput = process.communicate()[0]

  # Make the directory we will use to mount the vmdk to get it's version number
  if not os.path.exists("/tmp/vmdkMount"):
    os.makedirs("/tmp/vmdkMount")

  # Mount the vmdk to the vmdkMount directory
  print "Mounting VMDK"
  bashCommand = 'vmware-mount ./alienvault-usm/usm-disk1.vmdk 1 /tmp/vmdkMount/'
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]
 
  # Read the version number and store it as a var
  with open('/tmp/vmdkMount/etc/alienvault/system_version', 'r') as myfile:
     version=myfile.read().replace('\n', '')
  print "New Version: " + version

  # Unmount the vmdk
  print "Unmounting VMDK"
  bashCommand = 'vmware-mount -d /tmp/vmdkMount/'
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]

  # Make Sensor name
  new_template = "USMA_Sensor-" + version + "-" + current_sensor
  print new_template

  # Upload new sensor
  bashCommand = "govc import.ovf -ds=AWC-004 -folder Production_Sensor_Image -name " + new_template + " ./alienvault-usm/USM_sensor-node.ovf"
  print bashCommand
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]  

  # Change sensor MAC
  bashCommand = "govc vm.network.change -vm " + new_template + " -net.address 00:50:56:12:34:56 -net=MGMT ethernet-0"
  print bashCommand
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]

  # Change sensor memory & cpu
  bashCommand = "govc vm.change -vm " + new_template + " -m=8192 -c=2"
  print bashCommand
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]

  # Turn into a Template
  bashCommand = "govc vm.markastemplate " + new_template
  print bashCommand
  process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  print process.communicate()[0]

  # Delete the zip and extracted directory
  #bashCommand = "rm usm-anywhere-sensor-vmware.zip;rm -rf alienvault-usm/"
  #print bashCommand
  #process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
  #print process.communicate()[0]

else:
  print "No Update Required"
