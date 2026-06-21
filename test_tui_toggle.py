import pexpect

import sys

import time



def run_test():

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

        return False

        

    child.expect(r'\$')

    print("\nConnected! Stopping background service...")

    child.sendline("sudo systemctl stop wacknet-handheld")

    idx = child.expect([r'\[sudo\] password for', r'\$'])

    if idx == 0:

        child.sendline(password)

        child.expect(r'\$')

        

    print("\nService stopped. Launching handheld.py...")

    child.sendline("python3 ~/trans/execute/handheld.py")

    

                                  

    print("\nWaiting for base connection state...")

    idx = child.expect([r'Stay at 0\.3kbps', r'EMG TST Searching', pexpect.TIMEOUT], timeout=15)

    

    if idx == 1:

        print("\nSearching for base, waiting for base to connect...")

        child.expect(r'Stay at 0\.3kbps', timeout=60)

    elif idx == 2:

        print("\nTimeout waiting for base state.")

                                                  

        child.sendline("\x1b")           

        child.expect(r'\$')

        child.sendline("sudo systemctl start wacknet-handheld")

        child.expect(r'\$')

        return False

        

    print("\nBase found! Selecting 'Stay at 0.3kbps'...")

    child.send("s")

    time.sleep(0.5)

    child.send("\n")

    

                             

    child.expect(r'1\. Send Message', timeout=5)

    print("\nEntered main menu. Navigating down to 'Best Effort Rx' (option 10)...")

    

                                                         

    for i in range(9):

        child.send("s")

        time.sleep(0.3)

        

    print("\nToggling 'Best Effort Rx'...")

                                             

    child.expect(r'\[ \] Best Effort Rx')

    print("\nFound unchecked toggle. Pressing Enter to select...")

    child.send("\n")

    time.sleep(0.5)

    

                                             

    child.expect(r'\[x\] Best Effort Rx')

    print("\nSUCCESS: Found checked toggle '[x] Best Effort Rx'!")

    

    print("\nToggling 'Best Effort Rx' back to unchecked...")

    child.send("\n")

    time.sleep(0.5)

    child.expect(r'\[ \] Best Effort Rx')

    print("\nSUCCESS: Toggled back to '[ ] Best Effort Rx'!")

    

    print("\nExiting handheld.py...")

    child.send("\x1b")                                      

    child.expect(r'\$')

    

    print("\nRestarting background service...")

    child.sendline("sudo systemctl start wacknet-handheld")

    child.expect(r'\$')

    print("Service restarted.")

    

    child.sendline("exit")

    child.expect(pexpect.EOF)

    print("Test connection closed.")

    return True



if __name__ == '__main__':

    success = run_test()

    if success:

        print("\nTUI Toggle Verification PASSED!")

        sys.exit(0)

    else:

        print("\nTUI Toggle Verification FAILED!")

        sys.exit(1)

