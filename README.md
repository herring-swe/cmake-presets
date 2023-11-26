# CMake Presets Generator

<!---
[![dsa][pypi_project_img]][pypi_project_url]
[![dsa][pypi_travis_img]][pypi_travis_url]
[![dsa][docs_img]][docs_url]
-->

Utility to create CMake presets based on available system compilers such or by running environment setup scripts.

This project is created to overcome a limitation in the CMakePresets.json definition (as of 2023-11-26) where a configurePreset cannot source an environment from a script. This is especially a problem with Ninja generator, which can be hinted to find for instance Visual Studio or a standard installation of GCC but trouble arise when trying to combine it to use more tools like Intel oneAPI.

A possible solution is to setup the environment before running CMake. This is probably okay when building from command-line but not from an IDE. Typically an IDE (or glorified editor like vscode) would help setup the environment.

To overcome this limitation one can use this utility to create a cmake_presets.cmake include file. This file will contain one or several presets corresponding to the development environment for a specific user/machine. The main CMakePresets.json can include this file and presets can refer the other presets by using inheritence.

## Information

* Current state: Pre-alpha - Pushing for first release
* Free software: MIT license
<!---* Documentation: https://cmake-presets.readthedocs.io.-->

## Requirements

* Python 3.6 (tested up to 3.12)
* Windows or GNU/Linux
* CMake 3.27 (for running the presets)

## Features

* Can be run via CLI or imported in python script
* Scan the local machine for installed build tools
  * Show, filter and select from this list according to required specifications
* Generate CMake presets
  * Containing environment and/or cacheVariables
  * Depending on build tool, environment is created:
    * Directly (GCC)
    * From running setup scripts (MSVC, oneAPI, custom script)
    * Merge environment from a chain of tools
      * For example: MSVC + Intel oneAPI or MSVC + custom script
* Generated presets:
  * Possible to IGNORE in version control.
    * Only the main CMakePresets.json (containing no user/machine environment) should be version controlled.
  * Usable directly from command line without environment setup
  * Usable from Visual Studio Code (with CMake Presets, obviously)

## Supported compilers and tools
Disclaimer: It works on what I have, and able to, test it on.

* Target programming languages are: C/C++/Fortran
  * No cross platform toolkits are supported
  * Only x64 -> x64 tested
* MS Visual Studio or Build Tools for Visual Studio 2017 or higher
  * Scans using vswhere
  * Filtering of VS Version, Toolkit and Windows SDK
* GNU Compiler Collection (gcc, g++ and gfortran)
  * Scans standard GNU paths, /opt and $HOME
    * Groups tools by path, version and -dumpmachine string
  * Filtering of version and/or gfortran
  * NOTE, only tested on:
    * CentOS 7 (default 4.8.5 and SCL 8.3.1)
    * Ubuntu 22.04 (default 11)
    * openSUSE 15 (default 7)
    * Built from source: 8.2.0
    * NOT tested mingw or cygwin.
* Intel oneAPI (Intel Fortran Compiler) 2021.1.1 or higher
  * Supported components:
    * Intel Fortran Compiler (+ Classic)
    * Intel MKL
  * Scans standard install paths in /opt and $HOME
  * Filtering of version, optional compiler and components
  * NOTE, only tested: 2021.3 and 2024.0
* Custom script:
  * Linux shell script
  * Windows batch file

## Ideas for future

* Refactor and rename everything
  * Decide on TOOLKIT/TOOLSET/DEVKIT/BUILD TOOLS :')
  * Split up Toolkit into ToolkitSpec and Toolkit?
* Cross platform compiler detection and support?
  * Easy with MSVC, seems not so easy with GCC unless only focused support.
* VS Code extension (I need to learn TypeScript urgh)
* Mac.. I don't have a Mac.. osxcross support?
* Automatic coffee brewer

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) (stub!)

Possible ways to help

* Testing
* Add support for more tools
* Extension for vscode
* Mac support
* General improvements

<!---
[pypi_project_img]: https://img.shields.io/pypi/v/cmake_presets.svg
[pypi_project_url]: https://pypi.python.org/pypi/cmake_presets

[pypi_user_img]: https://img.shields.io/travis/herring-swe/cmake_presets.svg
[pypi_user_url]: https://travis-ci.com/herring-swe/cmake_presets

[docs_img]: https://readthedocs.org/projects/cmake-presets/badge/?version=latest
[docs_url]: https://cmake-presets.readthedocs.io/en/latest/?version=latest
-->
