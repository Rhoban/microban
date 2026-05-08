# Microban: A Compact, Fully 3D-Printable Open-Source Humanoid Robot

[![License: CERN-OHL-S-2.0](https://img.shields.io/badge/Hardware-CERN--OHL--S--2.0-blue.svg)](LICENSE)

![Microban Prototype](link-to-a-cool-picture-of-your-robot.jpg) 
*(Note: Replace this with a good quality photo or GIF of Microban in action)*

Welcome to the **Microban** project! 

Microban is a ~30cm tall, fully open-source humanoid robot designed specifically for makers, students, and robotics enthusiasts. The core philosophy behind this project is **accessibility**: anyone with a standard desktop 3D printer and a few basic tools should be able to build their own Microban from scratch.

Aside from the motors and a few standard, easily sourced hardware components, **everything is 3D printable**. 

---

## ✨ Key Features

*   🤖 **100% Open-Source**: Mechanics, 3D models, and documentation are entirely free to use, modify, and distribute.
*   🖨️ **3D-Printable**: Designed to be printed on virtually any standard FDM desktop 3D printer (no support-heavy or overly complex geometries).
*   🔧 **DIY & Maker Friendly**: Uses standard, cheap, and easy-to-find off-the-shelf components (standard servos, common screws).
*   📏 **Compact Size**: Stands at approximately 30cm tall, making it the perfect desktop companion for robotics experimentation.

---

## 📁 Repository Structure

*   `/STL` — Contains all the 3D files ready to be sliced and printed.
*   `/STEP` — Contains the source STEP files for easy modification.

---

## 🛠️ Bill of Materials (BOM)

To keep this project highly accessible, Microban relies on common hardware. Here is a quick overview of what you will need:

| Component | Quantity | Description / Notes |
| :--- | :---: | :--- |
| **3D Printed Parts** | X | Check the `/STL` folder. Recommended material is PLA. |
| **Servo Motors** | 19 | XL330-M288-T from Dynamixel. |
| **Microcontroller**| 1 | Raspberry Pi Zero 2W. |
| **Board Hat** | 1 | X |
| **Power Supply** | 2 | 18650 3.7V Lithium-ion Batteries. |
| **Battery Holder** | 1 | 2x18650 Battery Holder. |
| **USB-C Charger** | 1 | Standard USB-C charger. |
| **BMS** | 1 | Battery Management System for 2x18650 batteries. |
| **M2x6 Plastic Screws**| ~X | Standard plastic screws for assembly. Recommended model is STP39. |
| **M2.2x8 Plastic Screws**| ~X | Standard plastic screws for assembly. Recommended model is STP39. |
| **20x30x0.3 Steel Shims** | 8 | X |
| **20x30x1 POM Shims** | 4 | X |

*(A full, detailed BOM with links to purchase components will be available in the the future.)*

---

## 🚀 Getting Started & Assembly

Building your own Microban is a straightforward process. 

1. **Print the parts:** Head over to the `/STL` folder. We recommend printing at *[insert recommended layer height, e.g., 0.2mm]* with *[insert infill, e.g., 20%]* infill.
2. **Source the hardware:** Gather the components listed in the BOM.
3. **Assemble:** Follow our step-by-step [Assembly Guide](link-to-docs) to put the mechanics together.
4. **Wire and Code:** *(Add brief instructions or links to the electronics/code section).*

---

## 🤝 Contributing

This project is community-driven! Whether it's designing a new head, improving the leg kinematics, writing code, or simply fixing typos in the documentation, contributions are always welcome. 

Feel free to fork the repository, make your changes, and submit a Pull Request. If you build your own Microban, please share it in the Discussions tab!

---

## 📄 License

This project is licensed under the **CERN-OHL-S-2.0** License - see the [LICENSE](LICENSE) file for details.


## Sources

Screws STP39 2x6: https://de.screwerk.com/fr/shop/detail/stp/STP39A0200060B.html
Screws STP39 2.2x8: https://de.screwerk.com/fr/shop/detail/stp/STP390220080B.html
