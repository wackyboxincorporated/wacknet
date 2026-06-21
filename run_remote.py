import pexpect

import sys

import os



def run_cmd(ip, username, password, command):

                                                                                 

    cmd = f"ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{ip} '{command}'"

    child = pexpect.spawn(cmd, timeout=30)

    

                                                             

    index = child.expect([r'[pP]assword:', pexpect.EOF, pexpect.TIMEOUT])

    if index == 0:

        child.sendline(password)

                                                                    

        idx2 = child.expect([r'\[sudo\] password for', pexpect.EOF, pexpect.TIMEOUT])

        if idx2 == 0:

            child.sendline(password)

            child.expect(pexpect.EOF)

        elif idx2 == 1:

            pass            

        else:

            print("Sub-timeout.")

    elif index == 1:

        pass

    else:

        print("Timeout.")

    

    output = child.before.decode('utf-8', errors='ignore')

    return output



if __name__ == '__main__':

    if len(sys.argv) < 3:

        print("Usage: python3 run_remote.py <ip> <command>")

        sys.exit(1)

    ip = sys.argv[1]

    command = " ".join(sys.argv[2:])

    output = run_cmd(ip, "user", "guest", command)

    print(output)

