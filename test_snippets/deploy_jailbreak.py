#!/usr/bin/env python

"""
Program to download the latest USMA sensor and deploy it as a smaller template
The linux machine will need ~10GB space for downloads
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
CPU = 2
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

    # because -h is reserved for 'help' we use -s for server
    parser.add_argument('-s', '--host',
                        required=True,
                        action='store',
                        help='vSphere server to connect to')

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
                        help='Num CPU (default 2)')

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
         log("Error: Specified folder is nested in too many subdirectories (max: 5)")
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
   bashCommand = "ovftool --skipManifestCheck --noSSLVerify --disableVerification --datastore=AWC-004 --network='MGMT' --name=" + vm + " --vmFolder='" + folderPath + "' --diskMode=thin " + DOWNLOAD + "/NewOVF/USM_sensor-node.ovf vi://'" + user + "':" + pwd + "@" + host + ESXPATH
   log("Info: Deploying " + vm + " to " + folderPath)
   log("Info: " + bashCommand)
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
      log("Error: VM is not powered off. Current State is " + vm.runtime.powerState)
      exit()

   if vm.config.template:
      log("Error: Unable to change the hardware of a template")
      exit()

   log("Info: Changing CPU to " + str(CPU) + "and Memory to " + str(RAM))
   cspec = vim.vm.ConfigSpec()
   cspec.numCPUs = CPU
   cspec.numCoresPerSocket = 1
   cspec.memoryMB = RAM
   vm.Reconfigure(cspec)

   log("Info: Changing MAC of the first NIC to " + str(MAC))
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
        match = re.search('Last-Modified:\s\w{3},\s(\d\d)\s(\w\w\w)\s(\d\d\d\d)\s\d\d:\d\d:\d\d\s\w\w\w', item)
        if match:
           day = match.group(1)
           month = match.group(2)
           year = match.group(3)
           current_date = day + "-" + month + "-" + year
           current_sensor_date = datetime.strptime(current_date, '%d-%b-%Y')
           current_sensor = current_sensor_date.strftime('%Y-%m-%d')
           found = True

   if found: 
      return current_sensor
   else:
      log("Error: Unable to access " + URL)
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
            log("Info: No Templates with the name USM_Sensor found")
            return "1970-01-01"

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
     log("Error: Folder " + FOLDER + " not found")
     return

#########################################################################################################
def downloadSensor(download):

   global URL

   # Download the sensor
   log("Info: Downloading sensor from " + URL)

   # Create the directories we will use
   if not os.path.exists(download + '/ZIP'):
      os.makedirs(download + '/ZIP')

   if not os.path.exists(download + '/OVF'):
      os.makedirs(download + '/OVF')

   if not os.path.exists(download + '/vmdkMount'):
      os.makedirs(download + '/vmdkMount')


   bashCommand = 'wget -O ' + download + '/ZIP/usm-anywhere-sensor-vmware.zip ' + URL
   #bashCommand = 'wget -O ' + download + '/usm-anywhere-sensor-vmware.zip https://hotel.zzzz.io/tmp/small.zip'
   log("Info: " + bashCommand)
   process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
   curloutput = process.communicate()[0]  
   log("Info: " + curloutput)

   # unzip the sensor
   log("Info: Unzipping " + download + "/ZIP/usm-anywhere-sensor-vmware.zip")
   bashCommand = 'unzip -o -d ' + download + '/OVF ' + download + '/ZIP/usm-anywhere-sensor-vmware.zip'
   log("Info: " + bashCommand)
   os.system(bashCommand)

   # Mount the vmdk to the vmdkMount directory
   log("Info: Mounting VMDK to " + download + "/vmdkMount")
   bashCommand = 'guestmount -a ' + download + '/OVF/alienvault-usm/usm-disk1.vmdk -i --rw ' + download + '/vmdkMount/'
   log("Info: " + bashCommand)
   os.system(bashCommand)

   # Read the version number and store it as a var
   if not os.path.exists(download + '/vmdkMount/etc/alienvault/system_version'):
      log("Error: Could not access system_version file in disk mounted to " + download + "/vmdkMount")
      log("Error: Perhaps the extraction of the downloaded zip file failed")
      log("Error: Or perhaps the zip file was not a valid USM Anywhere Sensor")
      exit()

   with open(download + '/vmdkMount/etc/alienvault/system_version', 'r') as myfile:
      version=myfile.read().replace('\n', '')
   log("Info: Version " + version + " detected")

   # Unmount the vmdk
   log("Info: Unmounting VMDK")
   bashCommand = 'guestunmount ' + download + '/vmdkMount'
   log("Info: " + bashCommand)
   os.system(bashCommand)

   return version

   # Make Sensor name
   #new_template = "USMA_Sensor-" + version + "-" + current_sensor
   

#########################################################################################################

def insertKey(DOWNLOAD):

   SSH_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDNeK3OFirnHQaAkkGTcRSsTGjWQNqvr758+tQnq2Q5WtIJjH/zRqHC2t7JPeJXlIbgFe+/BsRUC0W6Yurdca/V9wFpwdJNFjdHhc3sKFMoPHT9cV7x1tahyjAFbzPPxCFVJdtAIDsayGFeN2luugehzB9rxaE5hdd3zr7ky+cAde7ComB58iGBSD1i72FIkW/aj39PEU6f86ignOvZBXaAcziYUI4/qSEBiHDpSU7u+Wm8ZeNOdonVPh4oMT0eKczEVd5RSw9YcdfRrW5qdbESolYAlGF28LIf92qVSrGcmfsOmiU7HQvlAHUAcOp+HPrARsLWCn8O1ho34m6UretR joriordan@alienvault.com"

   # Create subdirectory for vm
   if not os.path.exists(DOWNLOAD + '/VM'):
      os.makedirs(DOWNLOAD + '/VM')
   log("Info: Created " + DOWNLOAD + "/VM")

   # Convert to VM
   bashCommand = "ovftool " + DOWNLOAD + "/OVF/alienvault-usm/USM_sensor-node.ovf " + DOWNLOAD + "/VM/USM_sensor-node.vmx"
   log("Info: Converting to VM....")
   log("Info: " + bashCommand)
   os.system(bashCommand)

   # Delete orginal ovf 
   bashCommand = "rm -rf " + DOWNLOAD + "/OVF"
   log("Info: Removing orginal OVF")
   log("Info: " +  bashCommand)
   os.system(bashCommand)


   # Mount ovf
   bashCommand = 'guestmount -a ' + DOWNLOAD + '/VM/USM_sensor-node-disk1.vmdk -i --rw ' + DOWNLOAD + '/vmdkMount/'
   log('Info: Mounting read/write')
   log("Info: " + bashCommand)
   os.system(bashCommand)

   # Create folder and file with text
   os.makedirs(DOWNLOAD + '/vmdkMount/home/sysadmin/.ssh')
   f = open(DOWNLOAD + '/vmdkMount/home/sysadmin/.ssh/authorized_keys','w')
   f.write(SSH_KEY)
   f.close()
   log('Info: Wrote the SSH key for sysadmin')

   # Create folder and file with text
   os.makedirs(DOWNLOAD + '/vmdkMount/root/.ssh')
   f = open(DOWNLOAD + '/vmdkMount/root/.ssh/authorized_keys','w')
   f.write(SSH_KEY)
   f.close()
   log('Info: Wrote the SSH key for root')

   # Unmount folder
   log("Info: Unmounting the disk")
   bashCommand = 'guestunmount ' + DOWNLOAD + '/vmdkMount/'
   os.system(bashCommand)
   log('Info: Unmounted the mount')

   # Convert to new ovf in subfolder
   if not os.path.exists(DOWNLOAD + '/NewOVF'):
      os.makedirs(DOWNLOAD + '/NewOVF')
   log("Info: Created " + DOWNLOAD + "/NewOVF")

   log("Info: Repackaging the VM into a new OVF")
   bashCommand = "ovftool " + DOWNLOAD + "/VM/USM_sensor-node.vmx " + DOWNLOAD + "/NewOVF/USM_sensor-node.ovf"
   os.system(bashCommand)

   # Delete VM file
   bashCommand = "rm -rf " + DOWNLOAD + "/VM"
   log("Info: Removing the VM files")
   log("Info: " +  bashCommand)
   os.system(bashCommand)


#########################################################################################################

def cleanup(DOWNLOAD):
   # Delete orginal ovf and VM files
   bashCommand = "rm -rf " + DOWNLOAD + "/VM; rm -rf " + DOWNLOAD + "/NewOVF; rm -rf " + DOWNLOAD + "/vmdkMount; rm -rf " + DOWNLOAD + "/OVF"
   log("Cleaning up temporary directories, except for the ZIP file which I will overwrite the next time")
   log("Info: " +  bashCommand)
   os.system(bashCommand)


#########################################################################################################

def log(text):
   f = open('/var/log/deploy.log','a')
   data = datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " " + text + "\n"
   f.write(data)
   f.close()
   print text


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
	#print "Info: vCenter time: {}".format(service_instance.CurrentTime())
        #print ""
        #print "Hello {}".format(session_name)
        #print "You have successfully logged into {}".format(args.host)
	log(" ")
        log(" ")
        log("Info: Logging in as " + session_name)
	#print "Info: Session key", service_instance.content.sessionManager.currentSession.key

	FOLDER = args.folder
        DOWNLOAD = args.download

	# This dumps all of the vCenter data into an object
	content = service_instance.RetrieveContent()

        #Check current sensor release date
        current_sensor = currentSensor()
        if current_sensor is not None:
           log("Info: Latest sensor online is: " + current_sensor)
        else:
           log("Error: Unable to determine latest sensor")
           return -1

	# Send the content to lastSensor which will use it to search the folder for the latest sensor
        last_sensor = lastSensor(content, FOLDER)
        if last_sensor is not None:
           log("Info: Last sensor in the specified folder is " + last_sensor)
        else:
           log("Error: Previous sensor not found")
           return -1

        if current_sensor > last_sensor:
           log("Info: Update Required")

	   # get_obj is defined above. It searchs through the content for the specified object
	   folder = get_obj(content, [vim.Folder], FOLDER)
	   # Get the full path of the specified folder and upload the ovf to it
	   if folder is not None:
	      folderPath = parentFolders(folder)

	
	      # The download & upload will take a while so lets close out the vCenter connection as it times out after 15 minutes
              connect.Disconnect(service_instance)
	      
              # Download the new sensor and mount it to get the version number
	      version = downloadSensor(DOWNLOAD)

	      # Convert the OVF to a VM so we can insert the SSH key for sysadmin
   	      insertKey(DOWNLOAD) 
	      
              new_template = "USMA_Sensor-" + version + "-" + current_sensor
              log("Info: New template name will be" + new_template)
	      uploadOVF(folderPath, new_template, DOWNLOAD)
	      #uploadOVF(newOVFPath, new_template, DOWNLOAD)

	      # Now that we've finished downloading and uploading we will log back into vCenter
	      service_instance = connect.SmartConnect(host=args.host,
                                                      user=args.user,
                                                      pwd=args.password,
                                                      port=int(args.port))

              atexit.register(connect.Disconnect, service_instance)


              # This dumps all of the vCenter data into an object
              content = service_instance.RetrieveContent()
 
           else:
              log("Error: Folder " + FOLDER + " not found")
              return -1

           vm = get_vm_in_folder(content, [vim.VirtualMachine], new_template, FOLDER)
	   # If we found the specified VM we will edit it's hardware
	   if vm is not None:
	      log("Info: Found"  + vm.name + " in " + vm.parent.name)
	      if vm.parent.name == FOLDER:
	         modifyHardware(vm)
                 vm.MarkAsTemplate()
	      else:
	         log("Error: " + vm.name + " was not found in " + FOLDER)
	         return -1
	   else:
              log("Error: " + new_template + " not found")
              return -1
        

           # Clean up all of the folders that we created
           # We wll leave the ZIP behind as it will be overwritten the next time anyway
           cleanup(DOWNLOAD)

        else:
           log("Info: No update required")
           return 0


    except vmodl.MethodFault as error:
        #print "Caught vmodl fault : " + error.msg
        log(error.msg)
        cleanup(DOWNLOAD)
	return -1

    return 0

#########################################################################################################

# Start program
if __name__ == "__main__":
    main()

#########################################################################################################
