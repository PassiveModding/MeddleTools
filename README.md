# Meddle Tools
This project is a Blender addon that provides various helper functions to assist working with [Meddle](https://github.com/PassiveModding/Meddle) exports.

## Installation
- Head to [Releases](https://github.com/PassiveModding/MeddleTools/releases)
- Download the latest MeddleTools.zip
- Install the zip in blender 4.2+ via `Edit > Preferences > Add-Ons > Install From Disk...`


## Usage
Access the menu via the main viewport. Current options will apply updates to all shader nodes in your scene based on the custom properties exported via Meddle.

![ViewPortMenu](img/viewportmenu.png)

### Terrain Example
1. Export terrain using Meddle
2. Import as glTF into blender

<img src="img/terrain_example_1.png" width="700"/>

3. Run `Fix bg.shpk`, selecting the `cache` directory from your Meddle export
4. Add-on looks up Meddle attached *Custom Properties* and fixes the shader nodes accordingly

<img src="img/terrain_example_2.png" width="700"/>