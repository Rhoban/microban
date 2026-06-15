# Microban: A Compact, Fully 3D-Printable Open-Source Humanoid Robot

[![License: CERN-OHL-S-2.0](https://img.shields.io/badge/Hardware-CERN--OHL--S--2.0-blue.svg)](LICENSE)

<p align="center">
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/e7bc975c-ab70-4ce5-a882-225468f9ffff" />
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/df0143d0-566d-44a4-a285-8507b6c01a19" />
  <img height="350px" alt="image" src="https://github.com/user-attachments/assets/63b53182-face-4d78-9a65-7006be63cb9d" />
<p\>
  
Welcome to the **Microban** project! 

Microban is a ~30cm tall, fully open-source humanoid robot designed specifically for makers, students, and robotics enthusiasts. The core philosophy behind this project is accessibility: the total cost of the robot is kept relatively low, all components are 3D-printable or easily sourced, and the assembly process is guided with detailed instructions. This means that anyone with a standard desktop 3D printer and a few basic tools should be able to build their own Microban from scratch.

The idea behind Microban is to provide a platform for learning and experimentation in robotics. By making the design open-source, users are encouraged to modify, improve, and share their own versions of the robot. Whether you're interested in programming, mechanical design, or electronics, Microban offers a hands-on experience that can help you develop your skills in a fun and engaging way.

The main features of Microban are:
*   🤖 **100% Open-Source**: Mechanics, 3D models, and documentation are entirely free to use, modify, and distribute.
*   🔧 **DIY & Maker Friendly**: Guided assembly instructions, fully 3D-printable parts, relatively cheap components.
*   📏 **Compact Size**: Microban stands at approximately 30cm tall, making it the perfect desktop companion for robotics experimentation.

---

## 📁 CAD Files

<img height="300" alt="Capture d’écran du 2026-06-15 13-33-16" src="https://github.com/user-attachments/assets/8dab3c1c-3dc4-4dd1-9fc4-ea44fbaea734" align="left"/>

The CAD files for Microban are in the `cad/` directory of this repository. It contains all the printable parts in both STL and STEP formats.

A visual representation of the CAD can be found in the [Onshape assembly](https://cad.onshape.com/documents/d424992a192a8ce34ffce163/v/094edb3a534c5e0eac603427/e/b34620a03cc3a684006c5867?renderMode=0&uiState=6a2fb9408e6d9214d2637394). This interactive assembly allow to 

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

