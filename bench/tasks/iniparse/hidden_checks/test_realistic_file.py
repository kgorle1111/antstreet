from iniparse import parse_ini

SAMPLE = """\
; global settings
name = demo
debug =

[server]
host = example.com
port = 8080
motd = "  welcome  "
# the next line is ignored
; and so is this one

[paths]
home = /home/demo
query = a=b&c=d

[server]
port = 9090

[empty]
"""


def test_a_realistic_file():
    assert parse_ini(SAMPLE) == {
        "": {"name": "demo", "debug": ""},
        "server": {"host": "example.com", "port": "9090", "motd": "  welcome  "},
        "paths": {"home": "/home/demo", "query": "a=b&c=d"},
        "empty": {},
    }


def test_the_same_file_with_crlf_endings_and_indentation():
    text = "\r\n".join("  " + line if line else line for line in SAMPLE.split("\n"))
    assert parse_ini(text) == parse_ini(SAMPLE)
