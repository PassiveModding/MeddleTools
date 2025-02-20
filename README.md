# Meddle Tools
<a href="https://ko-fi.com/ramen_au"><img alt="Sponsor Badge" src="https://img.shields.io/badge/Meddle-Sponsor-pink?style=flat"></a>
<a href="https://github.com/PassiveModding/MeddleTools/releases"><img alt="MeddleTools" src="https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2FPassiveModding%2FMeddleTools%2Frefs%2Fheads%2Fmain%2FMeddleTools%2Fblender_manifest.toml&query=%24.version&label=MeddleTools"></a>
<a href="https://github.com/PassiveModding/Meddle/"><img alt="Meddle" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FPassiveModding%2FMeddle%2Frefs%2Fheads%2Fmain%2Frepo.json&query=%24.%5B0%5D.AssemblyVersion&label=Meddle"></a>

This project is a Blender addon that provides various helper functions to assist working with [Meddle](https://github.com/PassiveModding/Meddle) exports.

## Installation
- Head to [Releases](https://github.com/PassiveModding/MeddleTools/releases)
- Download the latest MeddleTools.zip
- Install the zip in blender 4.2+ via `Edit > Preferences > Add-Ons > Install From Disk...`

## Usage

1. Import meddle .gltf into blender
2. Select the model imported, or any meshes you wish to apply shaders to
3. Select 'Apply Shaders' and open the 'Cache' folder from your Meddle export folder

![Usage](Assets/panel.png)

> NOTE: Make sure you export with Character Texture Mode set to 'raw' from the Meddle plugin

![Meddle Setup](Assets/raw-mode.png)

## Attributions
### [Lizzer_Tools_Meddle](https://github.com/SkulblakaDrotningu/Lizzer_Tools_Meddle) - [GNU GPL v3.0](https://github.com/SkulblakaDrotningu/Lizzer_Tools_Meddle/blob/main/LICENSE.txt)
Initial [Character Shaders](./MeddleTools/shaders.blend) and logic for character shaders + starting point for embedded blender file, shader node setups for skin, face, hair and variants.
