import pexpect

import sys

import time



def run_restart():

    ip = "192.168.8.114"

    username = "user"

    password = "guest"

    

    print(f"Connecting to Base Station ({ip})...")

    cmd = f"ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{ip}"

    child = pexpect.spawn(cmd, timeout=30)

    child.logfile_read = sys.stdout.buffer

    

    index = child.expect([r'[pP]assword:', pexpect.EOF, pexpect.TIMEOUT])

    if index == 0:

        child.sendline(password)

    else:

        print("Failed to connect or prompt password.")

        return

        

    child.expect(r'\$')

    print("\nConnected! Restarting wacknet-base service...")

    child.sendline("sudo systemctl restart wacknet-base")

    idx = child.expect([r'\[sudo\] password for', r'\$'])

    if idx == 0:

        child.sendline(password)

        child.expect(r'\$')

        

    print("\nChecking service status:")

    child.sendline("systemctl status wacknet-base")

    child.expect(r'\$')

    

    child.sendline("exit")

    child.expect(pexpect.EOF)

    print("\nBase Station restart complete.")



if __name__ == '__main__':

    run_restart()

