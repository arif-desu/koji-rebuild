# Koji Rebuild

A program to interact with Koji server(s) to build RPM packages.

The aim of this project is to fetch package and tag info from upstream Koji instances such as from [Fedora's](https://koji.fedoraproject.org/koji/) instance and build those packages in a downstream koji instance, while keeping your patched compilers and/or custom RPM packages.

---

## Setup Koji infrastructure

You can deploy your own Koji infrastructure following this [guide](https://docs.pagure.org/koji/server_howto/).

Alternatively you may use the shell scripts [here](https://github.com/arif-desu/koji-setup).

## Requirements
- `python3.11+`
- `poetry`

## Installation

### Clone the repository
```sh
git clone https://github.com/arif-desu/koji-build-automation
```
### Install
**It is recommended that this package is used in a virtual environment.**
```sh
poetry shell
```

```sh
poetry install
```

## Usage
```sh
koji-rebuild CONFIGFILE
```

The `CONFIGFILE` is a YAML formatted file. See [config.yaml](./config.yaml) for reference.

---

## Methodology

This is a simplified flowchart:

<p align="center">
<img src=assets/kojiauto_flow.png  style="height:650px" align="middle" >
</p>

---

## Approach

Building and waiting on packages is heavily IO-bounded operation. Thus we employ asynchronous programming patterns to a big extent, utilizing generator objects and Python's asyncio library.

<p align="center">
<img src=assets/koji_pythonrebuild.png style="height:800px" align="middle">
</p>

---

## Reference

- [Koji APIs](https://koji.fedoraproject.org/koji/api)
