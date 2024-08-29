Remove-Item dist/*
Remove-Item -Recurse build
Remove-Item -Recurse *.egg-info
python -m build
twine check dist/*