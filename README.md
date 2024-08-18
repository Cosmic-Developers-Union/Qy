# Qy

Qy Lang, a Lisp language implemented in and based on Python.

## Install

Use pip and github:

```shell
pip3 install -U --force-installed git+https://github.com/Cosmic-Developers-Union/Qy.git
```

or

```powershell
python -m pip install -U --force-installed git+https://github.com/Cosmic-Developers-Union/Qy.git
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
