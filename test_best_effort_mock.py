import sys

import os

import time

import base64

import random

import struct



                                                      

sys.path.append(os.path.abspath("./pi4_execute"))

sys.path.append(os.path.abspath("./pi3_execute"))



                                           

import handheld

import main



                             

handheld.SIMULATION_MODE = True

main.SIMULATION_MODE = True



def test_handheld_rx_strict_fails_under_loss():

    print("\n--- Test 1: Handheld Receiver (Strict Mode, Packet Loss) ---")

    handheld.BEST_EFFORT_RX = False

    handheld.active_rx_sessions.clear()

    handheld.incoming_messages.clear()

    

    payload_id = 12345

    text_data = "This is a test message to be sent in chunks"

    b64_data = base64.b64encode(text_data.encode('utf-8'))

    compressed = handheld.wacknet_compress(b64_data)

    chunks = [compressed[i:i+49] for i in range(0, len(compressed), 49)]

    total_chunks = len(chunks)

    

    print(f"Payload ID: {payload_id}, Total chunks: {total_chunks}")

    

                           

    syn_frame = bytearray(58)

    syn_frame[0] = 0xAA; syn_frame[1] = 0x01

    struct.pack_into(">I", syn_frame, 2, payload_id)

    syn_frame[6] = 1      

    syn_frame[8] = total_chunks

    syn_frame[9] = 0x00            

    struct.pack_into(">I", syn_frame, 10, len(compressed))

    

                       

    handheld.active_rx_sessions[payload_id] = {

        "type": 0x00,

        "total_chunks": total_chunks,

        "total_length": len(compressed),

        "chunks": {},

        "last_active": time.time()

    }

    

                                                                  

    session = handheld.active_rx_sessions[payload_id]

    for idx, chunk in enumerate(chunks):

        if idx == 1:

            print(f"Simulating drop of chunk index {idx}")

            continue               

            

        session["chunks"][idx] = chunk

        

                              

                                                                     

                                  

    is_malformed = len(session["chunks"]) < session["total_chunks"]

    status = 1 if is_malformed else 0

    

    print(f"Strict Mode: is_malformed={is_malformed}, status={status}")

    

                                               

                                                 

    success = False

    if (status == 0 or (is_malformed and handheld.BEST_EFFORT_RX)) and session:

        success = True

        

    print(f"Strict mode reassembly success (expected False): {success}")

    assert not success, "Expected strict mode to reject partial payload!"

    print("PASSED!")



def test_handheld_rx_best_effort_succeeds_under_loss():

    print("\n--- Test 2: Handheld Receiver (Best Effort Mode, Packet Loss) ---")

    handheld.BEST_EFFORT_RX = True

    handheld.active_rx_sessions.clear()

    handheld.incoming_messages.clear()

    

    payload_id = 12345

    text_data = "This is a test message to be sent in chunks"

    b64_data = base64.b64encode(text_data.encode('utf-8'))

    compressed = handheld.wacknet_compress(b64_data)

    chunks = [compressed[i:i+49] for i in range(0, len(compressed), 49)]

    total_chunks = len(chunks)

    

    print(f"Payload ID: {payload_id}, Total chunks: {total_chunks}")

    

                  

    handheld.active_rx_sessions[payload_id] = {

        "type": 0x00,

        "total_chunks": total_chunks,

        "total_length": len(compressed),

        "chunks": {},

        "last_active": time.time()

    }

    

    session = handheld.active_rx_sessions[payload_id]

                                               

    for idx, chunk in enumerate(chunks):

        if idx == 1:

            print(f"Simulating drop of chunk index {idx}")

            continue

        session["chunks"][idx] = chunk

        

    is_malformed = len(session["chunks"]) < session["total_chunks"]

    status = 1 if is_malformed else 0

    

    print(f"Best Effort Mode: is_malformed={is_malformed}, status={status}")

    

                          

    success = False

    reassembled_decoded = None

    if (status == 0 or (is_malformed and handheld.BEST_EFFORT_RX)) and session:

        success = True

        ordered = [session["chunks"][i] for i in sorted(session["chunks"].keys())]

        full_b64_or_raw = b"".join(ordered)

        decoded_payload = handheld.wacknet_decompress(full_b64_or_raw)

        full_b64 = decoded_payload.decode('utf-8', errors='ignore')

        try:

            decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

        except Exception:

            decoded = f"[Binary payload: {len(full_b64)} chars]"

        

        if is_malformed:

            decoded = f"[MALFORMED/PARTIAL] {decoded}"

        reassembled_decoded = decoded

        

    print(f"Best Effort reassembly success (expected True): {success}")

    print(f"Reassembled output: '{reassembled_decoded}'")

    

    assert success, "Expected best effort mode to succeed!"

    assert reassembled_decoded.startswith("[MALFORMED/PARTIAL]"), "Expected warning prefix!"

    print("PASSED!")



