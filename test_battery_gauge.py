import sys

import os

import time

import json



                                      

sys.path.append(os.path.abspath("./pi3_execute"))



                                           

import main

main.SIMULATION_MODE = True



def cleanup():

    for p in ("/tmp/test_shm_bat.json", "/tmp/test_disk_bat.json"):

        if os.path.exists(p):

            try:

                os.remove(p)

            except Exception:

                pass



def test_battery_math():

    print("--- Test 1: Battery Math & Capacity ---")

    cleanup()

    gauge = main.BatteryFuelGauge(shm_path="/tmp/test_shm_bat.json", disk_path="/tmp/test_disk_bat.json")

    gauge.running = False

    

                                                        

    expected_mas = 2407.8 * 3600.0

    print(f"Expected Capacity: {expected_mas} mAs")

    print(f"Actual Capacity: {gauge.total_capacity_mas} mAs")

    assert abs(gauge.total_capacity_mas - expected_mas) < 1e-3

    assert abs(gauge.remaining_mas - expected_mas) < 1e-3

    assert abs(gauge.get_percentage() - 100.0) < 1e-3

    print("PASSED!")



def test_energy_draw_idle():

    print("\n--- Test 2: Energy Consumption (Idle State) ---")

    cleanup()

    gauge = main.BatteryFuelGauge(shm_path="/tmp/test_shm_bat.json", disk_path="/tmp/test_disk_bat.json")

    gauge.running = False                                  

    

    initial = gauge.remaining_mas

    gauge.last_update_time = time.time() - 10.0                              

    gauge._update_energy()

    

                                          

    consumed = initial - gauge.remaining_mas

    print(f"10s idle consumption: {consumed:.2f} mAs (Expected: 1650.0 mAs)")

    assert abs(consumed - 1650.0) < 1.0                                   

    print("PASSED!")



def test_energy_draw_heavy_tx():

    print("\n--- Test 3: Energy Consumption (Heavy TX State) ---")

    cleanup()

    gauge = main.BatteryFuelGauge(shm_path="/tmp/test_shm_bat.json", disk_path="/tmp/test_disk_bat.json")

    gauge.running = False

    

                          

    gauge.set_heavy_tx(True)

    initial = gauge.remaining_mas

    gauge.last_update_time = time.time() - 10.0                              

    gauge._update_energy()

    

                                                        

    consumed = initial - gauge.remaining_mas

    print(f"10s heavy TX consumption: {consumed:.2f} mAs (Expected: 2750.0 mAs)")

    assert abs(consumed - 2750.0) < 1.0

    print("PASSED!")



def test_ram_and_disk_persistence():

    print("\n--- Test 4: RAM & Disk Persistence ---")

    cleanup()

    shm_p = "/tmp/test_shm_bat.json"

    disk_p = "/tmp/test_disk_bat.json"

    

    gauge = main.BatteryFuelGauge(shm_path=shm_p, disk_path=disk_p)

    gauge.running = False

    

                         

    gauge.remaining_mas -= 500000.0

    percentage = gauge.get_percentage()

    

                

    gauge.save_state(to_disk=True)

    

                                                          

    assert os.path.exists(shm_p)

    assert os.path.exists(disk_p)

    

    with open(disk_p, "r") as f:

        data = json.load(f)

        print(f"Saved remaining capacity in file: {data['remaining_mas']} mAs")

        assert abs(data["remaining_mas"] - gauge.remaining_mas) < 1e-3

        

                                                             

    new_gauge = main.BatteryFuelGauge(shm_path=shm_p, disk_path=disk_p)

    new_gauge.running = False

    print(f"New gauge loaded percentage: {new_gauge.get_percentage():.2f}%")

    assert abs(new_gauge.get_percentage() - percentage) < 1e-3

    print("PASSED!")



def test_telemetry_payload_format():

    print("\n--- Test 5: Status Telemetry Format ---")

    cleanup()

    shm_p = "/tmp/test_shm_bat.json"

    disk_p = "/tmp/test_disk_bat.json"

    

    gauge = main.BatteryFuelGauge(shm_path=shm_p, disk_path=disk_p)

    gauge.running = False

    gauge.remaining_mas = gauge.total_capacity_mas * 0.845        

    gauge.save_state(to_disk=True)

    

                                     

    main.battery_gauge = gauge

    

    status = main.get_system_status()

    print("Status output:")

    print(status)

    

    lines = status.split("\n")

    assert lines[0] == "--- WackNet Status ---"

    assert lines[1] == "Battery: 84.5%"

    print("PASSED!")



def test_battery_reset():

    print("\n--- Test 6: Battery Reset ---")

    cleanup()

    gauge = main.BatteryFuelGauge(shm_path="/tmp/test_shm_bat.json", disk_path="/tmp/test_disk_bat.json")

    gauge.running = False

    

                           

    gauge.remaining_mas -= 1000000.0

    assert gauge.get_percentage() < 100.0

    

           

    gauge.reset_charge()

    assert abs(gauge.remaining_mas - gauge.total_capacity_mas) < 1e-3

    assert abs(gauge.get_percentage() - 100.0) < 1e-3

    print("PASSED!")



if __name__ == "__main__":

    test_battery_math()

    test_energy_draw_idle()

    test_energy_draw_heavy_tx()

    test_ram_and_disk_persistence()

    test_telemetry_payload_format()

    test_battery_reset()

    cleanup()

    print("\nALL OFFLINE TELEMETRY ENGINE TESTS PASSED!")

