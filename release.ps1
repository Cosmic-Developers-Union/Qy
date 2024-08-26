git push
Remove-Item dist/*
python -m build
twine upload -r testpypi dist/*
twine upload dist/*