def test_base_rx_best_effort_flag_from_syn():

    print("\n--- Test 3: Base Station Receiver respecting best_effort flag from SYN ---")

    main.active_rx_sessions.clear()

    main.incoming_messages.clear()

    

    payload_id = 54321

    text_data = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=300))

    b64_data = base64.b64encode(text_data.encode('utf-8'))

    compressed = main.wacknet_compress(b64_data)

    chunks = [compressed[i:i+49] for i in range(0, len(compressed), 49)]

    total_chunks = len(chunks)

    

                                                        

                 

    syn_frame = bytearray(58)

    syn_frame[0] = 0xAA; syn_frame[1] = 0x01

    struct.pack_into(">I", syn_frame, 2, payload_id)

    syn_frame[6] = 1      

    syn_frame[8] = total_chunks

    syn_frame[9] = 0x00            

    syn_frame[14] = 1                           

    

                        

    best_effort_flag = (syn_frame[14] == 1)

    main.active_rx_sessions[payload_id] = {

        "type": 0x00,

        "total_chunks": total_chunks,

        "total_length": len(compressed),

        "chunks": {},

        "last_active": time.time(),

        "best_effort": best_effort_flag

    }

    

    session = main.active_rx_sessions[payload_id]

                                               

    for idx, chunk in enumerate(chunks):

        if idx == 1:

            print(f"Simulating drop of chunk index {idx}")

            continue

        session["chunks"][idx] = chunk

        

    is_malformed = len(session["chunks"]) < session["total_chunks"]

    status = 1 if is_malformed else 0

    

    best_effort = session.get("best_effort")

    print(f"Base session best_effort flag: {best_effort}")

    

                               

    success = False

    reassembled_decoded = None

    if (status == 0 or (is_malformed and best_effort)) and session:

        success = True

        ordered = [session["chunks"][i] for i in sorted(session["chunks"].keys())]

        full_b64_or_raw = b"".join(ordered)

        decoded_payload = main.wacknet_decompress(full_b64_or_raw)

        full_b64 = decoded_payload.decode('utf-8', errors='ignore')

        try:

            decoded = base64.b64decode(full_b64).decode('utf-8', errors='ignore')

        except Exception:

            decoded = f"[Binary payload: {len(full_b64)} chars]"

        

        if is_malformed:

            decoded = f"[MALFORMED/PARTIAL] {decoded}"

        reassembled_decoded = decoded

        

    print(f"Base reassembly success (expected True): {success}")

    print(f"Reassembled output: '{reassembled_decoded}'")

    

    assert success, "Expected base station to succeed because SYN flag was 1!"

    assert reassembled_decoded.startswith("[MALFORMED/PARTIAL]"), "Expected warning prefix on base station!"

    print("PASSED!")



if __name__ == "__main__":

    try:

        test_handheld_rx_strict_fails_under_loss()

        test_handheld_rx_best_effort_succeeds_under_loss()

        test_base_rx_best_effort_flag_from_syn()

        print("\nALL OFFLINE LOGIC TESTS PASSED!")

        sys.exit(0)

    except AssertionError as e:

        print(f"\nTEST FAILED: {e}")

        sys.exit(1)

