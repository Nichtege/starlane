"""The tests check the shipped files and the code, never the settings of the machine they run on.

A developer's own aos.local.toml (merged over aos.toml, see config.read_settings) and AOS_* variables in the shell would
otherwise change what the tests see: another vault, another language. Tests that need either set them themselves.
"""

import os

from aos import config

config.LOCAL_OVERRIDES = False
for _name in [n for n in os.environ if n.startswith("AOS_")]:
    del os.environ[_name]
os.environ["AOS_UI_LANGUAGE"] = "en"  # child processes (`python -m aos ...` in a checkout) never take aos.local.toml's language
