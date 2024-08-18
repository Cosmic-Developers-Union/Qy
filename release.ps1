git push
rm dist/*
python -m build
twine upload -r testpypi dist/*
twine upload dist/*