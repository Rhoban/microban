# Bill of Materials (BOM)

Here is a detailed Bill of Materials (BOM) for the project, including links to purchase each component and their approximate prices. Please note that prices may vary based on location and availability.

## Robot BOM

To build a complete Microban robot, you will need the following components:

| Component | Quantity | Price | Link | Description / Notes |
| :--- | :---: | :--- | :--- | :--- |
| Battery Holder | 1 | ~$5.00 | [Amazon](https://www.amazon.fr/gp/product/B08YDTSML8/ref=sw_img_1?smid=A9DEKVHK1XMRT&th=1) | 2x18650 Battery Holder. |
| BMS | 1 | ~$10.00 | [Amazon](https://www.amazon.fr/gp/product/B0GJLGG7MM/ref=ewc_pr_img_1?smid=A263J3XHEW00G8&psc=1) | Battery Management System for 2x18650 batteries. |
| Switch | 1 | ~$5.00 | [Amazon](https://www.amazon.fr/gp/product/B0F32NVDHW/ref=ewc_pr_img_1?smid=A3PA4HG72LIUMJ&psc=1) | Power switch for the robot. |
| Charger | 1 | ~$10.00 | [Amazon](https://www.amazon.fr/gp/product/B0BWTK7SVN/ref=ox_sc_act_title_1?smid=A25R4KS2AL1P7J&psc=1) | Standard USB-C charger. |
| Batteries | 2 | | ~$4.00 each | [Nkon](https://www.nkon.nl/fr/sony-murata-us18650-vtc6.html) | 18650 3.7V Lithium-ion Batteries. Murata VTC6 are recommended but not mandatory. |
| Raspberry Pi Zero 2W | 1 | $15.00 | [Raspberry Pi](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) | Microcontroller for the robot. |
| Custom Pollen Hat | 1 | ~$10.00 | INCOMING | Custom hat for Raspberry Pi Zero 2W. |
| 16GB micro SD card | 1 | ~$10.00 | ? | For Raspberry Pi OS and software. |
| Dynamixel XL330-M288-T | 19 | $23.90 each | [Robotis](https://en.robotis.com/shop_en/item.php?it_id=902-0163-000) | Servomotor with 1 motor, 1 180mm cable, 10 2.2x8 screws, 6 2x6 screws. |
| Filament material | <1 | ~$10.00 | Depends on the 3D printer | To print the robot parts. Less than one roll. |
| 20x30x1mm POM shims | 4 | TODO | ? | Alternative to needle bearings for motors without idler horns. |
| 25x30x0.3mm Steel shims | 8 | TODO | ? | Parts on which the POM shim rests. |

## Configuration Tools

In addition to the components that make up the robot, you will also need configuration tools to set up the Dynamixel motors:

| Component | Quantity | Price | Link | Description / Notes |
| :--- | :---: | :--- | :--- | :--- |
| Dynamixel U2D2 | 1 | $32.10 | [Robotis](https://en.robotis.com/shop_en/item.php?it_id=902-0132-000) | USB to Dynamixel adapter for motor configuration. |
| Dynamixel U2D2 Power Hub | 1 | $19.00 | [Robotis](https://en.robotis.com/shop_en/item.php?it_id=902-0145-001) | Power hub for U2D2. |

In case of building several robots, it is not necessary to buy several U2D2 and U2D2 Power Hub, as they are only required for the initial configuration of the motors. 

## Optional Components

TODO: verify if the M2x8 screws provided with the motors work for the M2.2x8 or if you need to buy M2.2x8 screws separately.

The number of cables provided with the motors should be sufficient for the robot, but you may need additional cables in case of damage. 
Having extra screws can also be useful in case of loss. For these reasons, here are some optional components you may want to consider:

| Component | Quantity | Price | Link | Description / Notes |
| :--- | :---: | :--- | :--- | :--- |
| Screws STP39 2x6 | 10 | ? | [Screwerk](https://de.screwerk.com/fr/shop/detail/stp/STP390200060S.html) | Optional screws for assembly. |
| Screws STP39 2.2x8 | 10 | ? | [Screwerk](https://de.screwerk.com/fr/shop/detail/stp/STP390220080B.html) | Optional screws for assembly. |
| Additional cables | 1 | ? | [Robotis](https://en.robotis.com/shop_en/item.php?it_id=903-0249-000) | Optional additional cables for motors. |

---

## Cost Summary

At the time of writing, the total cost of building **a Microban robot is approximately $533**, which includes all the necessary components. 
If you also include the configuration tools (Dynamixel U2D2 and U2D2 Power Hub), the **total cost rises to approximately $584**.