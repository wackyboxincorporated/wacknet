import pexpect

import sys

import os



def upload_file(ip, username, password, local_path, remote_path):

    print(f"Uploading {local_path} to {username}@{ip}:{remote_path}...")

    cmd = f"scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {local_path} {username}@{ip}:{remote_path}"

    child = pexpect.spawn(cmd, timeout=30)

    

    index = child.expect([r'[pP]assword:', pexpect.EOF, pexpect.TIMEOUT])

    if index == 0:

        child.sendline(password)

        child.expect(pexpect.EOF)

    elif index == 1:

        print("Completed without password prompt.")

    else:

        print("Timeout.")

    

    print(child.before.decode('utf-8', errors='ignore'))

    print(f"Done uploading to {ip}.")



if __name__ == '__main__':

                                 

    upload_file("192.168.8.114", "user", "guest", "./pi3_execute/main.py", "~/trans/execute/main.py")

    upload_file("192.168.8.114", "user", "guest", "./pi3_execute/index.html", "~/trans/execute/index.html")

    

                             

    upload_file("192.168.8.182", "user", "guest", "./pi4_execute/handheld.py", "~/trans/execute/handheld.py")

