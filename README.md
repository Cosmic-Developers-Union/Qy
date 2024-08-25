# Qy

> Warning: The project is being developed rapidly and iteratively except before version 0.1.0, there will not be a truly stable API interface and built-in operators, and it is strongly recommended that you do not use it in production.

Qy Lang, a Lisp language implemented in and based on Python.

## Install

Use pip and github:

```shell
pip3 install -U -I git+https://github.com/Cosmic-Developers-Union/Qy.git
```

or

```powershell
python -m pip install -U -I git+https://github.com/Cosmic-Developers-Union/Qy.git
```

Use PyPi:

```shell
pip3 install QyLang
```

or

```powershell
python -m pip install QyLang
```

## Usage

### Operator

- quote
- atom
- eq
- car
- cdr
- cons
- cond

### Middle Langer

```python
from qy import qy

qy.eval(print, 'Hello World!')
```
