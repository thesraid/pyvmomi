#!/usr/bin/env python

"""
Program to download the latest USMA sensor and deploy it as a smaller template
The system that runs this application will need the following applications installed
python: 			apt install python
python package installer:	apt install python-pip
pyVmomi python package:		pip install pyVmomi 
guestmount:			apt install libguestfs-tools
ovftool:			https://my.vmware.com/group/vmware/details?productId=614&downloadGroup=OVFTOOL420
				install with --console
unzip:				apt install unzip
"""

import sys
import os
import subprocess
import syslog
import time
import re
import atexit
import argparse
import getpass
from datetime import date, datetime, timedelta
from shutil import copyfile
from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim


#########################################################################################################

"""
Ignore SSL warnings
"""
# http://pyvmomi.2338814.n4.nabble.com/Connect-to-esxi-host-with-self-Signed-certificate-td21.html
import requests
requests.packages.urllib3.disable_warnings()

import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

#########################################################################################################

"""
Default global variables
Any of these can be changed if required
"""

# Default RAM in MB to give the sensor
# Can be edited at run time with -r
RAM = 8192
# Default number of CPUs to give the sensor
# Can be edited at run time with -c
CPU = 4
# Default MAC address
# Can be edited at run time with -m
MAC = "00:50:56:12:34:56"
# Default ESX Host to deploy to
# Currently this points to the sandbox host
ESXPATH = "/AV/host/AWC/awc-esx01.nil.com"
# URL to the sensor
URL = "http://downloads.alienvault.cloud/usm-anywhere/sensor-images/usm-anywhere-sensor-vmware.zip"

#########################################################################################################

def get_args():
    """Get command line args from the user.
    """
    parser = argparse.ArgumentParser(
        description='Standard Arguments for talking to vCenter')

    # because -h is reserved for 'help' we use -s for service
    parser.add_argument('-s', '--host',
                        required=True,
                        action='store',
                        help='vSphere service to connect to')

    # because we want -p for password, we use -o for port
    parser.add_argument('-o', '--port',
                        type=int,
                        default=443,
                        action='store',
                        help='Port to connect on')

    parser.add_argument('-u', '--user',
                        required=True,
                        action='store',
                        help='User name to use when connecting to host')

    parser.add_argument('-p', '--password',
                        required=False,
                        action='store',
                        help='Password to use when connecting to host')

    parser.add_argument('-f', '--folder',
                        required=True,
                        action='store',
                        help='Folder to store the template')

    parser.add_argument('-r', '--ram',
                        required=False,
                        action='store',
                        help='RAM value in MB (default 8192)')

    parser.add_argument('-c', '--cpu',
                        required=False,
                        action='store',
                        help='Num CPU (default 4)')

    parser.add_argument('-m', '--mac',
                        required=False,
                        action='store',
                        help='MAC Address (default 00:50:56:12:34:56)')

    parser.add_argument('-d', '--download',
                        required=True,
                        action='store',
                        help='Sensor download directory')


    args = parser.parse_args()

    if not args.password:
        args.password = getpass.getpass(
            prompt='Enter password for host %s and user %s: ' %
                   (args.host, args.user))
    return args

#########################################################################################################

def get_obj(content, vimtype, name):
    """
    Return an object by name, if name is None the
    first found object is returned
    """
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if name:
            if c.name == name:
                obj = c
                break
        else:
            obj = c
            break
    return obj

#########################################################################################################

def get_vm_in_folder(content, vimtype, name, folder):
    """
    Return an object by name, if name is None the
    first found object is returned
    """
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if name:
            if (c.name == name) and (c.parent.name == folder):
                obj = c
                break
        else:
            obj = c
            break
    return obj

#########################################################################################################

def parentFolders(folder):

   """
   Get the full path to the specified folder
   """

   folderPath = ""
   depth = 5
   while folder.name != "vm":
      if depth != 0:
         folderPath = folder.name + "/" + folderPath
         folder = folder.parent
         depth = depth-1
      else:
         print "Error: Specified folder is nested in too many subdirectories (max: 5)"
         exit()

   return folderPath

#########################################################################################################

def uploadOVF(folderPath, vm, DOWNLOAD):
   
   """
   Upload the OVF to the specified folder
   Required OVFTOOL be installed
   """

   global ESXPATH
   args = get_args()

   host=args.host
   user=args.user
   pwd=args.password
   
   # Requires ovftool to be installed
   bashCommand = "ovftool --skipManifestCheck --noSSLVerify --disableVerification --datastore=AWC-004 --network='MGMT' --name=" + vm + " --vmFolder=" + folderPath + " --diskMode=thin " + DOWNLOAD + "/alienvault-usm/USM_sensor-node.ovf vi://'" + user + "':" + pwd + "@" + host + ESXPATH
   print "Info: Deploying", vm, "to", folderPath
   #print bashCommand
   os.system(bashCommand) 


#########################################################################################################

