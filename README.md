# WACKNET V1... 
 the only waydio to radio. Sort of.

You've totally heard of meshtastic[https://meshtastic.org/] , right?


TLDR; I made a radio system out of garbage, E32 modules, and old single board computers, because the internet went out.

the pre-project:

A while back (Months prior) I had gained another interest in trying to setup a meshtastic network in my town. 
However, I'm so far away from other towns that it wouldn't be cost-effective, nor would it be able to integrate into any meshes surrounding my town. (and it would not be cool enough.)
So I did some research and settled on E32-433-t20D 100MW LoRa radio modules, and ordered them.
They took weeks to arrive, and once they did, I had little for solid ideas on how to use them.

the Stardance:

Fast forward to Stardance opening up. I produce and submit Meaty Player for wackybox.org. 
That's all fine. 
Then, two weeks afterward, the entire network infrastructure leading into my town goes out due to a remote fire.
For days. Many, many days. Cell phones, WiFi, everything is out. You have to drive a few dozen miles out to get service.
I get bored fast. And I still have those E32 modules. I start digging through stuff. Uno Qs, ESP32, Arduino,... **RASPBERRY PI!**
I find my old Pi 4 2G and Pi 3. And I have a lot of old experiments with other radio stuff documented on my home server..
So I load up the WBS Interfill 8B with some old projects, documentation, the radio's manufacturer docs, and some ideas as context.
I reference those manufacturer docs and get both Pis *attached* to a radio each, and very slowly communicating with eachother just sending pings back and forth and blinking an LED to indicate those pings.
I spend the next 3 days or so gradually making changes and running across town and testing the hardware, integrating a 20x4 I2C LCD into the pi 4 and turning it into a very clunky handheld, controlled by a 
$20 USD random wireless mini keyboard I had sitting in the drawer. It was simple. 2.4kbps only, just text, very slow delivery, uncompressed. Just from handheld to base.
Whoever was at home with the base would open up its IP at port 8080 and use the very basic web UI to send and recieve messages over Wacknet. So a two person thing!
As the offline days continued, I got progressively more and more unsatisfied. I spent hours upon hours, adding all the features I could easily implement into both the web UI and the handheld.
I refined the UI a lot on the handheld side, adding some basic flairs and such. Then nearly *4 DAYS* were spent optimising transmission as much as possible, and adding support for all hardware channels and
speeds. NAK retransmission, an established handshake system, a wireless terminal, etc. All kinds of stuff.
The issue was: the base was constructed out of crayon box packages. The handheld was constructed out of various cardboard, packing materials, and a ton of scotch tape.
They work, but they're REALLY ugly. I do not have a 3D printer. My friend has an Ender 3 I can use, but he was out of town for work for an extended period, so I never got the chance to really come up with 
any 3D designs. It was just improvisation. 


And as such, you have Wacknet V1. And I need funding for V2. Bleh. Hope this is cool. There's a really long youtube video on the Hack Club page.
