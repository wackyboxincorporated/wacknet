import pexpect

import sys



def check_logs():

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

    print("\nReading base station logs...")

    child.sendline("sudo journalctl -n 50 -u wacknet-base")

    idx = child.expect([r'\[sudo\] password for', r'\$'])

    if idx == 0:

        child.sendline(password)

        child.expect(r'\$')

        

    child.sendline("exit")

    child.expect(pexpect.EOF)

    print("\nLogs fetched.")



if __name__ == '__main__':

    check_logs()

