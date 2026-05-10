from qy.reader import Symbol
from qy.reader import read_one_tuple
from qy.reader import write_tuple

S = Symbol

source = '(let (("abc" 1)) abc "abc")'
exchange_form = read_one_tuple(source)

assert exchange_form == (S("let"), ((S("abc"), S("1")),), S("abc"), S("abc"))

planned_form = (S("embed"), (S("load"), S("my docs")), S(":size"), 800)

print(exchange_form)
print(write_tuple(planned_form))
