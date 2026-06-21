import sys



with open("pi4_execute/handheld.py", "r") as f:

    code = f.read()



                

globals_target = """pending_responses = {}
pending_lock = threading.Lock()"""



globals_replace = """pending_responses = {}
pending_lock = threading.Lock()

outbound_lock = threading.Lock()
EMG_TST_MODE = False
last_heartbeat_time = time.time()
active_cmd_output = []
cmd_output_lock = threading.Lock()
command_eof_received = False
cmd_output_dirty = False
option_index = 0
typed_command = ""
typed_cmd_input = ""
"""



if globals_target in code:

    code = code.replace(globals_target, globals_replace, 1)

    print("Globals added successfully.")

else:

    print("Error: globals target not found.")



                                        

menu_items_target = """    MENU_ITEMS = [
        "Send Message",
        "Message Inbox",
        "Set Air Rate",
        "Set Channel",
        "Set Tx Power",
        "WiFi Settings",
        "Run Ping Test",
        "Telemetry Logs",
        "Shutdown"
    ]"""



menu_items_replace = """    MENU_ITEMS = [
        "Send Message",
        "Message Inbox",
        "Command Mode",
        "Set Air Rate",
        "Set Channel",
        "Set Tx Power",
        "WiFi Settings",
        "Run Ping Test",
        "Telemetry Logs",
        "Shutdown"
    ]"""



if menu_items_target in code:

    code = code.replace(menu_items_target, menu_items_replace, 1)

    print("MENU_ITEMS updated successfully.")

else:

    print("Error: menu_items target not found.")



                                          

boot_target = """    # Start threads
    threading.Thread(target=background_radio_rx_engine, daemon=True).start()
    threading.Thread(target=rx_cleaner, daemon=True).start()"""



boot_replace = """    # Start threads
    threading.Thread(target=background_radio_rx_engine, daemon=True).start()
    threading.Thread(target=rx_cleaner, daemon=True).start()
    threading.Thread(target=handheld_heartbeat_monitor_loop, daemon=True).start()"""



if boot_target in code:

    code = code.replace(boot_target, boot_replace, 1)

    print("Heartbeat launch added successfully.")

else:

    print("Error: boot target not found.")



with open("pi4_execute/handheld.py", "w") as f:

    f.write(code)



print("Patching completed.")

