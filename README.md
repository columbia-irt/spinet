# SPINET: System for Provisioning of IoT NETworks

## Installation Instructions
Create and activate a new Python 3 virtual environment:
```bash
$ python3 -m venv spinet
$ . spinet/bin/activate
```
Install the spinet package and extra dependencies from the git repository:
```bash
(spinet) $ pip install git+git://github.com/columbia-irt/spinet#egg=spinet
(spinet) $ pip install spinet[commissioner]
(spinet) $ pip install spinet[enrolled]
```
