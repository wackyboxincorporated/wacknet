import pexpect

import sys

import time



def run_cleanup():

    ip = "192.168.8.182"

    username = "user"

    password = "guest"

    

    print(f"Connecting to Handheld ({ip})...")

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

    print("\nConnected! Killing any stale python3 processes...")

    child.sendline("sudo killall -9 python3")

    idx = child.expect([r'\[sudo\] password for', r'\$'])

    if idx == 0:

        child.sendline(password)

        child.expect(r'\$')

        

    print("\nStopping background service...")

    child.sendline("sudo systemctl stop wacknet-handheld")

    child.expect(r'\$')

    

    print("\nChecking running processes:")

    child.sendline("ps aux | grep python")

    child.expect(r'\$')

    

    child.sendline("exit")

    child.expect(pexpect.EOF)

    print("\nCleanup complete.")



if __name__ == '__main__':

    run_cleanup()

