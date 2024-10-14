# Koji Build Automation

A program to interact with Koji server(s) to build RPM packages.

> [!NOTE]
> This program is still in early development

The aim of this project is to fetch package and tag info from upstream Koji instances such as from [Fedora's](https://koji.fedoraproject.org/koji/) instance and build those packages in a downstream koji instance, while keeping your patched compilers and/or custom RPM packages.

---

## Getting started

You can deploy your own Koji infrastructure following this [guide](https://docs.pagure.org/koji/server_howto/).

Alternatively you may use the shell scripts [here](https://github.com/arif-desu/koji-setup).

Then modify the [config.yml](./config.yml) file to specify the build parameters. 

----
## Methodology

This is a simplied flowchart:

<p align="center">
<img src=assets/kojiauto_flow.png  style="height:650px" align="middle" >
</p>
---

## Approach

Building and waiting on packages is heavily IO-bounded operation. Thus we employ asynchronous programming patterns to a big extent. 
We utilize generator objects and Python's asyncio library.

<p align="center">
<img src=assets/kojirebuild_prog.png style="height:650px" align="middle">
</p>

---

### TODO:
- [x] Incorporate logging library
- [x] Create task observer
- [x] Check NVR before calling build APIs
- [ ] Async task dispatcher
- [ ] Use comps to priortise builds based on groups
- [ ] Build packages in exact order of dependencies

---

## Reference

- [Koji APIs](https://koji.fedoraproject.org/koji/api)