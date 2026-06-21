import pexpect

import sys

import os



def fetch_folder(ip, username, password, remote_path, local_path):

    print(f"Fetching from {username}@{ip}:{remote_path} to {local_path}...")

    os.makedirs(local_path, exist_ok=True)

                                             

                                                           

    cmd = f"scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{ip}:{remote_path}/* {local_path}/"

    child = pexpect.spawn(cmd, timeout=30)

    

                                       

    index = child.expect([r'[pP]assword:', pexpect.EOF, pexpect.TIMEOUT])

    if index == 0:

        child.sendline(password)

        child.expect(pexpect.EOF)

    elif index == 1:

        print("Completed or failed without password prompt.")

    else:

        print("Timeout.")

    

    print(child.before.decode('utf-8', errors='ignore'))

    print(f"Done fetching from {ip}.")



if __name__ == '__main__':

    fetch_folder("10.250.10.83", "user", "guest", "~/trans/execute", "./pi3_execute")

    fetch_folder("10.250.1.44", "user", "guest", "~/trans/execute", "./pi4_execute")