def modifyHardware(vm):
   """
   Modify the specified vms hardware
   """

   global CPU
   global RAM
   global MAC
   
   args = get_args()
 
   if args.cpu:
      CPU = int(args.cpu)

   if args.ram:
      RAM = int(args.ram)

   if args.mac:
      MAC = args.mac

   if vm.runtime.powerState != "poweredOff":
      print "Error: VM is not powered off. Current State is",vm.runtime.powerState
      exit()

   if vm.config.template:
      print "Error: Unable to change the hardware of a template"
      exit()

   print "Info: Changing CPU to", CPU, "and Memory to", RAM, "MB"
   cspec = vim.vm.ConfigSpec()
   cspec.numCPUs = CPU
   cspec.numCoresPerSocket = 1
   cspec.memoryMB = RAM
   vm.Reconfigure(cspec)

   print "Info: Changing MAC of the first NIC to", MAC
   for dev in vm.config.hardware.device:
      if dev.deviceInfo.label == 'Network adapter 1':
        virtual_nic_device = dev
        virtual_nic_spec = vim.vm.device.VirtualDeviceSpec()
        virtual_nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        virtual_nic_spec.device = virtual_nic_device
        virtual_nic_spec.device.macAddress = MAC
        virtual_nic_spec.device.addressType = 'manual'
        dev_changes = []
        dev_changes.append(virtual_nic_spec)
        spec = vim.vm.ConfigSpec()
        spec.deviceChange = dev_changes
        vm.ReconfigVM_Task(spec=spec)

#########################################################################################################

def currentSensor():
   """
   Find the most current sensor in the speficied URL
   """

   global URL
   found = False
 
   # Run a curl command to see when the ZIP file containing the sensor was last updated
   # http://stackoverflow.com/questions/4256107/running-bash-commands-in-python
   bashCommand = 'curl -s -I ' + URL
   process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   curloutput = process.communicate()[0]

   # http://stackoverflow.com/questions/2557808/search-and-get-a-line-in-python
   # Read the output and find the Date.
   for item in curloutput.split("\n"):
      if "Last-Modified" in item:
        #print item
        match = re.search('Last-Modified:\s\w{3},\s(\d\d)\s(\w\w\w)\s(\d\d\d\d)\s\d\d:\d\d:\d\d\s\w\w\w', item)
        #print match
        if match:
           day = match.group(1)
           month = match.group(2)
           year = match.group(3)
           current_date = day + "-" + month + "-" + year
           current_sensor_date = datetime.strptime(current_date, '%d-%b-%Y')
           current_sensor = current_sensor_date.strftime('%Y-%m-%d')
           #print "Latest Sensor is",current_sensor
           found = True

   if found: 
      return current_sensor
   else:
      print "Error: Unable to access", URL
      exit()

#########################################################################################################
def lastSensor(content, FOLDER):
   """
   Find the latest sensor in the specified folder
   """

   # Print list of VMs in the specified folder
   folder = get_obj(content, [vim.Folder], FOLDER)
   # If the folder was found list it's contents
   if folder is not None:
      listTemplates = ""
      templateList = []
      #print folder.parent.name
      # We will add all of the childObjects of the folder to a variable
      vms = folder.childEntity
      # Iterate through the VMs in the folder printing the names
      for vm in vms:
         #name = vm.name
         listTemplates = listTemplates + vm.name

      # Search the results for the date portion of the template name
      for template in listTemplates.split("\n"):
         if "USMA_Sensor" in template:
            match = re.search('\d\d\d\d-\d\d-\d\d', template)
         else:
            print "Error: No Templates with the name USM_Sensor found"
            return

      # If it's a match add it to the list
      if match:
        date_string = match.group()
        date = datetime.strptime(date_string, '%Y-%m-%d')
        templateList.append(date)

      # Find the latest date
      last_sensor_date = max(templateList)
      last_sensor = last_sensor_date.strftime('%Y-%m-%d')

      return last_sensor

   else:
     print "Error: Folder", FOLDER, "not found"
     return

