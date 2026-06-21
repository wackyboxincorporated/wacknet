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

        

    print("\nService stopped. Waiting 5s for serial port to release...")

    time.sleep(5)

    print("\nLaunching handheld.py...")

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

    print("\nEntered main menu. Navigating to Command Mode...")

    

                                           

    child.send("s")

    time.sleep(0.5)

    child.send("s")

    time.sleep(0.5)

    child.send("\n")

    

                                   

    child.expect(r'Command: \(Enter\)', timeout=5)

    print("\nEntered Command Mode. Sending command: ping -c 5 127.0.0.1")

    child.send("ping -c 5 127.0.0.1\n")

    

                                   

    print("\nMonitoring command execution. Making sure heartbeat failsafe does NOT trigger...")

                                                                        

    idx = child.expect([r'\* New Message \*', r'Cmd Finished', r'Link Offline', pexpect.TIMEOUT], timeout=240)

    

    test_ok = False

    if idx in (0, 1):

        print("\nSUCCESS: Command finished or Return Message prompt appeared without triggering Link Offline!")

        if idx == 1:

                                                                                    

            child.expect([r'\* New Message \*', pexpect.TIMEOUT], timeout=60)

        

        print("\nSelecting 'Read' on the New Message prompt...")

        child.send("\n")                          

        

                                                                                

        child.expect([r'\[TKT-', pexpect.TIMEOUT], timeout=10)

        print("\nSUCCESS: Found Ticket ID [TKT-XXXX] in the final Return Message!")

        

        child.expect([r'64 bytes', pexpect.TIMEOUT], timeout=5)

        print("\nSUCCESS: Found command output in the Return Message!")

        

                         

        child.send("\x1b")                        

        child.expect(r'1\. Send Message', timeout=5)

        print("Returned to main menu successfully.")

        test_ok = True

    elif idx == 2:

        print("\nFAILURE: Heartbeat failsafe was triggered during command execution!")

    else:

        print("\nFAILURE: Timeout waiting for command or Return Message.")

        

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

    return test_ok



if __name__ == '__main__':

    success = run_test()

    if success:

        print("\nVerification PASSED!")

        sys.exit(0)

    else:

        print("\nVerification FAILED!")

        sys.exit(1)

