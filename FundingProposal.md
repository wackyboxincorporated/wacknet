# Wacknet V2

I understand that it kind of looks like I just tossed some parts together and barely did anything.
The funding is needed to *complete* and *refine* the project, (yes I started during Stardance!)
which will allow me to expand the existing system into a multi-node structure with enhanced transmission distances to cover my whole town.

As it is, my income and supplies are very limited. 

I can afford to spend maybe $30 on hardware to improve this, so I applied for Tier S by intention.

It's not one big unit, or one single piece of hardware, but *several smaller ones*.

The base, the handheld, the secondary handheld, and a relay unit.

This gives me the basis to easily integrate more nodes in the future, while establishing a complete product.

The required master parts list is roughly as follows:
4x E32-433T30d
2x high gain omnidirectional antenna
2x high-gain whip antenna
2x ESP32 dev board, dual USB-C
3x lithium batteries (varying capacity)
3x charge controllers
3x DC-DC step up 2.5A
1x 5 to 10 watt compact solar panel 5/6v
1x mini keyboard
1x 20x4 I2C LCD or mini OLED display
?x Various mount hardware, meshing material for waterproofing, Pi 4 heatsink and fan, solder

First steps:
Assemble all three battery systems so that it's easier for me to construct the final products.
Organise materials.
Modify existing firmware to be more friendly to per-device transmissions, using on-the-fly channel handling.
Install antennae on radios.

Current Handheld plan:
Swap 100mw module for 1 watt module, integrate battery system and test. 
Apply new heatsink and fan to Pi 4.
Design complete 3D printable housing and install the hardware. 

New Handheld plan:
Attach ESP32 board to new E32 module using Dupont wires/ Connectors and UART+aux
Test power and monitoring of battery system.
Attach screen, write basic testing firmware, and get it working.
Design 3D enclosure around the screen shape and install hardware and velcro for keyboard.
Port master handheld firmware to the . ESP ! and maybe redesign the UI system around the new display, if applicable?

Relay plan: 
Pretty much the same as the New Handheld, minus screen and keyboard, and with a solar panel.
ESP to E32, both to battery, wire up solar panel. 
Design case. Print it. Assemble it. Install components and waterproofing.
Install solar panel on center tilt-rotate mount.

Base Unit plan:
Swap for 1 watt radio. attach battery system, design and print case, install hardware.


I have fully established the visual and functional design of all hardware and the enclosures, but I haven't the opportunity to create the 3D print files.
This is mainly because trying to design the 3D files around... nothing as a reference is rather difficult. I will sketch basic display files for you to evaluate, but they are not the final ones.

Once the parts arrive and I have something to base my designs on, the final 3D files will be uploaded here.
I don't have CAD? software that is compatible (or includes) the hardware I'm using so I cannot prototype the designs in software easily. They will be documented and executed for your review.
I will create a series of proper videos logging progress as it goes on, and link them in a "VideosLog.md" file here.

To Hack Club evaluators:
Please contact me with questions, requirements, etc. 
I am more than willing to adapt to inputs.

This is not a finished product.
