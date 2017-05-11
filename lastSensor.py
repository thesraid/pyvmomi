#!/usr/bin/env python

"""
Program to authenticate and print VM details
"""
import sys
from datetime import date, datetime, timedelta
from shutil import copyfile
import os
import subprocess
import syslog
import time
import re

import atexit
import argparse
import getpass

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

from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim


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
                        help='Folder to list')


    args = parser.parse_args()

    if not args.password:
        args.password = getpass.getpass(
            prompt='Enter password for host %s and user %s: ' %
                   (args.host, args.user))
    return args

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

	# Print list of VMs in the specified folder
        FOLDER = args.folder
	# This dumps all of the vCenter data into an object
	content = service_instance.RetrieveContent()
	# get_obj is defined above. It searchs through the content for the specified folder
	# It returns a folder object
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
		 exit()

	   # If it's a match add it to the list
   	   if match:
     	     date_string = match.group()
     	     date = datetime.strptime(date_string, '%Y-%m-%d')
     	     templateList.append(date)

	   # Find the latest date
	   last_sensor_date = max(templateList)
	   last_sensor = last_sensor_date.strftime('%Y-%m-%d')

	   print "Last sensor on VMware is: " + last_sensor

	else:
	   print "Folder", FOLDER, "not found"

    except vmodl.MethodFault as error:
        #print "Caught vmodl fault : " + error.msg
        print error.msg
	return -1

    return 0

# Start program
if __name__ == "__main__":
    main()

