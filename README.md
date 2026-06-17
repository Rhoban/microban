# Microban: A Compact, Fully 3D-Printable Open-Source Humanoid Robot

[![License: CERN-OHL-S-2.0](https://img.shields.io/badge/Hardware-CERN--OHL--S--2.0-blue.svg)](LICENSE)

<p align="center">
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/e7bc975c-ab70-4ce5-a882-225468f9ffff" />
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/df0143d0-566d-44a4-a285-8507b6c01a19" />
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/63b53182-face-4d78-9a65-7006be63cb9d" />
<p\>
  
Welcome to the **Microban** project! **This repository is currently under development**, so I advise you to wait for the 1.0 release before attempting to build your own robot. One of the major issue with building the robot currently is the **lack of off-the-shelf hat for the Raspberry Pi Zero 2W**. The custom hat will be available in the 1.0 release. In the meantime, feel free to explore the documentation and the CAD files, and stay tuned for updates on the project.

Microban is a \~30cm tall, fully open-source humanoid robot designed specifically for makers, students, and robotics enthusiasts. The core philosophy behind this project is accessibility: the total cost of the robot is kept relatively low (\~$550), all components are 3D-printable or easily sourced, and the assembly process is guided with detailed instructions. This means that anyone with a standard desktop 3D printer and a few basic tools should be able to build their own Microban from scratch.

The idea behind Microban is to provide a platform for learning and experimentation in robotics. By making the design open-source, users are encouraged to modify, improve, and share their own versions of the robot. Whether you're interested in programming, mechanical design, or electronics, Microban offers a hands-on experience that can help you develop your skills in a fun and engaging way.

The main features of Microban are:
*   🤖 **100% Open-Source**: Mechanics, 3D models, and documentation are entirely free to use and modify.
*   🔧 **DIY & Maker Friendly**: Guided assembly instructions, fully 3D-printable parts and cheap components.
*   📏 **Compact Size**: Microban is only 30cm tall, making it the perfect desktop companion for robotics experimentation.

---

## 🛠️ Components Overview

Here is a quick overview of what is in the robot:

| Component | Quantity | Description / Notes |
| :--- | :---: | :--- |
| **3D Printed Parts** | 26 | Check the CAD files. Recommended material is PLA. |
| **Servo Motors** | 19 | Dynamixel XL330-M288-T servomotor. |
| **Microcontroller**| 1 | Raspberry Pi Zero 2W. |
| **Board Hat** | 1 | Pollen custom hat for Raspberry Pi Zero 2W |
| **Power Supply** | 2 | 18650 3.7V Lithium-ion Batteries. |
| **Battery Holder** | 1 | 2x18650 Battery Holder. |
| **USB-C Charger** | 1 | Standard USB-C charger. |
| **BMS** | 1 | Battery Management System for 2x18650 batteries. |
| **Plastic Screws**| ~200 | Standard plastic screws for assembly. |
| **Steel & POM Shims** | 12 | Alternative to needle bearings for motors without idler horns. | 

A full, detailed Bill Of Materials (BOM) with links to purchase and prices is available in [docs/bom.md](docs/bom.md)

---

## 📁 CAD Files

<img height="350px" alt="Capture d’écran du 2026-06-15 13-33-16" src="https://github.com/user-attachments/assets/8dab3c1c-3dc4-4dd1-9fc4-ea44fbaea734" align="right"/>

The CAD files for Microban are in the `cad/` directory of this repository. It contains all the printable parts in both STL and STEP formats.

A visual representation of the 3D model can be found in the [Onshape assembly](https://cad.onshape.com/documents/d424992a192a8ce34ffce163/v/7de3e6e40f0e1185d169e6d9/e/b34620a03cc3a684006c5867?renderMode=0&uiState=6a2fccab8e6d9214d2644ca7). This interactive assembly allows you to explore the robot's design in detail, providing a better understanding of how the parts fit together. It also serves as a reference for assembly, helping you visualize the final product and ensuring that you can correctly identify each component during the build process.

An emphasis is placed on the range of motion of the 19 degrees of freedom of the robot. It allows for a wide variety of movements, making it suitable for various applications. Stops are integrated into the design to control which self-collisions are likely to occur, ensuring that the robot can move safely without damaging itself. The design also takes into account the cable routing for the servo motors, ensuring that the wires are neatly organized and do not interfere with the robot's movements.

---

## 🚀 Getting Started 

To build your own Microban, you will need to follow these steps:

1. **Source the hardware:** Gather the components listed in the [BOM](docs/bom.md). Links are provided to purchase each item, but feel free to source them from your preferred suppliers. Some components, like the Dynamixel motors, may have specific distributors depending on your location, which can impact the total cost. 

2. **Print the parts:** Head over to the `cad/stl/` folder and print all the parts using a 3D printer. The recommended filament is PLA with a layer height of 0.12mm and a 15% infill. Some parts require specific orientations for printing to ensure strength and proper fit. Refer to the guide [docs/printing.md](docs/printing.md) for detailed instructions on how to print each part correctly.

3. **Assemble:** Follow our step-by-step [Assembly Guide](docs/assembly.md) to put the mechanics together.

4. **Wire and Code:** *(Add brief instructions or links to the electronics/code section).*

---

## 🤝 Contributing

This project is community-driven! Whether it's designing a new head, improving the leg kinematics, writing code, or simply fixing typos in the documentation, contributions are always welcome. 

Feel free to fork the repository, make your changes, and submit a Pull Request. If you build your own Microban, please share it in the Discussions tab!

---

## 📄 License

This project is licensed under the **CERN-OHL-S-2.0** License - see the [LICENSE](LICENSE) file for details.

---

## Citation

If you use Microban in your research, please cite it as follows:

```
TODO
```
