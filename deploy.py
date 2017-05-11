#!/usr/bin/env python

"""
Program to authenticate and print VM details
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

# Ignore SSL warnings
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

RAM = 8192
CPU = 4
MAC = "00:50:56:12:34:56"
ESXPATH = "/AV/host/AWC/awc-esx01.nil.com"

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

    parser.add_argument('-v', '--vm',
                        required=True,
                        action='store',
                        help='VM to display')

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

def parentFolders(folder):

   folderPath = ""
   depth = 5
   while folder.name != "vm":
      if depth != 0:
         folderPath = folder.name + "/" + folderPath
         folder = folder.parent
         depth = depth-1
      else:
         print "Error: Specified folder is nested in too many subdirectories (max: 5)"
         return -1

   return folderPath

#########################################################################################################

def uploadOVF(folderPath):

   global ESXPATH
   args = get_args()

   host=args.host
   user=args.user
   pwd=args.password
   vm = args.vm
   
   
   # Requires ovftool to be installed
   bashCommand = "ovftool --skipManifestCheck --machineOutput --noSSLVerify --disableVerification --datastore=AWC-004 --network='MGMT' --name=" + vm + " --vmFolder=" + folderPath + " --diskMode=thin ova/small.ova vi://'" + user + "':" + pwd + "@" + host + ESXPATH
   print ""
   print "Deploying", vm, "to", folderPath
   print ""
   #process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE, shell=True)
   #print process.communicate()[0]
   os.system(bashCommand) 


#########################################################################################################

def modifyHardware(vm):

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
      return -1

   print "Changing CPU to", CPU, "and Memory to", RAM, "MB"
   cspec = vim.vm.ConfigSpec()
   cspec.numCPUs = CPU
   cspec.numCoresPerSocket = 1
   cspec.memoryMB = RAM
   vm.Reconfigure(cspec)

   print "Changing MAC of the first NIC to", MAC
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

def main():
    """
    Simple command-line program for listing the vms in a foler.
    """

    args = get_args()

    try:
        service_instance = connect.SmartConnect(host=args.host,
                                                user=args.user,
                                                pwd=args.password,
                                                port=int(args.port))

        atexit.register(connect.Disconnect, service_instance)
	
	print " "
	session_name = service_instance.content.sessionManager.currentSession.fullName
        print "Hello {}".format(session_name)
        print "You have successfully logged into {}".format(args.host)
        # NOTE (hartsock): only a successfully authenticated session has a
        # session key aka session id.
	print " "
	print " "	

        VM = args.vm
	FOLDER = args.folder
	# This dumps all of the vCenter data into an object
	content = service_instance.RetrieveContent()
	# get_obj is defined above. It searchs through the content for the specified object
	folder = get_obj(content, [vim.Folder], FOLDER)
	if folder is not None:
	   folderPath = parentFolders(folder)
	   uploadOVF(folderPath)
        else:
           print "Folder", FOLDER, "not found"

        vm = get_obj(content, [vim.VirtualMachine], VM)
	# If we found the specified VM we will edit it's hardware
	if vm is not None:
	   print "Found", vm.name, "in", vm.parent.name
	   if vm.parent.name == FOLDER:
	      modifyHardware(vm)
              vm.MarkAsTemplate()
	   else:
	      print "Error:", vm.name, "was found in a folder called", vm.parent.name, ": I expected it to be in",FOLDER 
	      return -1
	else:
           print "Error:", VM, "not found"
           return -1



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
