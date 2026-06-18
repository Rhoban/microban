# Assembly Guide

This guide provides detailed instructions on how to assemble the parts for the Microban robot. Printing the parts and buying the necessary components are prequisites for this guide, so please refer to the [Printing Guide](printing.md) and the [BOM](bom.md) before starting the assembly process. 

At any point during the assembly, you can refer to the [Onshape assembly](https://cad.onshape.com/documents/d424992a192a8ce34ffce163/v/7de3e6e40f0e1185d169e6d9/e/b34620a03cc3a684006c5867?renderMode=0&uiState=6a2fccab8e6d9214d2644ca7) to see how the parts fit together.

---

## Motor Setup

### Motor IDs

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

### Motor Configuration

First, factory reset all motors to clear any previous configurations if they have been used before. 
TODO: Add img of the factory reset in wizard ?

Then, some specific settings need to be applied through the Dynamixel Wizard software. While scanning for motors, be sure to scan for 57600 bps and Protocol 2.0, which are the default settings after a factory reset.

Apply the following settings to each motor:
    Return Delay Time: 0
    Baud Rate: 3 (1Mbps)
    Shutdown: 52 (Removing "Bit 0 Input voltage error")
    PWM Slope: 255 (no slope)

---

## Cable Routing

The XL330 motors used in the Microban robot are daisy-chained, which means that the motors are connected in series. This allows to limit the number of cables that need to be routed through the robot. The only exception is near the board, where the first cables are split to connect to several links. The following diagram shows how the motors are connected to each other and to the board.

### Splitter Cable

Two splitter cables are used to connect the first 

### Reducing Cable Length