#########################################################################################################
def downloadSensor(download):

   global URL

   # Download the sensor
   print "Info: Downloading sensor from", URL
   bashCommand = 'wget -O ' + download + '/usm-anywhere-sensor-vmware.zip ' + URL
   #bashCommand = 'wget -O ' + download + '/usm-anywhere-sensor-vmware.zip https://hotel.zzzz.io/tmp/small.zip'
   process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   curloutput = process.communicate()[0]


   # unzip the sensor
   print "Info: Unzipping", download, "/usm-anywhere-sensor-vmware.zip"
   bashCommand = 'unzip -o -d ' + download + ' ' + download + '/usm-anywhere-sensor-vmware.zip'
   #print bashCommand
   #process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   #while process.poll() is None:
   #   print process.stdout.readline() #give output from your execution/your own message
   #self.commandResult = process.wait() #catch return code
   #print "RETURN", self.commandResult
   #curloutput = process.communicate()[0]
   os.system(bashCommand)

   # create a mount in tmp
   if not os.path.exists('/tmp/vmdkMount'):
      os.makedirs('/tmp/vmdkMount')
   
   # mount the VMDK
   # Mount the vmdk to the vmdkMount directory
   print "Info: Mounting VMDK to /tmp/vmdkMount"
   #bashCommand = 'vmware-mount ./alienvault-usm/usm-disk1.vmdk 1 /tmp/vmdkMount/'
   #bashCommand = 'vmware-mount ' + download + '/alienvault-usm/usm-disk1.vmdk 1 /tmp/vmdkMount/'
   bashCommand = 'guestmount -a ' + download + '/alienvault-usm/usm-disk1.vmdk -i --rw /tmp/vmdkMount/'
   #print bashCommand
   #process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   #print process.communicate()[0]
   os.system(bashCommand)

   # Read the version number and store it as a var
   if not os.path.exists('/tmp/vmdkMount/etc/alienvault/system_version'):
      print "Error: Could not access system_version file in disk mounted to /tmp/vmdkMount"
      print "Error: Perhaps the extraction of the downloaded zip file failed"
      print "Error: Or perhaps the zip file was not a valid USM Anywhere Sensor"
      exit()

   with open('/tmp/vmdkMount/etc/alienvault/system_version', 'r') as myfile:
      version=myfile.read().replace('\n', '')
   print "Info: Version", version, "detected"

   # Unmount the vmdk
   print "Info: Unmounting VMDK"
   bashCommand = 'guestunmount /tmp/vmdkMount'
   #bashCommand = 'vmware-mount -d /tmp/vmdkMount/'
   #process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   #print process.communicate()[0]
   os.system(bashCommand)

   return version

   # Make Sensor name
   #new_template = "USMA_Sensor-" + version + "-" + current_sensor
   

#########################################################################################################

def main():
    """
    main method which checks the sensor version, downloads if required, edits the hardware and tempaltes it
    """

    args = get_args()

    try:
        service_instance = connect.SmartConnect(host=args.host,
                                                user=args.user,
                                                pwd=args.password,
                                                port=int(args.port))

        atexit.register(connect.Disconnect, service_instance)
        #connect.Disconnect(service_instance)
	
	session_name = service_instance.content.sessionManager.currentSession.fullName
	print "Info: vCenter time: {}".format(service_instance.CurrentTime())
        print ""
        print "Hello {}".format(session_name)
        print "You have successfully logged into {}".format(args.host)
	#print "Info: Session key", service_instance.content.sessionManager.currentSession.key

	FOLDER = args.folder
        DOWNLOAD = args.download

	# This dumps all of the vCenter data into an object
	content = service_instance.RetrieveContent()

        #Check current sensor release date
        current_sensor = currentSensor()
        if current_sensor is not None:
           print "Info: Latest sensor online is:", current_sensor
        else:
           print "Error: Unable to determine latest sensor"
           return -1

	# Send the content to lastSensor which will use it to search the folder for the latest sensor
        last_sensor = lastSensor(content, FOLDER)
        if last_sensor is not None:
           print "Info: Last sensor in the specified folder is", last_sensor
        else:
           print "Error: Previous sensor not found"
           return -1

        if current_sensor > last_sensor:
           print "Info: Update Required"

	   # get_obj is defined above. It searchs through the content for the specified object
	   folder = get_obj(content, [vim.Folder], FOLDER)
	   # Get the full path of the specified folder and upload the ovf to it
	   if folder is not None:
	      folderPath = parentFolders(folder)

	
	      # The download & upload will take a while so lets close out the vCenter connection as it times out after 15 minutes
              connect.Disconnect(service_instance)
	      #print "Info: Logged Out"

	      version = downloadSensor(DOWNLOAD)
	      
              new_template = "USMA_Sensor-" + version + "-" + current_sensor
              print "Info: New template name will be", new_template
	      uploadOVF(folderPath, new_template, DOWNLOAD)

	      # Now that we've finished downloading and uploading we will log back into vCenter
	      service_instance = connect.SmartConnect(host=args.host,
                                                      user=args.user,
                                                      pwd=args.password,
                                                      port=int(args.port))

              atexit.register(connect.Disconnect, service_instance)

              #print "Info: Session key", service_instance.content.sessionManager.currentSession.key
              #print "Info: Username", service_instance.content.sessionManager.currentSession.userName
              #print ""
              #print " "


              # This dumps all of the vCenter data into an object
              content = service_instance.RetrieveContent()
 
           else:
              print "Error: Folder", FOLDER, "not found"
              return -1

           vm = get_vm_in_folder(content, [vim.VirtualMachine], new_template, FOLDER)
	   # If we found the specified VM we will edit it's hardware
	   if vm is not None:
	      print "Info: Found", vm.name, "in", vm.parent.name
	      if vm.parent.name == FOLDER:
	         modifyHardware(vm)
                 vm.MarkAsTemplate()
	      else:
	         print "Error:", vm.name, "was not found in", FOLDER 
	         return -1
	   else:
              print "Error:", new_template, "not found"
              return -1

        else:
           print "Info: No update required"
           return 0


    except vmodl.MethodFault as error:
        #print "Caught vmodl fault : " + error.msg
        print error.msg
	return -1

    return 0

#########################################################################################################

# Start program
if __name__ == "__main__":
    main()

#########################################################################################################
