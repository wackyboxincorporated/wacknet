import pexpect

import sys



def test_gpio():

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

    print("\nListing processes...")

    child.sendline("ps aux")

    child.expect(r'\$')

    

    child.sendline("exit")

    child.expect(pexpect.EOF)

    print("\nDone.")



if __name__ == '__main__':

    test_gpio()

