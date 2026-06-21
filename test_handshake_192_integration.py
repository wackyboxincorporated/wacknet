import pexpect

import sys

import time

import threading

import requests



BASE_URL = "http://192.168.8.114:8080"



def reset_base_to_03k():

    """Force base station back to 0.3 kbps to ensure a clean starting state."""

    print("[PRE-TEST] Resetting base station to 0.3 kbps...")

    try:

        r = requests.post(f"{BASE_URL}/api/config", data={"air_rate": "0.3"}, timeout=15)

        print(f"[PRE-TEST] Reset response: {r.status_code} - {r.text}")

        time.sleep(3)                             

    except Exception as e:

        print(f"[PRE-TEST] Reset failed: {e}")



def trigger_config_change(ready_event):

    """Wait for the ready signal, then trigger the 19.2 kbps config change."""

    print("\n[TEST THREAD] Waiting for handheld to reach MENU before triggering...")

    ready_event.wait(timeout=120)

                                                                           

    time.sleep(2)

    print("\n[TEST THREAD] Triggering rate change to 19.2 kbps via Base Station API...")

    try:

        r = requests.post(f"{BASE_URL}/api/config", data={"air_rate": "19.2"}, timeout=30)

        print(f"\n[TEST THREAD] API Response: {r.status_code} - {r.text}")

    except Exception as e:

        print(f"\n[TEST THREAD] API Request failed: {e}")



def run_test():

    ip = "192.168.8.182"

    username = "user"

    password = "guest"



                                                            

    reset_base_to_03k()



                                                                                  

    ready_event = threading.Event()



                                                                            

    t = threading.Thread(target=trigger_config_change, args=(ready_event,), daemon=True)

    t.start()



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

    idx = child.expect([r'Stay at 0\.3kbps', r'EMG TST Searching', pexpect.TIMEOUT], timeout=20)



    if idx == 1:

        print("\nSearching for base, waiting for base to connect...")

        idx2 = child.expect([r'Stay at 0\.3kbps', pexpect.TIMEOUT], timeout=90)

        if idx2 == 1:

            print("\nTimeout: base never connected.")

            child.send("\x1b")

            try:

                child.expect(r'\$', timeout=5)

                child.sendline("sudo systemctl start wacknet-handheld")

                child.expect(r'\$')

            except Exception:

                pass

            return False

    elif idx == 2:

        print("\nTimeout waiting for base state.")

        child.send("\x1b")

        try:

            child.expect(r'\$', timeout=5)

            child.sendline("sudo systemctl start wacknet-handheld")

            child.expect(r'\$')

        except Exception:

            pass

        return False



    print("\nBase found! Selecting 'Stay at 0.3kbps'...")

    child.send("s")

    time.sleep(0.5)

    child.send("\n")



                             

    child.expect(r'1\. Send Message', timeout=10)

    print("\nEntered main menu. Signalling trigger thread...")

    ready_event.set()                                                     



    print("Waiting for background rate change transition to trigger...")



                                                         

    child.expect(r'CONFIRM received', timeout=30)

    print("\nSUCCESS: Handheld received CONFIG CONFIRM!")



    child.expect(r'VERIFY received.*Config confirmed', timeout=15)

    print("\nSUCCESS: Handheld verified new configuration!")



                                                                              

    print("\nWaiting for active heartbeat/ping-pong over 19.2 kbps...")

    child.expect(r'TELEMETRY.*PONG', timeout=60)

    print("\nSUCCESS: Received pong/telemetry over 19.2 kbps!")



    test_ok = True



    print("\nExiting handheld.py...")

    child.send("\x1b")

    child.expect(r'\$', timeout=10)



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

        print("\n19.2 kbps Handshake Verification PASSED!")

        sys.exit(0)

    else:

        print("\n19.2 kbps Handshake Verification FAILED!")

        sys.exit(1)

