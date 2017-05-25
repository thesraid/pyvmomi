#!/usr/bin/env python
import os

SSH_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDNeK3OFirnHQaAkkGTcRSsTGjWQNqvr758+tQnq2Q5WtIJjH/zRqHC2t7JPeJXlIbgFe+/BsRUC0W6Yurdca/V9wFpwdJNFjdHhc3sKFMoPHT9cV7x1tahyjAFbzPPxCFVJdtAIDsayGFeN2luugehzB9rxaE5hdd3zr7ky+cAde7ComB58iGBSD1i72FIkW/aj39PEU6f86ignOvZBXaAcziYUI4/qSEBiHDpSU7u+Wm8ZeNOdonVPh4oMT0eKczEVd5RSw9YcdfRrW5qdbESolYAlGF28LIf92qVSrGcmfsOmiU7HQvlAHUAcOp+HPrARsLWCn8O1ho34m6UretR joriordan@alienvault.com"

def main():

   # Var with ovf folder
   FOLDER = "/root/python/down/alienvault-usm"
   print FOLDER

   # Create subdirectory for vm
   if not os.path.exists(FOLDER + '/VM'):
      os.makedirs(FOLDER + '/VM')
   print "Created", FOLDER + "/VM"

   # Convert to VM
   bashCommand = "ovftool " + FOLDER + "/USM_sensor-node.ovf " + FOLDER + "/VM/USM_sensor-node.vmx" 
   print "Converting to VM...."
   os.system(bashCommand)

   # Create mount point
   if not os.path.exists(FOLDER + '/Mount'):
      os.makedirs(FOLDER + '/Mount')
   print "Created", FOLDER + "/Mount" 

   # Mount ovf
   bashCommand = 'guestmount -a ' + FOLDER + '/VM/USM_sensor-node-disk1.vmdk -i --rw ' + FOLDER + '/Mount/'
   print bashCommand
   os.system(bashCommand)

   # Create folder and file with text
   os.makedirs(FOLDER + '/Mount/home/sysadmin/.ssh')
   f = open(FOLDER + '/Mount/home/sysadmin/.ssh/authorized_keys','w')
   f.write(SSH_KEY)
   f.close()

   # Unmount folder
   bashCommand = 'guestunmount ' + FOLDER + '/Mount/'
   os.system(bashCommand)

   # Convert to new ovf in subfolder
   if not os.path.exists(FOLDER + '/NewOVF'):
      os.makedirs(FOLDER + '/NewOVF')
   print "Created", FOLDER + "/NewOVF"

   bashCommand = "ovftool " + FOLDER + "/VM/USM_sensor-node.vmx " + FOLDER + "/NewOVF/USM_sensor-node.ovf"
   os.system(bashCommand)

   # Delete orginal ovf and VM files

#########################################################################################################

# Start program
if __name__ == "__main__":
    main()

#########################################################################################################

