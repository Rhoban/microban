# Assembly Guide

This guide provides detailed instructions on how to assemble the parts for the Microban robot. Printing the parts and buying the necessary components are prequisites for this guide, so please refer to the [Printing Guide](printing.md) and the [BOM](bom.md) before starting the assembly process. 

At any point during the assembly, you can refer to the [Onshape assembly](https://cad.onshape.com/documents/d424992a192a8ce34ffce163/v/7de3e6e40f0e1185d169e6d9/e/b34620a03cc3a684006c5867?renderMode=0&uiState=6a2fccab8e6d9214d2644ca7) to see how the parts fit together.

The steps to assemble the robot are as follows:
1. [Motor Setup](#1-motor-setup): Configure the motors using the Dynamixel Wizard software.
2. [Cable Setup](#2-cable-setup): Prepare all the cables necessary for the assembly. 
3. [Leg Assembly](#3-leg-assembly): Assemble the legs of the robot.
4. [Torso Assembly](#4-torso-assembly): Assemble the torso and arms of the robot.
5. [Trunk Top Assembly](#5-trunk-top-assembly): Assemble the top of the trunk and the head of the robot.
6. [Battery Module Assembly](#6-battery-module-assembly): Assemble the battery module.
7. [Final Assembly](#7-final-assembly): Assemble all the parts together to complete the robot.


---

## 1. Motor Setup

The first step in the assembly process is to set up the motors. I highly recommend writing the motor IDs directly on them to avoid mixing them up during configuration and assembly. The following table lists the motor names and their corresponding IDs:

| Motor Name | ID |
|------------|----|
| Left Hip Yaw | 11 |
| Left Hip Roll | 12 |
| Left Hip Pitch | 13 |
| Left Knee | 14 |
| Left Ankle Pitch | 15 |
| Left Ankle Roll | 16 |
| Right Hip Yaw | 21 |
| Right Hip Roll | 22 |
| Right Hip Pitch | 23 |
| Right Knee | 24 |
| Right Ankle Pitch | 25 |
| Right Ankle Roll | 26 |
| Left Shoulder Pitch | 31 |
| Left Shoulder Roll | 32 |
| Left Elbow | 33 |
| Right Shoulder Pitch | 41 |
| Right Shoulder Roll | 42 |
| Right Elbow | 43 |
| Head | 51 |

To configure all the motors, connect one motor at a time to your PC using the U2D2 kit as presented in the image below. 

<img width="100%" alt="image" src="https://github.com/user-attachments/assets/240468b4-6963-4800-a00a-176226eb9185" />

<br>
<br>

Then, launch [Dynamixel Wizard](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_wizard2/). If your XL330 motor is not new, perform a factory reset by clicking on the "Recovery" button, selecting the XL-330-288 model and following the instructions. 

In the "Option" tab, select "Protocol 2.0", "57600 bps" as the baud rate, and verify that the correct COM port is selected. Then, click on the "Scan" button to detect the motor. Once the motor is detected, you can set the following parameters (and click on the "Save" button to save the settings):
- ID: the ID of the motor as listed in the table above
- Baud Rate: 3 (1Mbps)
- Return Delay Time: 0
- PWM Slope: 255 (no slope)
- Shutdown: 52 (Removing "Bit 0 Input voltage error")

Once the parameters are set, you can disconnect the motor and move on to the next one. If you want to check the motors at the end, you can connect them together as their IDs are set. You will need to change the baud rate of the scan to 1Mbps as it as been changed during the configuration. 

---

## 2. Cable Setup

The XL330 motors used in the Microban robot are daisy-chained, which means that the motors are connected in series. This allows to limit the number of cables that need to be routed through the robot. The only exception is near the board, where the first cables are split to connect to several links. The following diagram shows how the motors are connected to each other and to the board, and what cable lengths are used for each connection. 

<img width="100%" alt="routing" src="https://github.com/user-attachments/assets/fd655925-4968-4892-afc6-e4fe00495b89" />

### Splitter Cable

To create the 1-to-2 splitter cable, you can cut 2 cables of 180mm to obtain 3 half-cables of approximately 50mm (you don't need more length than that). Then, you can solder 2 of them to the 3rd one. Be careful to solder together the same wires, as an incorrect connection can damage permanently the motors. Do not forget to insulate the soldered connections with heat shrink tubing. 

To do the 1-to-3 splitter cable, the process is the same, but one of the 3 outgoing cables should be longer than the other two to allow for the robot opening from the top. So you should cut 2 cables of 180mm into 3 half-cables of approximately 50mm and one half-cable of approximately 120-130mm. 

The following images shows how the splitter cable should look like.

<img width="100%" alt="image190" src="https://github.com/user-attachments/assets/9384e878-72db-4b22-9de8-bbf1af28c7f9" />

### Reducing Cable Length

To reduce the length of the 180mm cables, you can cut them to the desired length and solder the ends back together, but it can lead to a weak connection and communication issues. A better solution is to re-crimp the cables to the desired length. To do this, you will need a crimping tool, JST EH crimp terminals, and optionally a wire stripper. You can check the [BOM](bom.md) for references.

<img width="100%" alt="image922" src="https://github.com/user-attachments/assets/e0d045f5-8e5a-4335-8f9a-7266d1a41eca" />

<br>
<br>

First, cut the cable to the desired length. The end cut to the correct length should be stripped to expose the wires on 2mm, not more. While crimping the terminals, the first crimp will be done on the plastic part of the terminal to hold the wire in place, and the second crimp will be done on the metal part of the terminal to make the electrical connection. The details of the crimping process are presented in this [video](TODO).

<img height="250px" alt="image958" src="https://github.com/user-attachments/assets/31fa1b7c-5757-465e-8c69-24e27dfedf70" />
<img height="250px" alt="image940" src="https://github.com/user-attachments/assets/82b92448-4931-4d4c-bf3d-20253d7764bc" />

<br>
<br>

Once the 3 end terminals are crimped, you need to retrieve the plastic housing from the second half of the cable. You can do this by rising the plastic stops on the housing with a small screwdriver and pulling the housing out. If you have trouble with this step, here is another [video](TODO) showing how to do it. 

Finally, you can insert the 3 crimped terminals into the plastic housing. The order of the wires is important, so make sure to insert them in their corresponding position. Here is a last [video](TODO) showing how to insert the terminals into the housing.


--- 

## 3. Leg Assembly

