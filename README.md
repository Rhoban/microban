# Microban: A Small, Fully Open-Source Humanoid Robot

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
*   `/CAD` — (Optional) Contains the source CAD files (e.g., STEP or Fusion360 files) for easy modification.
*   `/Docs` — Assembly guides, diagrams, and additional documentation.

---

## 🛠️ Bill of Materials (BOM)

To keep this project highly accessible, Microban relies on common hardware. Here is a quick overview of what you will need:

| Component | Quantity | Description / Notes |
| :--- | :---: | :--- |
| **3D Printed Parts** | 1 Set | Check the `/STL` folder. Recommended material: PLA or PETG. |
| **Servo Motors** | X | *[e.g., MG996R or SG90, specify the exact model]* |
| **Microcontroller**| 1 | *[e.g., Arduino Nano, ESP32, Raspberry Pi Pico]* |
| **Power Supply** | 1 | *[e.g., 2S LiPo Battery or standard 5V/6V power adapter]* |
| **M3 Screws & Nuts**| ~XX | Standard M3 hardware for assembly. |
| **Bearings** *(if any)*| X | *[e.g., 608ZZ standard skate bearings]* |

*(A full, detailed BOM with links to purchase components will be available in the [Wiki/Docs section].)*

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

This project is licensed under the **[Insert License Name, e.g., MIT, GNU GPLv3, or Creative Commons BY-SA 4.0]** License - see the [LICENSE](LICENSE) file for details.


## Sources

Screws STP39 2x6: https://de.screwerk.com/fr/shop/detail/stp/STP39A0200060B.html
Screws STP39 2.2x8: https://de.screwerk.com/fr/shop/detail/stp/STP390220080B.html
